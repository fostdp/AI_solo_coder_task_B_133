import sys
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.routers.sensor import router as sensor_router
from app.bus import MessageBus
from app.database import AsyncSessionLocal
from app.modules import (
    ModbusReceiver,
    CFDSimulator,
    AirQualityAnalyzer,
    AlarmMQTTService,
)
from app.config_loader import load_fuel_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 应用状态：总线 + 四个模块
# ---------------------------------------------------------------------------
APP_STATE = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"启动 {settings.APP_NAME} v2.0（微服务解耦版）")

    # 1. 初始化消息总线（Redis Pub/Sub + 内存回退）
    bus = MessageBus(redis_url=settings.REDIS_URL)
    await bus.connect()
    APP_STATE["bus"] = bus

    # 2. 创建数据库会话（每个模块独立持有，便于后续拆进程）
    db = AsyncSessionLocal()
    APP_STATE["db"] = db

    # 3. 初始化四个模块
    fuel_cfg = load_fuel_config()
    receiver = ModbusReceiver(db, bus, default_fuel_type=settings.DEFAULT_FUEL_TYPE)
    cfd = CFDSimulator(db, bus)
    aq = AirQualityAnalyzer(db, bus)
    alarm = AlarmMQTTService(db, bus)

    APP_STATE["modbus_receiver"] = receiver
    APP_STATE["cfd_simulator"] = cfd
    APP_STATE["air_quality_analyzer"] = aq
    APP_STATE["alarm_mqtt"] = alarm

    # 4. 绑定总线订阅（发布订阅关系：receiver -> cfd -> aq -> alarm）
    await cfd.bind_to_bus()
    await aq.bind_to_bus()
    await alarm.bind_to_bus()

    # 5. 连接 MQTT（用于外部告警与传感器广播）
    if settings.MQTT_HOST:
        await alarm.connect_mqtt(
            host=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            topic_prefix=settings.MQTT_TOPIC_PREFIX,
        )

    # 6. 提供给路由层使用
    app.state.bus = bus
    app.state.modbus_receiver = receiver
    app.state.cfd_simulator = cfd
    app.state.air_quality_analyzer = aq
    app.state.alarm_mqtt = alarm
    app.state.fuel_types = fuel_cfg["fuel_types"]
    app.state.modbus_to_fuel = fuel_cfg["modbus_mapping"]

    logger.info(
        "模块加载完成: modbus_receiver, cfd_simulator, air_quality_analyzer, alarm_mqtt"
    )
    yield

    # ---------- 清理 ----------
    logger.info("正在关闭服务...")
    await alarm.disconnect_mqtt()
    try:
        await db.close()
    except Exception:
        pass
    await bus.close()
    logger.info("服务已停止")


app = FastAPI(
    title=settings.APP_NAME,
    description="汉代长信宫灯烟道流体仿真与室内空气质量分析系统（微服务解耦版）",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=500,
    compresslevel=6,
)

app.include_router(sensor_router)

frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    async def read_index():
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": settings.APP_NAME}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "architecture": "modbus_receiver -> cfd_simulator -> air_quality_analyzer -> alarm_mqtt",
        "bus": "redis_pubsub (in-memory fallback)",
        "configs": ["fuel_types.json", "cfd_parameters.json", "air_quality_parameters.json"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8090,
        reload=False,
    )
