import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, and_
import paho.mqtt.client as mqtt

from ..models.lamp import Alert
from ..config import settings

logger = logging.getLogger(__name__)


class AlertService:
    """告警服务 - 检测异常并通过MQTT推送"""

    ALERT_FLUE_BLOCKAGE = "FLUE_BLOCKAGE"
    ALERT_PM25_EXCEEDED = "PM25_EXCEEDED"
    ALERT_TEMPERATURE_HIGH = "TEMPERATURE_HIGH"

    SEVERITY_WARNING = "WARNING"
    SEVERITY_CRITICAL = "CRITICAL"

    def __init__(self):
        self.mqtt_client: Optional[mqtt.Client] = None
        self._recent_alerts: Dict[str, datetime] = {}
        self._alert_cooldown = 300

    def connect_mqtt(self):
        try:
            self.mqtt_client = mqtt.Client(
                client_id=f"gongdeng_alert_{datetime.now().timestamp()}",
                protocol=mqtt.MQTTv5
            )
            if settings.MQTT_USERNAME and settings.MQTT_PASSWORD:
                self.mqtt_client.username_pw_set(
                    settings.MQTT_USERNAME,
                    settings.MQTT_PASSWORD
                )
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            self.mqtt_client.connect_async(
                settings.MQTT_BROKER,
                settings.MQTT_PORT,
                keepalive=60
            )
            self.mqtt_client.loop_start()
            logger.info(f"MQTT客户端已启动，连接到 {settings.MQTT_BROKER}:{settings.MQTT_PORT}")
        except Exception as e:
            logger.warning(f"MQTT连接失败（将继续运行无MQTT推送）: {e}")
            self.mqtt_client = None

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("MQTT连接成功")
        else:
            logger.warning(f"MQTT连接失败，返回码: {rc}")

    def _on_mqtt_disconnect(self, client, userdata, rc, properties=None):
        if rc != 0:
            logger.warning(f"MQTT意外断开，返回码: {rc}")

    def _is_alert_cooled_down(self, alert_key: str) -> bool:
        if alert_key in self._recent_alerts:
            elapsed = (datetime.now() - self._recent_alerts[alert_key]).total_seconds()
            return elapsed >= self._alert_cooldown
        return True

    async def check_and_create_alerts(
        self,
        db: AsyncSession,
        lamp_id: int,
        flue_velocity: float,
        flue_temperature: float,
        indoor_pm25: float
    ) -> List[Dict]:
        created_alerts = []

        if flue_velocity < settings.FLUE_VELOCITY_MIN:
            alert = await self._create_alert(
                db=db,
                lamp_id=lamp_id,
                alert_type=self.ALERT_FLUE_BLOCKAGE,
                severity=self.SEVERITY_WARNING if flue_velocity > 0.05 else self.SEVERITY_CRITICAL,
                message=f"烟道疑似堵塞，烟气流速过低: {flue_velocity:.3f}m/s (阈值: {settings.FLUE_VELOCITY_MIN}m/s)",
                threshold_value=settings.FLUE_VELOCITY_MIN,
                actual_value=flue_velocity
            )
            if alert:
                created_alerts.append(alert)

        if indoor_pm25 >= settings.PM25_THRESHOLD_CRITICAL:
            alert = await self._create_alert(
                db=db,
                lamp_id=lamp_id,
                alert_type=self.ALERT_PM25_EXCEEDED,
                severity=self.SEVERITY_CRITICAL,
                message=f"PM2.5严重超标: {indoor_pm25:.1f}μg/m³ (阈值: {settings.PM25_THRESHOLD_CRITICAL}μg/m³)",
                threshold_value=settings.PM25_THRESHOLD_CRITICAL,
                actual_value=indoor_pm25
            )
            if alert:
                created_alerts.append(alert)
        elif indoor_pm25 >= settings.PM25_THRESHOLD_WARNING:
            alert = await self._create_alert(
                db=db,
                lamp_id=lamp_id,
                alert_type=self.ALERT_PM25_EXCEEDED,
                severity=self.SEVERITY_WARNING,
                message=f"PM2.5超标警告: {indoor_pm25:.1f}μg/m³ (阈值: {settings.PM25_THRESHOLD_WARNING}μg/m³)",
                threshold_value=settings.PM25_THRESHOLD_WARNING,
                actual_value=indoor_pm25
            )
            if alert:
                created_alerts.append(alert)

        if flue_temperature >= settings.FLUE_TEMPERATURE_MAX:
            alert = await self._create_alert(
                db=db,
                lamp_id=lamp_id,
                alert_type=self.ALERT_TEMPERATURE_HIGH,
                severity=self.SEVERITY_CRITICAL if flue_temperature > 250 else self.SEVERITY_WARNING,
                message=f"烟道温度过高: {flue_temperature:.1f}°C (阈值: {settings.FLUE_TEMPERATURE_MAX}°C)",
                threshold_value=settings.FLUE_TEMPERATURE_MAX,
                actual_value=flue_temperature
            )
            if alert:
                created_alerts.append(alert)

        return created_alerts

    async def _create_alert(
        self,
        db: AsyncSession,
        lamp_id: int,
        alert_type: str,
        severity: str,
        message: str,
        threshold_value: float,
        actual_value: float
    ) -> Optional[Dict]:
        alert_key = f"{lamp_id}_{alert_type}_{severity}"

        if not self._is_alert_cooled_down(alert_key):
            return None

        now = datetime.now()
        self._recent_alerts[alert_key] = now

        try:
            stmt = insert(Alert).values(
                time=now,
                lamp_id=lamp_id,
                alert_type=alert_type,
                severity=severity,
                message=message,
                threshold_value=threshold_value,
                actual_value=actual_value,
                resolved=False
            )
            result = await db.execute(stmt)
            await db.commit()

            alert_id = result.inserted_primary_key[0] if result.inserted_primary_key else None

            alert_data = {
                "alert_id": alert_id,
                "time": now.isoformat(),
                "lamp_id": lamp_id,
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                "threshold_value": threshold_value,
                actual_value: actual_value
            }

            self._publish_mqtt_alert(alert_data)

            logger.warning(f"告警已创建: [{severity}] {alert_type} - {message}")

            return alert_data

        except Exception as e:
            logger.error(f"创建告警失败: {e}")
            await db.rollback()
            return None

    def _publish_mqtt_alert(self, alert_data: Dict):
        if not self.mqtt_client:
            return

        try:
            topic = settings.MQTT_TOPIC_ALERT
            payload = json.dumps(alert_data, ensure_ascii=False)
            result = self.mqtt_client.publish(
                topic,
                payload,
                qos=1,
                retain=False
            )
            if result.rc != 0:
                logger.warning(f"MQTT消息发布失败，返回码: {result.rc}")
            else:
                logger.info(f"MQTT告警已推送到主题 {topic}")
        except Exception as e:
            logger.error(f"MQTT推送失败: {e}")

    def publish_sensor_data(self, sensor_data: Dict):
        if not self.mqtt_client:
            return

        try:
            topic = settings.MQTT_TOPIC_DATA
            payload = json.dumps(sensor_data, ensure_ascii=False, default=str)
            self.mqtt_client.publish(topic, payload, qos=0)
        except Exception as e:
            logger.error(f"MQTT传感器数据推送失败: {e}")

    async def get_active_alerts(self, db: AsyncSession, lamp_id: Optional[int] = None) -> List[Alert]:
        query = select(Alert).where(Alert.resolved == False)
        if lamp_id:
            query = query.where(Alert.lamp_id == lamp_id)
        query = query.order_by(Alert.time.desc()).limit(50)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def resolve_alert(self, db: AsyncSession, alert_id: int) -> bool:
        query = select(Alert).where(Alert.alert_id == alert_id)
        result = await db.execute(query)
        alert = result.scalar_one_or_none()

        if not alert:
            return False

        alert.resolved = True
        alert.resolved_at = datetime.now()
        await db.commit()

        logger.info(f"告警已解决: alert_id={alert_id}")
        return True

    async def get_alert_history(
        self,
        db: AsyncSession,
        lamp_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Alert]:
        query = select(Alert)
        conditions = []

        if lamp_id:
            conditions.append(Alert.lamp_id == lamp_id)
        if start_time:
            conditions.append(Alert.time >= start_time)
        if end_time:
            conditions.append(Alert.time <= end_time)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Alert.time.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    def disconnect(self):
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.info("MQTT客户端已断开")


alert_service = AlertService()
