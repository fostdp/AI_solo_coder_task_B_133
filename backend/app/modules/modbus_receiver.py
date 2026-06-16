"""
modbus_receiver 模块：传感器数据采集和校验

职责：
  1. 接收 HTTP/Modbus 上报的传感器原始数据
  2. 执行数据完整性校验、物理合理性校验
  3. 将校验后的数据持久化到 sensor_data 超表
  4. 向消息总线发布两条消息：
     - SENSOR_RAW: 完整校验过的原始数据
     - CFD_INPUT: 提供给 CFD 模块的最小必要字段
     - SENSOR_MQTT_BROADCAST: 直接转发给 MQTT 广播

订阅：无
发布：SENSOR_RAW, CFD_INPUT, SENSOR_MQTT_BROADCAST
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from ..bus import MessageBus, SENSOR_RAW, CFD_INPUT, SENSOR_MQTT_BROADCAST
from ..models.lamp import SensorData, Lamp
from ..schemas.sensor import SensorDataCreate
from ..config_loader import load_fuel_config

logger = logging.getLogger(__name__)


class ModbusReceiver:
    def __init__(self, db: AsyncSession, bus: MessageBus, default_fuel_type: str = "animal_fat"):
        self.db = db
        self.bus = bus
        self.default_fuel_type = default_fuel_type
        self._fuel_cfg = load_fuel_config()
        self._fuel_names = set(self._fuel_cfg["fuel_types"].keys())
        self._modbus_map = self._fuel_cfg["modbus_mapping"]

    # ------------------------------------------------------------------
    # 校验层
    # ------------------------------------------------------------------
    def validate_sensor_payload(self, payload: SensorDataCreate) -> Tuple[bool, Dict[str, str], Dict[str, Any]]:
        """
        返回 (是否通过, 错误字段 -> 原因, 修正/补全后的字段字典)
        """
        errors: Dict[str, str] = {}
        fixed: Dict[str, Any] = payload.model_dump()

        # 1. 物理范围校验
        checks = [
            ("oil_consumption", lambda v: 0.0 <= v <= 20.0, "油耗 0~20 g/min"),
            ("flue_temperature", lambda v: 10.0 <= v <= 400.0, "烟温 10~400 °C"),
            ("flue_velocity", lambda v: 0.001 <= v <= 10.0, "流速 0.001~10 m/s"),
            ("indoor_pm25", lambda v: 0.0 <= v <= 1000.0, "PM2.5 0~1000 μg/m³"),
            ("oil_level", lambda v: 0.0 <= v <= 1000.0, "油量 0~1000 mL"),
            ("ambient_temperature", lambda v: -10.0 <= v <= 50.0, "室温 -10~50 °C"),
            ("ambient_humidity", lambda v: 0.0 <= v <= 100.0, "湿度 0~100 %"),
        ]
        for field, pred, rule in checks:
            val = fixed.get(field)
            if val is None or not pred(val):
                errors[field] = f"超出物理范围 [{rule}]，收到={val}"

        # 2. 燃料类型校验与补全
        ft = fixed.get("fuel_type")
        if ft is None:
            fixed["fuel_type"] = self.default_fuel_type
        elif ft not in self._fuel_names:
            errors["fuel_type"] = f"未知燃料类型: {ft}"
            fixed["fuel_type"] = self.default_fuel_type

        # 3. 通风参数校验与补全
        if fixed.get("air_change_rate") is None:
            fixed["air_change_rate"] = 1.0
        elif not (0 <= fixed["air_change_rate"] <= 20):
            errors["air_change_rate"] = "ACH 超出 0~20 范围"

        if fixed.get("outdoor_pm25") is None:
            fixed["outdoor_pm25"] = 25.0
        elif not (0 <= fixed["outdoor_pm25"] <= 500):
            errors["outdoor_pm25"] = "室外PM2.5 超出 0~500 范围"

        # 4. 合理性联动：烟温 > 室温 + 5
        if (
            not errors.get("flue_temperature")
            and not errors.get("ambient_temperature")
        ):
            if fixed["flue_temperature"] <= fixed["ambient_temperature"] + 3:
                errors["flue_temperature_vs_ambient"] = (
                    f"烟温({fixed['flue_temperature']})与室温差过小"
                )

        return (len(errors) == 0, errors, fixed)

    # ------------------------------------------------------------------
    # 主处理流程（供路由调用）
    # ------------------------------------------------------------------
    async def ingest(self, payload: SensorDataCreate, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now()
        ok, errors, fixed = self.validate_sensor_payload(payload)
        if not ok:
            logger.warning(f"[modbus_receiver] 数据校验不通过 lamp_id={payload.lamp_id}: {errors}")

        # 持久化（即使校验不通过，也保留原始数据供排查；持久化失败不阻断消息管线）
        try:
            stmt = insert(SensorData).values(
                time=now,
                lamp_id=payload.lamp_id,
                oil_consumption=payload.oil_consumption,
                flue_temperature=payload.flue_temperature,
                flue_velocity=payload.flue_velocity,
                indoor_pm25=payload.indoor_pm25,
                oil_level=payload.oil_level,
                ambient_temperature=payload.ambient_temperature,
                ambient_humidity=payload.ambient_humidity,
                blockage_degree=fixed.get("blockage_degree", 0.0),
            )
            await self.db.execute(stmt)
            await self.db.commit()
        except Exception as db_e:
            logger.warning(f"[modbus_receiver] 持久化失败 (DB未就绪？): {db_e}")

        full_payload = {
            **fixed,
            "time": now.isoformat(),
            "timestamp": int(now.timestamp()),
            "validation": {
                "passed": ok,
                "errors": errors,
            },
        }

        # 发布三条消息
        await self.bus.publish(SENSOR_RAW, full_payload)
        await self.bus.publish(CFD_INPUT, self._build_cfd_message(full_payload))
        await self.bus.publish(SENSOR_MQTT_BROADCAST, self._build_mqtt_message(full_payload))

        return {
            "status": "accepted" if ok else "accepted_with_validation_errors",
            "validation": full_payload["validation"],
            "payload_summary": {
                "lamp_id": full_payload["lamp_id"],
                "fuel_type": full_payload["fuel_type"],
                "flue_temperature": full_payload["flue_temperature"],
                "flue_velocity": full_payload["flue_velocity"],
                "indoor_pm25": full_payload["indoor_pm25"],
                "air_change_rate": full_payload["air_change_rate"],
            },
        }

    # ------------------------------------------------------------------
    # 消息构造辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _build_cfd_message(full: Dict[str, Any]) -> Dict[str, Any]:
        """CFD 模块最小字段集合"""
        return {
            "correlation_id": full.get("timestamp"),
            "lamp_id": full["lamp_id"],
            "time": full["time"],
            "flue_temperature": full["flue_temperature"],
            "flue_velocity": full["flue_velocity"],
            "oil_consumption": full.get("oil_consumption", 0.0),
            "ambient_temperature": full.get("ambient_temperature", 22.0),
            "ambient_humidity": full.get("ambient_humidity", 50.0),
            "fuel_type": full["fuel_type"],
            "indoor_pm25": full["indoor_pm25"],
            "oil_level": full.get("oil_level", 0.0),
        }

    @staticmethod
    def _build_mqtt_message(full: Dict[str, Any]) -> Dict[str, Any]:
        """MQTT 广播最小字段集合"""
        return {
            "lamp_id": full["lamp_id"],
            "time": full["time"],
            "oil_consumption": full.get("oil_consumption"),
            "flue_temperature": full["flue_temperature"],
            "flue_velocity": full["flue_velocity"],
            "indoor_pm25": full["indoor_pm25"],
            "oil_level": full.get("oil_level"),
            "ambient_temperature": full.get("ambient_temperature"),
            "ambient_humidity": full.get("ambient_humidity"),
            "fuel_type": full.get("fuel_type"),
        }
