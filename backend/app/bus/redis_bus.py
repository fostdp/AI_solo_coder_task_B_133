import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class MessageBus:
    """基于 Redis Pub/Sub 的事件总线 + 内存回退

    当 Redis 可用时走真实 Pub/Sub，否则使用 in-process asyncio.Queue
    保证在本地开发环境（无Redis）也能完整运行。
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url
        self._redis = None
        self._inproc: Dict[str, asyncio.Queue] = {}
        self._subscriber_tasks: Dict[str, asyncio.Task] = {}
        self._use_redis = False

    async def connect(self) -> None:
        if not self._redis_url:
            logger.info("未配置Redis URL，使用内存事件总线")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url)
            await self._redis.ping()
            self._use_redis = True
            logger.info(f"Redis事件总线已连接: {self._redis_url}")
        except Exception as e:
            logger.warning(f"Redis连接失败，回退到内存事件总线: {e}")
            self._redis = None
            self._use_redis = False

    async def close(self) -> None:
        for task in list(self._subscriber_tasks.values()):
            task.cancel()
        self._subscriber_tasks.clear()
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
        self._redis = None
        self._use_redis = False

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    async def publish(self, channel: str, payload: Dict[str, Any]) -> int:
        if self._use_redis:
            try:
                data = json.dumps(payload, ensure_ascii=False, default=str)
                return await self._redis.publish(channel, data)
            except Exception as e:
                logger.error(f"Redis发布失败[{channel}]: {e}，回退内存")
        # 内存回退
        if channel not in self._inproc:
            self._inproc[channel] = asyncio.Queue()
        await self._inproc[channel].put(payload)
        return 1

    # ------------------------------------------------------------------
    # 订阅
    # ------------------------------------------------------------------
    async def subscribe(
        self,
        channel: str,
        handler: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        if channel in self._subscriber_tasks:
            logger.warning(f"通道[{channel}]已有订阅者，覆盖")
            await self.unsubscribe(channel)

        if self._use_redis:
            task = asyncio.create_task(self._redis_consumer(channel, handler))
        else:
            task = asyncio.create_task(self._inproc_consumer(channel, handler))
        self._subscriber_tasks[channel] = task
        logger.info(f"已订阅通道[{channel}]")

    async def unsubscribe(self, channel: str) -> None:
        task = self._subscriber_tasks.pop(channel, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _redis_consumer(self, channel: str, handler) -> None:
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                except Exception as e:
                    logger.error(f"Redis消息解码失败[{channel}]: {e}")
                    continue
                try:
                    await handler(payload)
                except Exception as e:
                    logger.exception(f"消息处理器异常[{channel}]: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Redis消费者异常[{channel}]: {e}")

    async def _inproc_consumer(self, channel: str, handler) -> None:
        if channel not in self._inproc:
            self._inproc[channel] = asyncio.Queue()
        queue = self._inproc[channel]
        try:
            while True:
                payload = await queue.get()
                try:
                    await handler(payload)
                except Exception as e:
                    logger.exception(f"内存消费者异常[{channel}]: {e}")
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
