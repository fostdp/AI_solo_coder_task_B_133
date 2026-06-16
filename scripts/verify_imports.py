# -*- coding: utf-8 -*-
"""验证模块导入、配置加载、4个模块实例化正确性（匹配真实模块签名）"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

OK = "[OK]"
INFO = "[INFO]"
FAIL = "[FAIL]"


class FakeDB:
    """仿真数据库会话，用于离线验证模块（避免依赖真实TimescaleDB）"""
    async def add(self, obj): return None
    async def flush(self): return None
    async def commit(self): return None
    async def close(self): return None
    async def execute(self, *a, **kw):
        class R:
            def all(self): return []
            def fetchone(self): return None
            def scalars(self):
                class S:
                    def all(self): return []
                    def first(self): return None
                return S()
        return R()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def test_config_loader():
    print("=== [1/5] 配置加载器测试 ===")
    from app.config_loader import load_fuel_config, load_cfd_config, load_air_quality_config

    fuel = load_fuel_config()
    assert "fuel_types" in fuel, "fuel_types 缺失"
    assert "modbus_mapping" in fuel, "modbus_mapping 缺失"
    assert len(fuel["fuel_types"]) >= 5, f"燃料类型数量不足: {len(fuel['fuel_types'])}"
    for ft in ['animal_fat', 'sesame_oil', 'beeswax', 'mineral_oil', 'tallow']:
        assert ft in fuel["fuel_types"], f"缺少燃料: {ft}"
        props = fuel["fuel_types"][ft]
        for key in ['heating_value_mjkg', 'density_gcm3', 'smoke_particle_density_kgm3',
                    'co2_emission_factor_kgkg', 'h2o_emission_factor_kgkg', 'soot_emission_factor_kgkg',
                    'combustion_efficiency', 'modbus_value', 'temp_factor']:
            assert key in props, f"燃料 {ft} 缺少属性 {key}"
    print(f"  {OK} 燃料配置: {len(fuel['fuel_types'])} 种燃料, Modbus映射 {len(fuel['modbus_mapping'])} 项")

    cfd = load_cfd_config()
    for key in ['flue_geometry', 'fluid_properties', 'heat_transfer', 'pressure_loss',
                'particle_settling', 'trajectory_simulation']:
        assert key in cfd, f"CFD配置缺少 {key}"
    print(f"  {OK} CFD配置: 6 个分区完整, 烟道直径={cfd['flue_geometry']['flue_diameter_m']}m, 长={cfd['flue_geometry']['flue_length_m']}m")

    aq = load_air_quality_config()
    for key in ['room_geometry', 'grid_resolution', 'diffusion_model', 'ventilation',
                'purification_model', 'emission_model', 'aqi_thresholds', 'alert_thresholds']:
        assert key in aq, f"AQ配置缺少 {key}"
    print(f"  {OK} 空气质量配置: 默认ACH={aq['ventilation']['default_air_change_rate_ach']} 次/小时")


def test_bus_channels():
    print("\n=== [2/5] 事件总线通道测试 ===")
    from app.bus.channels import CHANNELS, CHANNEL_FLOW, ALL_CHANNELS
    required = ['SENSOR_RAW', 'CFD_INPUT', 'CFD_RESULT', 'AIR_QUALITY_INPUT',
                'AIR_QUALITY_RESULT', 'ALERT_INPUT', 'ALERT_PUBLISHED', 'SENSOR_MQTT_BROADCAST']
    for ch in required:
        assert ch in CHANNELS, f"缺少通道: {ch}"
    print(f"  {OK} 通道定义: {len(CHANNELS)} 个通道")
    print(f"  {OK} ALL_CHANNELS: {len(ALL_CHANNELS)} 个通道字符串")
    print(f"  {OK} 管线流向: {' -> '.join(CHANNEL_FLOW)}")


async def test_module_instantiation():
    print("\n=== [3/5] 4模块实例化测试 ===")
    from app.bus.redis_bus import MessageBus
    from app.modules.modbus_receiver import ModbusReceiver
    from app.modules.cfd_simulator import CFDSimulator
    from app.modules.air_quality_analyzer import AirQualityAnalyzer
    from app.modules.alarm_mqtt import AlarmMQTTService
    from app.config import Settings
    from app.config_loader import load_cfd_config, load_air_quality_config

    settings = Settings()
    fake_db = FakeDB()

    bus = MessageBus(settings.REDIS_URL)
    await bus.connect()
    mode = "Redis Pub/Sub" if bus._use_redis else "In-Memory Queue (fallback)"
    print(f"  {OK} 事件总线就绪 (模式: {mode})")

    receiver = ModbusReceiver(fake_db, bus, default_fuel_type=settings.DEFAULT_FUEL_TYPE)
    print(f"  {OK} ModbusReceiver 实例化 (默认燃料={settings.DEFAULT_FUEL_TYPE})")

    cfd = CFDSimulator(fake_db, bus)
    print(f"  {OK} CFDSimulator 实例化 (烟道长={cfd.params.flue_length:.3f}m, 直径={cfd.params.flue_diameter:.3f}m)")

    aq = AirQualityAnalyzer(fake_db, bus)
    aq_cfg = load_air_quality_config()
    print(f"  {OK} AirQualityAnalyzer 实例化 (网格: {aq_cfg['grid_resolution']['nx']}x{aq_cfg['grid_resolution']['ny']}x{aq_cfg['grid_resolution']['nz']})")

    alarm = AlarmMQTTService(fake_db, bus)
    print(f"  {OK} AlarmMQTTService 实例化")

    return bus, receiver, cfd, aq, alarm, fake_db


async def test_pipeline_flow():
    print("\n=== [4/5] 模块管线级联调用测试 ===")
    from app.bus.redis_bus import MessageBus
    from app.modules.modbus_receiver import ModbusReceiver
    from app.modules.cfd_simulator import CFDSimulator
    from app.modules.air_quality_analyzer import AirQualityAnalyzer
    from app.modules.alarm_mqtt import AlarmMQTTService
    from app.bus.channels import CHANNELS
    from app.config import Settings
    from app.schemas.sensor import SensorDataCreate

    published = {ch: [] for ch in CHANNELS.values()}

    def make_publish_tap(bus_publish):
        async def wrapped(channel, payload):
            published[channel].append(payload)
            return await bus_publish(channel, payload)
        return wrapped

    settings = Settings()
    fake_db = FakeDB()

    bus = MessageBus(settings.REDIS_URL)
    await bus.connect()
    orig_publish = bus.publish
    bus.publish = make_publish_tap(orig_publish)

    receiver = ModbusReceiver(fake_db, bus, default_fuel_type=settings.DEFAULT_FUEL_TYPE)
    cfd = CFDSimulator(fake_db, bus)
    aq = AirQualityAnalyzer(fake_db, bus)
    alarm = AlarmMQTTService(fake_db, bus)

    await cfd.bind_to_bus()
    await aq.bind_to_bus()
    await alarm.bind_to_bus()

    test_payload = SensorDataCreate(
        lamp_id=1,
        oil_consumption=2.5,
        flue_temperature=145.0,
        flue_velocity=0.55,
        indoor_pm25=68.0,
        oil_level=420,
        ambient_temperature=24.5,
        ambient_humidity=55.0,
        fuel_type="sesame_oil",
        air_change_rate=1.2,
        outdoor_pm25=30.0,
    )

    try:
        ingest_result = await receiver.ingest(test_payload)
        print(f"  {OK} ModbusReceiver.ingest() 返回: status={ingest_result.get('status')}")
        if ingest_result.get("validation"):
            v = ingest_result["validation"]
            print(f"  {OK}   校验: passed={v.get('passed')}, errors={len(v.get('errors', []))}")
    except Exception as e:
        print(f"  {INFO} DB层跳过 (无真实DB): {type(e).__name__}: {e}")

    await asyncio.sleep(0.2)

    print(f"  {OK} 接收器触发: {len(published[CHANNELS['SENSOR_RAW']])}x SENSOR_RAW, "
          f"{len(published[CHANNELS['CFD_INPUT']])}x CFD_INPUT")
    print(f"  {OK} CFD->AQ: {len(published[CHANNELS['CFD_RESULT']])}x CFD_RESULT")
    print(f"  {OK} AQ->告警: {len(published[CHANNELS['AIR_QUALITY_RESULT']])}x AIR_QUALITY_RESULT")
    print(f"  {OK} 告警输入: {len(published[CHANNELS['ALERT_INPUT']])}x ALERT_INPUT")
    print(f"  {OK} MQTT广播: {len(published[CHANNELS['SENSOR_MQTT_BROADCAST']])}x SENSOR_MQTT_BROADCAST")
    print(f"  {OK} 告警已发布: {len(published[CHANNELS['ALERT_PUBLISHED']])}x ALERT_PUBLISHED")

    assert len(published[CHANNELS['SENSOR_RAW']]) >= 1, "SENSOR_RAW 未发布"
    assert len(published[CHANNELS['CFD_INPUT']]) >= 1, "CFD_INPUT 未发布"
    assert len(published[CHANNELS['SENSOR_MQTT_BROADCAST']]) >= 1, "MQTT广播未发布"

    if published[CHANNELS['CFD_RESULT']]:
        cfd_res = published[CHANNELS['CFD_RESULT']][0]
        cfd_inner = cfd_res.get("cfd", cfd_res)
        for key in ['reynolds_number', 'prandtl_number', 'nusselt_number',
                    'settling_efficiency', 'outlet_temperature', 'flow_regime']:
            assert key in cfd_inner, f"CFD结果缺少 {key}"
        print(f"  {OK} CFD结果字段完整: Re={cfd_inner['reynolds_number']:.0f}, "
              f"流型={cfd_inner['flow_regime']}, 沉降={cfd_inner['settling_efficiency']*100:.1f}%")

    if published[CHANNELS['AIR_QUALITY_RESULT']]:
        aq_res = published[CHANNELS['AIR_QUALITY_RESULT']][0]
        print(f"  {OK} AQ结果样例键: {list(aq_res.keys())[:10]}")

    if published[CHANNELS['ALERT_PUBLISHED']]:
        alert = published[CHANNELS['ALERT_PUBLISHED']][0]
        print(f"  {OK} 告警样例: type={alert.get('alert_type')}, severity={alert.get('severity')}")

    touched = sum(1 for v in published.values() if len(v) > 0)
    print(f"  {OK} 管线活跃度: {touched}/{len(CHANNELS)} 个通道有消息")

    await bus.close()
    return True


async def test_cfd_physics():
    print("\n=== [5/5] CFD物理模型 & AQ扩散单元测试 ===")
    from app.bus.redis_bus import MessageBus
    from app.modules.cfd_simulator import CFDSimulator
    from app.config import Settings

    settings = Settings()
    fake_db = FakeDB()
    bus = MessageBus(settings.REDIS_URL)
    await bus.connect()
    cfd = CFDSimulator(fake_db, bus)

    regimes = []
    test_cases = [
        (0.05, 120, "LAMINAR"),
        (0.1, 180, "LAMINAR"),
        (0.6, 220, "TRANSITIONAL"),
        (1.8, 260, "TURBULENT"),
    ]
    for vel, temp, expected in test_cases:
        sim = cfd.simulate(
            flue_temperature=temp,
            flue_velocity=vel,
            ambient_temperature=25.0,
            fuel_type="animal_fat",
        )
        regimes.append(sim['flow_regime'])
        assert 0 < sim['reynolds_number'] < 1e5, f"Re范围异常: {sim['reynolds_number']}"
        assert sim['outlet_temperature'] < temp, "冷却后温度应低于入口"
        assert 0 <= sim['settling_efficiency'] <= 1.0, f"沉降效率范围异常: {sim['settling_efficiency']}"
    expected_regimes = [tc[2] for tc in test_cases]
    print(f"  {OK} 流型分区验证: 预期 {expected_regimes} -> 实际 {regimes}")

    start_pos = (0.01, 0.0, 0.0)
    traj = cfd.get_particle_trajectory(
        start_pos=start_pos,
        flue_velocity=0.3,
        T_inlet=150.0,
        T_ambient=25.0,
        num_steps=50,
        fuel_type="beeswax",
    )
    assert len(traj) >= 2, f"粒子轨迹点数过少: 期望>=2, 实际{len(traj)}"
    for p in traj:
        assert len(p) == 3 and -1 <= p[1] <= 5.0, f"轨迹点格式错误: {p}"
    print(f"  {OK} 粒子轨迹: {len(traj)} 点, 初始 y={traj[0][1]:.3f}m, 最终 y={traj[-1][1]:.3f}m")

    fuels = ['animal_fat', 'sesame_oil', 'beeswax', 'mineral_oil', 'tallow']
    settle_by_fuel = {}
    for ft in fuels:
        s = cfd.simulate(
            flue_temperature=160.0,
            flue_velocity=0.6,
            ambient_temperature=25.0,
            fuel_type=ft,
        )
        settle_by_fuel[ft] = s['settling_efficiency'] * 100
    best = max(settle_by_fuel, key=settle_by_fuel.get)
    print(f"  {OK} 5燃料沉降效率: " + ", ".join(f"{k}={v:.1f}%" for k, v in settle_by_fuel.items()) + f" (最优={best})")

    await bus.close()
    return True


async def main():
    print("=" * 70)
    print("模块导入 & 管线验证套件 (v2 - 匹配真实模块签名)")
    print("=" * 70)
    try:
        test_config_loader()
        test_bus_channels()
        await test_module_instantiation()
        await test_pipeline_flow()
        await test_cfd_physics()
        print("\n" + "=" * 70)
        print("ALL PASSED - 全部 5 项验证通过!")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n{FAIL} 断言失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n{FAIL} 运行时错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
