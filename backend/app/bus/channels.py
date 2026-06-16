"""
Redis Pub/Sub 消息通道定义
数据流向:
  SENSOR_RAW (modbus_receiver 发布)
       │
       ▼
  CFD_INPUT (modbus_receiver 转发) ──► cfd_simulator 订阅
       │
       └──► 结果写入 CFD_RESULT
                   │
                   ▼
              AIR_QUALITY_INPUT ──► air_quality_analyzer 订阅
                   │
                   └──► 结果写入 AIR_QUALITY_RESULT
                               │
                               ▼
                          ALERT_INPUT ──► alarm_mqtt 订阅
                               │
                               └──► 结果写入 ALERT_PUBLISHED
"""

SENSOR_RAW = "gongdeng:sensor:raw"
CFD_INPUT = "gongdeng:cfd:input"
CFD_RESULT = "gongdeng:cfd:result"
AIR_QUALITY_INPUT = "gongdeng:aq:input"
AIR_QUALITY_RESULT = "gongdeng:aq:result"
ALERT_INPUT = "gongdeng:alert:input"
ALERT_PUBLISHED = "gongdeng:alert:published"
SENSOR_MQTT_BROADCAST = "gongdeng:sensor:mqtt"

CHANNELS = {
    "SENSOR_RAW": SENSOR_RAW,
    "CFD_INPUT": CFD_INPUT,
    "CFD_RESULT": CFD_RESULT,
    "AIR_QUALITY_INPUT": AIR_QUALITY_INPUT,
    "AIR_QUALITY_RESULT": AIR_QUALITY_RESULT,
    "ALERT_INPUT": ALERT_INPUT,
    "ALERT_PUBLISHED": ALERT_PUBLISHED,
    "SENSOR_MQTT_BROADCAST": SENSOR_MQTT_BROADCAST,
}

CHANNEL_FLOW = [
    "SENSOR_RAW",
    "CFD_INPUT",
    "CFD_RESULT",
    "AIR_QUALITY_INPUT",
    "AIR_QUALITY_RESULT",
    "ALERT_INPUT",
    "ALERT_PUBLISHED",
]

ALL_CHANNELS = [
    SENSOR_RAW,
    CFD_INPUT,
    CFD_RESULT,
    AIR_QUALITY_INPUT,
    AIR_QUALITY_RESULT,
    ALERT_INPUT,
    ALERT_PUBLISHED,
    SENSOR_MQTT_BROADCAST,
]
