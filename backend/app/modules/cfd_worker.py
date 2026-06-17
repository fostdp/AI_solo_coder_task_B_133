"""
cfd_worker: CFD 流体仿真独立 Worker 进程
设计动机：
  1. CFD 仿真（含对流扩散显式Euler迭代）是 CPU 密集型，阻塞主线程
  2. 拆到独立子进程，FastAPI 主事件循环不被阻塞
  3. 使用 multiprocessing.Queue 传递任务和结果
  4. 提供同步/异步两种调用方式，兼容测试环境

使用方式：
    # 模式A：Worker 子进程模式（生产）
    worker = CFDWorkerProcess()
    worker.start()
    future = worker.submit_task(task_id="t1", **params)
    result = future.result(timeout=30)  # 阻塞等待
    worker.stop()

    # 模式B：fallback 直接调用（测试）
    worker = CFDWorkerProcess()
    worker.set_local_simulator(my_cfd_instance)
    result = worker.run_local(**params)  # 直接跑，不启子进程
"""

import logging
import multiprocessing as mp
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 任务对象
# ---------------------------------------------------------------------------
@dataclass(order=True)
class CfdTask:
    """CFD 任务（带优先级，数值越小优先级越高）"""
    priority: int = field(compare=True, default=10)
    task_id: str = field(compare=False, default_factory=lambda: uuid.uuid4().hex)
    params: Dict[str, Any] = field(compare=False, default_factory=dict)
    submitted_at: float = field(compare=False, default_factory=time.time)


@dataclass
class CfdTaskResult:
    task_id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# 子进程 Worker 函数（在独立进程中运行）
# ---------------------------------------------------------------------------
def _worker_process_entry(
    task_queue: mp.Queue,
    result_queue: mp.Queue,
    stop_event: "mp.synchronize.Event",
    cfd_config: Dict[str, Any],
):
    """
    CFD Worker 子进程入口函数。
    在这里 import cfd_simulator，构建实例，循环处理任务。
    子进程是一个隔离的 Python 解释器，不继承主进程的任何模块。
    """
    try:
        from ..config_loader import load_dynasty_lamps_config

        # 子进程内构造 CFD simulator（使用 None db/bus，纯模式下不依赖数据库和总线）
        from .cfd_simulator import CFDSimulator
        from ..bus import MessageBus
        from ..config import settings
        from ..database import AsyncSessionLocal

        lamps_cfg = cfd_config.get("dynasty_lamps_cfg") or load_dynasty_lamps_config()
        try:
            db = AsyncSessionLocal()
        except Exception:
            db = None
        try:
            bus = MessageBus(settings.REDIS_URL)
        except Exception:
            bus = None
        simulator = CFDSimulator(db, bus)

        logger.info("[CFD-Worker] 子进程启动，PID=%s，等待任务...", mp.current_process().pid)
        result_queue.put({
            "_type": "worker_ready",
            "pid": mp.current_process().pid,
        })

        while not stop_event.is_set():
            try:
                task: CfdTask = task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:
                break  # 毒丸终止

            started = time.time()
            try:
                # 执行 CFD 仿真
                params = task.params or {}
                cfd_res = simulator.simulate(**params)
                result_queue.put({
                    "_type": "task_result",
                    "task_id": task.task_id,
                    "success": True,
                    "result": cfd_res,
                    "started_at": started,
                    "finished_at": time.time(),
                    "duration_ms": (time.time() - started) * 1000,
                })
            except Exception as e:
                logger.exception("[CFD-Worker] 任务 %s 异常: %s", task.task_id, e)
                result_queue.put({
                    "_type": "task_result",
                    "task_id": task.task_id,
                    "success": False,
                    "error": str(e),
                    "started_at": started,
                    "finished_at": time.time(),
                    "duration_ms": (time.time() - started) * 1000,
                })

        logger.info("[CFD-Worker] 子进程退出，PID=%s", mp.current_process().pid)
    except Exception as e:
        logger.exception("[CFD-Worker] 子进程启动失败: %s", e)
        try:
            result_queue.put({
                "_type": "worker_error",
                "error": str(e),
            })
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Future 异步句柄
# ---------------------------------------------------------------------------
class CfdFuture:
    """CFD 任务的 Future 句柄，用于等待结果"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._event = threading.Event()
        self._result: Optional[CfdTaskResult] = None

    def set_result(self, result: CfdTaskResult):
        self._result = result
        self._event.set()

    def done(self) -> bool:
        return self._event.is_set()

    def result(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        if not self._event.wait(timeout=timeout):
            raise TimeoutError(f"CFD 任务 {self.task_id} 超时")
        if not self._result:
            raise RuntimeError("Future 完成但无结果")
        if not self._result.success:
            raise RuntimeError(f"CFD 任务失败: {self._result.error}")
        return self._result.result


# ---------------------------------------------------------------------------
# CFD Worker 管理器（主进程侧使用）
# ---------------------------------------------------------------------------
class CFDWorkerProcess:
    """
    CFD 独立子进程管理器。
    - 模式A（生产）：start() 启子进程，submit_task() 异步
    - 模式B（测试）：set_local_simulator() 后 run_local() 同步，不启子进程
    """

    def __init__(
        self,
        dynasty_lamps_cfg: Optional[Dict] = None,
        task_queue_maxsize: int = 64,
        result_queue_maxsize: int = 128,
    ):
        self.dynasty_lamps_cfg = dynasty_lamps_cfg
        self.task_queue: "mp.Queue[CfdTask]" = mp.Queue(maxsize=task_queue_maxsize)
        self.result_queue: mp.Queue = mp.Queue(maxsize=result_queue_maxsize)
        self.stop_event = mp.Event()
        self._process: Optional[mp.Process] = None
        self._result_thread: Optional[threading.Thread] = None
        self._futures: Dict[str, CfdFuture] = {}
        self._local_simulator = None  # 模式B 用
        self._started = False
        self._worker_pid: Optional[int] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        """启动子进程 + 结果监听线程"""
        if self._started:
            return
        self.stop_event.clear()
        self._process = mp.Process(
            target=_worker_process_entry,
            args=(
                self.task_queue,
                self.result_queue,
                self.stop_event,
                {"dynasty_lamps_cfg": self.dynasty_lamps_cfg},
            ),
            name="CFD-Worker",
            daemon=True,
        )
        self._process.start()

        # 等待 worker_ready 消息
        try:
            msg = self.result_queue.get(timeout=10)
            if msg.get("_type") == "worker_ready":
                self._worker_pid = msg.get("pid")
                logger.info("[CFDWorker] Worker 就绪，PID=%s", self._worker_pid)
            elif msg.get("_type") == "worker_error":
                raise RuntimeError(f"CFD Worker 启动失败: {msg.get('error')}")
        except queue.Empty:
            raise RuntimeError("CFD Worker 启动超时（10秒未就绪）")

        # 启动结果监听线程
        self._result_thread = threading.Thread(
            target=self._result_listener,
            name="CFD-Result-Listener",
            daemon=True,
        )
        self._result_thread.start()
        self._started = True

    def stop(self, timeout: float = 5.0) -> None:
        """优雅关闭子进程"""
        if not self._started:
            return
        self.stop_event.set()
        try:
            self.task_queue.put(None, timeout=0.5)  # 毒丸
        except Exception:
            pass
        if self._process:
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                logger.warning("[CFDWorker] Worker 未及时退出，强制终止")
                self._process.terminate()
        self._started = False
        self._worker_pid = None
        # 清空 futures
        for f in self._futures.values():
            if not f.done():
                f.set_result(CfdTaskResult(
                    task_id=f.task_id,
                    success=False,
                    error="Worker 已停止",
                ))
        self._futures.clear()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()

    # ------------------------------------------------------------------
    # 结果监听（线程）
    # ------------------------------------------------------------------
    def _result_listener(self):
        """在独立线程中循环从 result_queue 取结果，分发到 futures"""
        while self._started and not self.stop_event.is_set():
            try:
                msg = self.result_queue.get(timeout=0.3)
            except queue.Empty:
                continue
            except (EOFError, BrokenPipeError):
                logger.warning("[CFDWorker] 结果队列关闭")
                break

            if not isinstance(msg, dict):
                continue
            if msg.get("_type") != "task_result":
                continue

            task_id = msg.get("task_id", "")
            result = CfdTaskResult(
                task_id=task_id,
                success=msg.get("success", False),
                result=msg.get("result"),
                error=msg.get("error"),
                started_at=msg.get("started_at", 0.0),
                finished_at=msg.get("finished_at", 0.0),
                duration_ms=msg.get("duration_ms", 0.0),
            )
            future = self._futures.pop(task_id, None)
            if future:
                future.set_result(result)
            else:
                logger.debug("[CFDWorker] 收到无匹配 Future 的任务结果: %s", task_id)

    # ------------------------------------------------------------------
    # 异步任务提交
    # ------------------------------------------------------------------
    def submit_task(
        self,
        priority: int = 10,
        task_id: Optional[str] = None,
        **cfd_params,
    ) -> CfdFuture:
        """
        提交 CFD 任务，异步返回 Future。
        典型参数：
          flue_temperature, flue_velocity, ambient_temperature,
          ambient_humidity, oil_consumption, fuel_type, lamp_type
        """
        if not self._started:
            raise RuntimeError("CFDWorker 未启动，请先调用 start()")
        tid = task_id or uuid.uuid4().hex
        task = CfdTask(
            priority=priority,
            task_id=tid,
            params=dict(cfd_params),
        )
        future = CfdFuture(tid)
        self._futures[tid] = future
        self.task_queue.put(task)
        return future

    # ------------------------------------------------------------------
    # 模式B：本地同步（不启子进程，用于测试/简单场景）
    # ------------------------------------------------------------------
    def set_local_simulator(self, simulator_instance: Any) -> None:
        """设置本地 simulator 后，可以直接 run_local，不启动子进程"""
        self._local_simulator = simulator_instance

    def run_local(self, **cfd_params) -> Dict[str, Any]:
        """
        同步执行 CFD（不启子进程）。
        必须先调用 set_local_simulator()，否则懒加载构造带 db/bus 的实例。
        """
        sim = self._local_simulator
        if sim is None:
            try:
                from ..bus import MessageBus
                from ..config import settings
                from ..database import AsyncSessionLocal
                from .cfd_simulator import CFDSimulator
                try:
                    db = AsyncSessionLocal()
                except Exception:
                    db = None
                try:
                    bus = MessageBus(settings.REDIS_URL)
                except Exception:
                    bus = None
                sim = CFDSimulator(db, bus)
                self._local_simulator = sim
            except Exception as e:
                raise RuntimeError(f"无法构造 CFD simulator: {e}") from e
        return sim.simulate(**cfd_params)

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------
    @property
    def worker_pid(self) -> Optional[int]:
        return self._worker_pid

    @property
    def is_running(self) -> bool:
        return self._started and self._process is not None and self._process.is_alive()

    @property
    def pending_tasks(self) -> int:
        return len(self._futures)

    @property
    def queue_size(self) -> int:
        try:
            return self.task_queue.qsize()
        except NotImplementedError:
            return -1
