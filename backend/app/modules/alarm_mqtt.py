"""
alarm_mqtt 模块：告警评估与 MQTT 推送

职责：
  1. 订阅两条通道：
     - AIR_QUALITY_RESULT: 包含 PM2.5 / CFD / 传感器完整数据
     - SENSOR_MQTT_BROADCAST: 原始传感器数据（直接转发给外部 MQTT broker）
  2. 执行三类告警检测：烟道堵塞、PM2.5超标、温度过高
  3. 告警持久化 alerts 表，5分钟冷却去重
  4. 通过 MQTT 推送告警与原始传感器数据

订阅：AIR_QUALITY_RESULT, SENSOR_MQTT_BROADCAST
发布：ALERT_PUBLISHED
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select

from ..bus import (
    MessageBus,
    AIR_QUALITY_RESULT,
    SENSOR_MQTT_BROADCAST,
    ALERT_PUBLISHED,
)
from ..models.lamp import Alert
from ..config_loader import load_air_quality_config

logger = logging.getLogger(__name__)

ALERT_BLOCKAGE = "FLUE_BLOCKAGE"
ALERT_PM25 = "PM25_EXCEEDED"
ALERT_TEMP = "TEMPERATURE_HIGH"
SEVERITY_WARN = "WARNING"
SEVERITY_CRIT = "CRITICAL"


class AlarmMQTTService:
    def __init__(self, db: AsyncSession, bus: MessageBus):
        self.db = db
        self.bus = bus
        thresholds = load_air_quality_config()["alert_thresholds"]
        self.pm25_warn = thresholds["pm25_warning_ugm3"]
        self.pm25_crit = thresholds["pm25_critical_ugm3"]
        self.vel_warn = thresholds["flue_velocity_warning_ms"]
        self.vel_crit = thresholds["flue_velocity_critical_ms"]
        self.temp_warn = thresholds["flue_temperature_warning_c"]
        self.temp_crit = thresholds["flue_temperature_critical_c"]

        self._recent_alerts: Dict[Tuple[int, str, str], float] = {}
        self._alert_cooldown_seconds = 300

        self._mqtt_client = None
        self._mqtt_connected = False
        self._bus_bound = False

    # ------------------------------------------------------------------
    # 总线 & MQTT 连接
    # ------------------------------------------------------------------
    async def bind_to_bus(self):
        if self._bus_bound:
            return
        await self.bus.subscribe(AIR_QUALITY_RESULT, self._on_air_quality_result)
        await self.bus.subscribe(SENSOR_MQTT_BROADCAST, self._on_sensor_broadcast)
        self._bus_bound = True

    async def connect_mqtt(self, host: str, port: int = 1883,
                           username: Optional[str] = None,
                           password: Optional[str] = None,
                           topic_prefix: str = "gongdeng") -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("[alarm_mqtt] paho-mqtt 未安装，MQTT推送不可用")
            return
        try:
            self._mqtt_client = mqtt.Client(
                client_id=f"gongdeng_alarm_{int(time.time())}",
                protocol=mqtt.MQTTv311,
            )
            if username:
                self._mqtt_client.username_pw_set(username, password)
            self._mqtt_client.connect_async(host, port)
            self._mqtt_client.loop_start()
            self._mqtt_topic_prefix = topic_prefix
            self._mqtt_connected = True
            logger.info(f"[alarm_mqtt] MQTT已连接 {host}:{port}")
        except Exception as e:
            logger.error(f"[alarm_mqtt] MQTT连接失败: {e}")
            self._mqtt_connected = False

    async def disconnect_mqtt(self):
        if self._mqtt_client and self._mqtt_connected:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
            self._mqtt_connected = False

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------
    async def _on_sensor_broadcast(self, payload: Dict[str, Any]):
        """直接转发传感器广播到 MQTT"""
        try:
            self._publish_mqtt_sensor(payload)
        except Exception as e:
            logger.exception(f"[alarm_mqtt] 传感器MQTT转发失败: {e}")

    async def _on_air_quality_result(self, payload: Dict[str, Any]):
        """评估告警并持久化 + 推送"""
        lamp_id = payload.get("lamp_id", 0)
        flue_velocity = payload.get("flue_velocity", 0)
        indoor_pm25 = payload.get("indoor_pm25", 0)
        flue_temperature = payload.get("flue_temperature", 0)

        alerts = self.check_alerts(lamp_id, flue_velocity, indoor_pm25, flue_temperature)
        saved_alerts = []
        try:
            t_str = payload.get("time", datetime.now().isoformat())
            t = datetime.fromisoformat(t_str) if isinstance(t_str, str) else t_str
            for alert_type, severity, message in alerts:
                if not self._is_alert_cooled_down(lamp_id, alert_type, severity):
                    continue
                try:
                    stmt = insert(Alert).values(
                        time=t,
                        lamp_id=lamp_id,
                        alert_type=alert_type,
                        severity=severity,
                        message=message,
                        resolved=False,
                    )
                    await self.db.execute(stmt)
                except Exception as db_e:
                    logger.warning(f"[alarm_mqtt] 告警入库失败 (DB未就绪？): {db_e}")
                alert_record = {
                    "lamp_id": lamp_id,
                    "time": t_str,
                    "alert_type": alert_type,
                    "severity": severity,
                    "message": message,
                }
                saved_alerts.append(alert_record)
                self._record_recent_alert(lamp_id, alert_type, severity)
                self._publish_mqtt_alert(alert_record)
            if saved_alerts:
                try:
                    await self.db.commit()
                except Exception as db_e:
                    logger.warning(f"[alarm_mqtt] 告警提交失败 (DB未就绪？): {db_e}")
                out = {
                    "correlation_id": payload.get("correlation_id"),
                    "lamp_id": lamp_id,
                    "time": t_str,
                    "alerts": saved_alerts,
                }
                await self.bus.publish(ALERT_PUBLISHED, out)
                for a in saved_alerts:
                    logger.warning(
                        f"[alarm_mqtt] lamp#{lamp_id} {a['alert_type']}/{a['severity']}: {a['message']}"
                    )
        except Exception as e:
            logger.exception(f"[alarm_mqtt] 告警处理失败: {e}")
            await self.db.rollback()

    # ------------------------------------------------------------------
    # 告警评估
    # ------------------------------------------------------------------
    def check_alerts(
        self,
        lamp_id: int,
        flue_velocity: float,
        indoor_pm25: float,
        flue_temperature: float,
    ) -> List[Tuple[str, str, str]]:
        alerts: List[Tuple[str, str, str]] = []
        if flue_velocity < self.vel_warn:
            severity = SEVERITY_CRIT if flue_velocity < self.vel_crit else SEVERITY_WARN
            alerts.append((
                ALERT_BLOCKAGE,
                severity,
                f"烟道流速过低 v={flue_velocity:.3f} m/s，疑似烟道堵塞",
            ))
        if indoor_pm25 >= self.pm25_warn:
            severity = SEVERITY_CRIT if indoor_pm25 >= self.pm25_crit else SEVERITY_WARN
            alerts.append((
                ALERT_PM25,
                severity,
                f"PM2.5超标 C={indoor_pm25:.1f} μg/m³",
            ))
        if flue_temperature >= self.temp_warn:
            severity = SEVERITY_CRIT if flue_temperature >= self.temp_crit else SEVERITY_WARN
            alerts.append((
                ALERT_TEMP,
                severity,
                f"烟道温度过高 T={flue_temperature:.1f} °C",
            ))
        return alerts

    def _is_alert_cooled_down(self, lamp_id: int, atype: str, severity: str) -> bool:
        key = (lamp_id, atype, severity)
        last = self._recent_alerts.get(key, 0)
        return (time.time() - last) >= self._alert_cooldown_seconds

    def _record_recent_alert(self, lamp_id: int, atype: str, severity: str):
        self._recent_alerts[(lamp_id, atype, severity)] = time.time()

    # ------------------------------------------------------------------
    # MQTT 推送
    # ------------------------------------------------------------------
    def _publish_mqtt_alert(self, alert: Dict[str, Any]) -> None:
        if not (self._mqtt_connected and self._mqtt_client):
            return
        try:
            topic = f"{self._mqtt_topic_prefix}/alerts"
            payload = json.dumps(alert, ensure_ascii=False, default=str)
            self._mqtt_client.publish(topic, payload, qos=1)
        except Exception as e:
            logger.error(f"[alarm_mqtt] 告警MQTT推送失败: {e}")

    def _publish_mqtt_sensor(self, payload: Dict[str, Any]) -> None:
        if not (self._mqtt_connected and self._mqtt_client):
            return
        try:
            topic = f"{self._mqtt_topic_prefix}/sensor"
            data = json.dumps(payload, ensure_ascii=False, default=str)
            self._mqtt_client.publish(topic, data, qos=0)
        except Exception as e:
            logger.error(f"[alarm_mqtt] 传感器MQTT推送失败: {e}")
