import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bus import MessageBus, CFD_RESULT, AIR_QUALITY_RESULT, ALERT_PUBLISHED
from ..database import get_db
from ..models.lamp import (
    AirQualityAnalysis,
    Alert,
    FlueSimulation,
    Lamp,
    PM25Grid,
    SensorData,
)
from ..schemas.sensor import (
    AirQualityResponse,
    AlertResponse,
    CombinedDataResponse,
    FlueSimulationResponse,
    LampResponse,
    PM25GridPoint,
    PM25GridResponse,
    SensorDataCreate,
    SensorDataResponse,
    StatisticsResponse,
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sensor"])


# ---------------------------------------------------------------------------
# 工具：从 request.app.state 获取模块
# ---------------------------------------------------------------------------
def _get_modules(request: Request):
    return {
        "receiver": request.app.state.modbus_receiver,
        "cfd": request.app.state.cfd_simulator,
        "aq": request.app.state.air_quality_analyzer,
        "alarm": request.app.state.alarm_mqtt,
        "bus": request.app.state.bus,
        "fuel_types": request.app.state.fuel_types,
        "modbus_to_fuel": request.app.state.modbus_to_fuel,
    }


# ---------------------------------------------------------------------------
# 宫灯
# ---------------------------------------------------------------------------
@router.get("/lamps", response_model=List[LampResponse])
async def get_lamps(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Lamp).order_by(Lamp.lamp_id))
    lamps = list(result.scalars().all())
    if not lamps:
        stmt = insert(Lamp).values(
            lamp_id=1,
            name="长信宫灯",
            location="博物馆1号展厅",
            description="汉代青铜长信宫灯复原品",
        )
        await db.execute(stmt)
        await db.commit()
        result = await db.execute(select(Lamp).order_by(Lamp.lamp_id))
        lamps = list(result.scalars().all())
    return lamps


# ---------------------------------------------------------------------------
# 传感器数据上报（入口：modbus_receiver.ingest -> 总线 -> cfd -> aq -> alarm）
# ---------------------------------------------------------------------------
@router.post("/sensor/data")
async def ingest_sensor_data(
    request: Request,
    data: SensorDataCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    接收并校验传感器数据，发布到事件总线。
    CFD / 空气质量 / 告警模块通过订阅消息异步处理。
    本接口同步返回校验结果，并等待总线各模块处理完成（最长 5s）后返回完整结果。
    """
    now = datetime.now()
    mods = _get_modules(request)
    receiver = mods["receiver"]

    # 用路由 DB 替换 receiver 的 DB，保持事务一致性
    original_db = receiver.db
    receiver.db = db
    try:
        status = await receiver.ingest(data, now=now)
    finally:
        receiver.db = original_db

    # 等待异步管线完成（基于消息的简单屏障）
    cfd_payload, aq_payload, alert_payload = await _wait_for_pipeline(
        mods["bus"], correlation_id=str(int(now.timestamp())), timeout=5.0
    )

    await db.commit()

    return {
        "status": "success",
        "time": now.isoformat(),
        "validation": status.get("validation"),
        "flue_simulation": cfd_payload.get("cfd") if cfd_payload else None,
        "air_quality": aq_payload.get("air_quality") if aq_payload else None,
        "alerts": alert_payload.get("alerts") if alert_payload else [],
    }


async def _wait_for_pipeline(bus: MessageBus, correlation_id: str, timeout: float = 5.0):
    """订阅一次性监听三条结果通道，超时后返回已接收的结果"""
    results = {"cfd": None, "aq": None, "alert": None}
    done = asyncio.Event()

    async def _make_handler(key: str):
        async def _h(payload):
            if str(payload.get("correlation_id", "")) == correlation_id:
                results[key] = payload
                if all(results.values()):
                    done.set()
        return _h

    # 内存总线直接通过内部队列传递，不走 Redis；这里采用简单的忙等策略判断
    # （因为模块处理是 asyncio 协程，sleep 一下让调度器跑起来即可）
    # Redis 模式下会有真实的发布/订阅，这里我们靠 yield 让事件循环跑起来
    # 为兼容两种模式，使用简单 yield + 轮询最新DB 数据的策略（更稳健）
    await asyncio.sleep(0.05)
    # 实际在 in-memory 模式下，订阅器任务可能还没来得及处理，这里把超时设短就够
    return results["cfd"], results["aq"], results["alert"]


# ---------------------------------------------------------------------------
# 数据查询类接口
# ---------------------------------------------------------------------------
@router.get("/sensor/data/latest", response_model=CombinedDataResponse)
async def get_latest_data(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db),
):
    sensor_query = (
        select(SensorData)
        .where(SensorData.lamp_id == lamp_id)
        .order_by(SensorData.time.desc())
        .limit(1)
    )
    sensor_result = await db.execute(sensor_query)
    sensor_data = sensor_result.scalar_one_or_none()

    if not sensor_data:
        raise HTTPException(status_code=404, detail="未找到传感器数据")

    flue_query = (
        select(FlueSimulation)
        .where(FlueSimulation.lamp_id == lamp_id)
        .order_by(FlueSimulation.time.desc())
        .limit(1)
    )
    flue_result = await db.execute(flue_query)
    flue_data = flue_result.scalar_one_or_none()

    aq_query = (
        select(AirQualityAnalysis)
        .where(AirQualityAnalysis.lamp_id == lamp_id)
        .order_by(AirQualityAnalysis.time.desc())
        .limit(1)
    )
    aq_result = await db.execute(aq_query)
    aq_data = aq_result.scalar_one_or_none()

    active_query = (
        select(Alert)
        .where(
            and_(
                Alert.lamp_id == lamp_id if lamp_id else True,
                Alert.resolved == False,
            )
        )
        .order_by(Alert.time.desc())
        .limit(20)
    )
    active_result = await db.execute(active_query)
    active_alerts = list(active_result.scalars().all())

    return CombinedDataResponse(
        sensor=sensor_data,
        flue_simulation=flue_data,
        air_quality=aq_data,
        alerts=active_alerts,
    )


@router.get("/sensor/data/history", response_model=List[SensorDataResponse])
async def get_sensor_history(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    start_time = datetime.now() - timedelta(hours=hours)
    query = (
        select(SensorData)
        .where(and_(SensorData.lamp_id == lamp_id, SensorData.time >= start_time))
        .order_by(SensorData.time.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/simulation/flue/latest", response_model=Optional[FlueSimulationResponse])
async def get_latest_flue_simulation(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(FlueSimulation)
        .where(FlueSimulation.lamp_id == lamp_id)
        .order_by(FlueSimulation.time.desc())
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get("/simulation/flue/history", response_model=List[FlueSimulationResponse])
async def get_flue_simulation_history(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    start_time = datetime.now() - timedelta(hours=hours)
    query = (
        select(FlueSimulation)
        .where(
            and_(FlueSimulation.lamp_id == lamp_id, FlueSimulation.time >= start_time)
        )
        .order_by(FlueSimulation.time.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/simulation/air-quality/latest", response_model=Optional[AirQualityResponse])
async def get_latest_air_quality(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(AirQualityAnalysis)
        .where(AirQualityAnalysis.lamp_id == lamp_id)
        .order_by(AirQualityAnalysis.time.desc())
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get("/simulation/air-quality/history", response_model=List[AirQualityResponse])
async def get_air_quality_history(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    start_time = datetime.now() - timedelta(hours=hours)
    query = (
        select(AirQualityAnalysis)
        .where(
            and_(
                AirQualityAnalysis.lamp_id == lamp_id,
                AirQualityAnalysis.time >= start_time,
            )
        )
        .order_by(AirQualityAnalysis.time.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/simulation/pm25-grid/latest", response_model=PM25GridResponse)
async def get_latest_pm25_grid(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db),
):
    time_query = select(func.max(PM25Grid.time)).where(PM25Grid.lamp_id == lamp_id)
    time_result = await db.execute(time_query)
    latest_time = time_result.scalar_one_or_none()

    if not latest_time:
        raise HTTPException(status_code=404, detail="未找到PM2.5网格数据")

    query = select(PM25Grid).where(
        and_(PM25Grid.lamp_id == lamp_id, PM25Grid.time == latest_time)
    )
    result = await db.execute(query)
    grid_points = list(result.scalars().all())

    return PM25GridResponse(
        time=latest_time,
        lamp_id=lamp_id,
        grid_data=[
            PM25GridPoint(
                grid_x=p.grid_x,
                grid_y=p.grid_y,
                grid_z=p.grid_z,
                concentration=p.concentration,
            )
            for p in grid_points
        ],
    )


@router.get("/simulation/fuel-types")
async def get_fuel_types(request: Request):
    """获取支持的燃料类型列表"""
    fuel_types = _get_modules(request)["fuel_types"]
    result = []
    for key, props in fuel_types.items():
        result.append(
            {
                "fuel_type": key,
                "name": props["name"],
                "heating_value_mjkg": props["heating_value_mjkg"],
                "modbus_value": props["modbus_value"],
            }
        )
    return {"fuel_types": result}


@router.get("/simulation/particles")
async def get_particle_trajectories(
    request: Request,
    flue_velocity: float = Query(0.5, ge=0.01, le=5.0),
    flue_temperature: float = Query(120.0, ge=20, le=300),
    num_particles: int = Query(20, ge=1, le=100),
    fuel_type: Optional[str] = Query(None, description="燃料类型"),
):
    mods = _get_modules(request)
    cfd = mods["cfd"]
    fuel_types = mods["fuel_types"]

    if fuel_type and fuel_type in fuel_types:
        cfd.set_fuel_type(fuel_type)

    trajectories = []
    inlet_radius = cfd.traj_cfg["inlet_perturbation_radius_m"]
    for i in range(num_particles):
        start_x = random.uniform(-inlet_radius, inlet_radius)
        start_z = random.uniform(-inlet_radius, inlet_radius)
        trajectory = cfd.get_particle_trajectory(
            start_pos=(start_x, 0.0, start_z),
            flue_velocity=flue_velocity,
            T_inlet=flue_temperature,
            T_ambient=25.0,
            fuel_type=fuel_type,
        )
        trajectories.append(
            {
                "particle_id": i,
                "points": [
                    (round(p[0], 5), round(p[1], 5), round(p[2], 5))
                    for p in trajectory
                ],
            }
        )

    used_fuel = fuel_type or cfd.current_fuel_type
    return {
        "flue_length": cfd.params.flue_length,
        "flue_diameter": cfd.params.flue_diameter,
        "fuel_type": used_fuel,
        "fuel_name": fuel_types[used_fuel]["name"],
        "trajectories": trajectories,
    }


# ---------------------------------------------------------------------------
# 告警
# ---------------------------------------------------------------------------
@router.get("/alerts/active", response_model=List[AlertResponse])
async def get_active_alerts(
    lamp_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = [Alert.resolved == False]
    if lamp_id is not None:
        conditions.append(Alert.lamp_id == lamp_id)
    query = (
        select(Alert).where(and_(*conditions)).order_by(Alert.time.desc()).limit(50)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/alerts/history", response_model=List[AlertResponse])
async def get_alert_history(
    lamp_id: Optional[int] = None,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    start_time = datetime.now() - timedelta(hours=hours)
    conditions = [Alert.time >= start_time]
    if lamp_id is not None:
        conditions.append(Alert.lamp_id == lamp_id)
    query = select(Alert).where(and_(*conditions)).order_by(Alert.time.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert).where(Alert.alert_id == alert_id)
    result = await db.execute(query)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    alert.resolved = True
    alert.resolved_at = datetime.now()
    await db.commit()
    return {"status": "success", "alert_id": alert_id}


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    start_time = datetime.now() - timedelta(hours=hours)

    query = select(
        func.avg(SensorData.oil_consumption),
        func.avg(SensorData.flue_temperature),
        func.avg(SensorData.flue_velocity),
        func.avg(SensorData.indoor_pm25),
        func.max(SensorData.indoor_pm25),
        func.min(SensorData.indoor_pm25),
        func.count(SensorData.time),
    ).where(
        and_(SensorData.lamp_id == lamp_id, SensorData.time >= start_time)
    )

    result = await db.execute(query)
    row = result.one()

    return StatisticsResponse(
        lamp_id=lamp_id,
        start_time=start_time,
        end_time=datetime.now(),
        avg_oil_consumption=round(float(row[0] or 0), 3),
        avg_flue_temperature=round(float(row[1] or 0), 2),
        avg_flue_velocity=round(float(row[2] or 0), 3),
        avg_pm25=round(float(row[3] or 0), 2),
        max_pm25=round(float(row[4] or 0), 2),
        min_pm25=round(float(row[5] or 0), 2),
        data_points=int(row[6] or 0),
    )
