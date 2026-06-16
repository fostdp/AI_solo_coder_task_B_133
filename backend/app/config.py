from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "长信宫灯烟道流体仿真与室内空气质量分析系统"
    API_V1_PREFIX: str = "/api"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/changxin_gongdeng"

    REDIS_URL: Optional[str] = None

    MQTT_HOST: Optional[str] = None
    MQTT_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    MQTT_TOPIC_PREFIX: str = "gongdeng"
    MQTT_BROKER: str = "localhost"
    MQTT_TOPIC_ALERT: str = "gongdeng/alerts"
    MQTT_TOPIC_DATA: str = "gongdeng/sensor"

    PM25_THRESHOLD_WARNING: float = 75.0
    PM25_THRESHOLD_CRITICAL: float = 150.0
    FLUE_VELOCITY_MIN: float = 0.1
    FLUE_TEMPERATURE_MAX: float = 200.0

    MODBUS_HOST: str = "localhost"
    MODBUS_PORT: int = 502

    ROOM_SIZE_X: float = 10.0
    ROOM_SIZE_Y: float = 8.0
    ROOM_SIZE_Z: float = 3.0
    GRID_RESOLUTION: int = 5

    DEFAULT_FUEL_TYPE: str = "animal_fat"
    AIR_CHANGE_RATE: float = 0.5
    OUTDOOR_PM25: float = 35.0
    VENTILATION_INLET: tuple = (0.0, 4.0, 2.0)
    VENTILATION_OUTLET: tuple = (10.0, 4.0, 2.0)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

FUEL_TYPES = {
    "animal_fat": {
        "name": "动物脂肪（汉代常用）",
        "heating_value": 37.5,
        "modbus_value": 1
    },
    "sesame_oil": {
        "name": "麻油",
        "heating_value": 37.0,
        "modbus_value": 2
    },
    "beeswax": {
        "name": "蜜蜡",
        "heating_value": 42.0,
        "modbus_value": 3
    },
    "mineral_oil": {
        "name": "矿物油（参照）",
        "heating_value": 44.0,
        "modbus_value": 4
    },
    "tallow": {
        "name": "牛油",
        "heating_value": 39.0,
        "modbus_value": 5
    }
}
