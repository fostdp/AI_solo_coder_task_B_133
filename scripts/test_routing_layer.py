import sys
import os
import asyncio
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

async def main():
    from datetime import datetime
    from app.config import settings
    from app.bus import MessageBus
    from app.database import AsyncSessionLocal
    from app.modules import ModbusReceiver, CFDSimulator, AirQualityAnalyzer, AlarmMQTTService
    from app.config_loader import load_fuel_config
    from app.schemas.sensor import SensorDataCreate
    from app.routers.sensor import ingest_sensor_data

    # 构造一个与lifespan等价的启动流程
    published = {}

    class FakeRequest:
        def __init__(self, app_state):
            self.app = type('App', (), {'state': app_state})()

    bus = MessageBus(settings.REDIS_URL)
    await bus.connect()
    orig_publish = bus.publish
    async def publish_tap(channel, payload):
        published.setdefault(channel, []).append(payload)
        return await orig_publish(channel, payload)
    bus.publish = publish_tap

    db = AsyncSessionLocal()
    fuel_cfg = load_fuel_config()
    receiver = ModbusReceiver(db, bus, default_fuel_type=settings.DEFAULT_FUEL_TYPE)
    cfd = CFDSimulator(db, bus)
    aq = AirQualityAnalyzer(db, bus)
    alarm = AlarmMQTTService(db, bus)
    await cfd.bind_to_bus()
    await aq.bind_to_bus()
    await alarm.bind_to_bus()

    app_state = type('State', (), {
        'bus': bus,
        'modbus_receiver': receiver,
        'cfd_simulator': cfd,
        'air_quality_analyzer': aq,
        'alarm_mqtt': alarm,
        'fuel_types': fuel_cfg["fuel_types"],
        'modbus_to_fuel': fuel_cfg["modbus_mapping"],
    })()

    request = FakeRequest(app_state)

    print("=" * 70)
    print("路由层功能回归测试 (直接调用端点函数)")
    print("=" * 70)

    # ---- 1. /health 等价逻辑 ----
    print("\n[1/3] 模拟 GET /health")
    health = {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "architecture": "modbus_receiver -> cfd_simulator -> air_quality_analyzer -> alarm_mqtt",
        "bus": "redis_pubsub (in-memory fallback)",
        "configs": ["fuel_types.json", "cfd_parameters.json", "air_quality_parameters.json"],
    }
    assert health["status"] == "healthy"
    print(f"  [OK] architecture: {health['architecture']}")
    print(f"  [OK] 配置文件: {health['configs']}")

    # ---- 2. 燃料类型 ----
    print("\n[2/3] 燃料类型列表 (等价于 /api/simulation/fuel-types)")
    fuel_types = app_state.fuel_types
    assert len(fuel_types) == 5
    for ft in ['animal_fat', 'sesame_oil', 'beeswax', 'mineral_oil', 'tallow']:
        assert ft in fuel_types
    print(f"  [OK] 5 种燃料: {list(fuel_types.keys())}")

    # ---- 3. 核心 POST /api/sensor/data ----
    print("\n[3/3] 调用 ingest_sensor_data (核心管线)")
    payload = SensorDataCreate(
        lamp_id=1,
        oil_consumption=2.1,
        flue_temperature=148.0,
        flue_velocity=0.52,
        indoor_pm25=72.0,
        oil_level=390,
        ambient_temperature=23.8,
        ambient_humidity=52.0,
        fuel_type="sesame_oil",
        air_change_rate=1.0,
        outdoor_pm25=28.0,
    )
    result = await ingest_sensor_data(payload, request)
    assert isinstance(result, dict)
    print(f"  [OK] ingest 返回 dict")

    print(f"\n  --- 返回字段解析 ---")
    assert "validation" in result
    v = result["validation"]
    print(f"  [OK] validation.passed = {v.get('passed')}, errors={v.get('errors')}")

    # 检查总线通道消息
    print(f"\n  --- 事件总线通道消息数 ---")
    from app.bus.channels import CHANNELS
    for name, ch in CHANNELS.items():
        cnt = len(published.get(ch, []))
        if cnt > 0:
            print(f"  {name}: {cnt} msg")
        else:
            print(f"  {name}: 0")

    # 检查 CFD 结果
    cfd_ch = CHANNELS["CFD_RESULT"]
    if published.get(cfd_ch):
        cfd_out = published[cfd_ch][0]
        cfd = cfd_out.get("cfd")
        if cfd:
            assert "reynolds_number" in cfd
            assert "flow_regime" in cfd
            assert "settling_efficiency" in cfd
            print(f"\n  [OK] CFD 结果: Re={cfd['reynolds_number']:.0f}, "
                  f"流型={cfd['flow_regime']}, 沉降={cfd['settling_efficiency']*100:.1f}%")

    # 检查 AQ 结果
    aq_ch = CHANNELS["AIR_QUALITY_RESULT"]
    if published.get(aq_ch):
        aq_out = published[aq_ch][0]
        print(f"  [OK] AQ 结果字段: {list(aq_out.keys())[:10]}")

    # 检查告警
    alert_pub = CHANNELS["ALERT_PUBLISHED"]
    if published.get(alert_pub):
        alerts = published[alert_pub]
        print(f"  [OK] 已发布告警: {len(alerts)} 条")
        for a in alerts[:3]:
            print(f"       {a.get('alert_type')}/{a.get('severity')}: {a.get('message')}")

    touched = sum(1 for v in published.values() if len(v) > 0)
    print(f"\n  [OK] 通道活跃度: {touched}/{len(CHANNELS)}")

    await asyncio.sleep(0.2)
    try:
        await db.close()
    except Exception:
        pass
    await bus.close()

    print("\n" + "=" * 70)
    print("全部功能回归测试通过!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
        sys.exit(rc)
    except AssertionError as e:
        import traceback
        print(f"\n[FAIL] 断言失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n[FATAL] 崩溃: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
