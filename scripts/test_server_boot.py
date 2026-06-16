import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

async def main():
    try:
        from app.config import settings
        from app.bus import MessageBus
        from app.database import AsyncSessionLocal
        from app.modules import ModbusReceiver, CFDSimulator, AirQualityAnalyzer, AlarmMQTTService
        from app.config_loader import load_fuel_config

        print("[1/6] Configs loaded")
        print(f"      REDIS_URL={settings.REDIS_URL}")
        print(f"      DEFAULT_FUEL={settings.DEFAULT_FUEL_TYPE}")
        print(f"      DATABASE_URL={settings.DATABASE_URL}")

        bus = MessageBus(redis_url=settings.REDIS_URL)
        await bus.connect()
        mode = "Redis" if bus._use_redis else "In-Memory"
        print(f"[2/6] Bus connected: {mode}")

        db = AsyncSessionLocal()
        print("[3/6] DB session created (未真实连接,后续将捕获异常)")

        fuel_cfg = load_fuel_config()
        print(f"[4/6] Fuel loaded: {len(fuel_cfg['fuel_types'])} types, mapping={len(fuel_cfg['modbus_mapping'])}")

        try:
            receiver = ModbusReceiver(db, bus, default_fuel_type=settings.DEFAULT_FUEL_TYPE)
            cfd = CFDSimulator(db, bus)
            aq = AirQualityAnalyzer(db, bus)
            alarm = AlarmMQTTService(db, bus)
            print(f"[5/6] 4 modules instantiated OK")
        except Exception as e:
            import traceback
            print(f"[5/6][FAIL] 模块实例化失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            return 1

        try:
            await cfd.bind_to_bus()
            await aq.bind_to_bus()
            await alarm.bind_to_bus()
            print(f"[6/6] Bus subscriptions bound OK")
        except Exception as e:
            import traceback
            print(f"[6/6][FAIL] 绑定订阅失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            return 1

        print("\n[INFO] 启动流程全部通过，现在模拟一次传感器数据请求:")
        from app.schemas.sensor import SensorDataCreate
        from datetime import datetime

        payload = SensorDataCreate(
            lamp_id=1,
            oil_consumption=1.8,
            flue_temperature=130.0,
            flue_velocity=0.42,
            indoor_pm25=55.0,
            oil_level=350,
            ambient_temperature=23.0,
            ambient_humidity=50.0,
            fuel_type="beeswax",
            air_change_rate=0.8,
            outdoor_pm25=22.0,
        )

        try:
            result = await receiver.ingest(payload)
            print(f"  Status: {result.get('status')}")
            print(f"  Validation: passed={result['validation']['passed']}, errors={result['validation']['errors']}")
            summary = result.get('payload_summary', {})
            print(f"  Summary: lamp={summary.get('lamp_id')}, fuel={summary.get('fuel_type')}, "
                  f"T={summary.get('flue_temperature')}, v={summary.get('flue_velocity')}, "
                  f"PM25={summary.get('indoor_pm25')}, ACH={summary.get('air_change_rate')}")
        except Exception as e:
            import traceback
            print(f"  [FAIL] 管线执行失败: {type(e).__name__}: {e}")
            traceback.print_exc()

        await asyncio.sleep(0.2)
        try:
            await db.close()
        except Exception:
            pass
        await bus.close()
        print("\n[SUCCESS] 全流程测试通过")
        return 0

    except Exception as e:
        import traceback
        print(f"[FATAL] 启动流程崩溃: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
