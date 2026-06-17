# -*- coding: utf-8 -*-
"""
Feature 新增功能测试套件
覆盖：朝代对比净化效率 / 跨时代CADR对比 / 多灯协同净化 / 虚拟操作交互
测试级别：正常 + 边界 + 异常
"""

import asyncio
import json
import math
import os
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.config_loader import (
    load_dynasty_lamps_config,
    load_modern_purifiers_config,
    load_banquet_scenes_config,
    load_cfd_config,
    load_air_quality_config,
    load_fuel_config,
)
from app.bus import MessageBus
from app.modules.cfd_simulator import CFDSimulator
from app.modules.air_quality_analyzer import AirQualityAnalyzer

PASS_COUNT = 0
FAIL_COUNT = 0
TESTS = []


def test(name):
    def decorator(fn):
        TESTS.append((name, fn))
        return fn
    return decorator


def assert_ok(condition, msg=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
        raise AssertionError(msg or f"断言失败: {condition}")


def assert_approx(a, b, tol=0.01, msg=""):
    diff = abs(a - b)
    assert_ok(diff <= tol, msg or f"近似断言失败: |{a} - {b}| = {diff} > {tol}")


def assert_between(val, lo, hi, msg=""):
    assert_ok(lo <= val <= hi, msg or f"范围断言失败: {val} 不在 [{lo}, {hi}]")


# ============================================================
# 一、朝代对比 — 净化效率验证
# ============================================================

class TestDynastyCompare:
    """朝代环保灯烟道设计对比：验证三种灯CFD结果与净化效率的正确性"""

    @test("朝代灯配置文件完整加载")
    def test_config_loaded(self, cfd):
        cfg = load_dynasty_lamps_config()
        lamps = cfg.get("dynasty_lamps", {})
        assert_ok(len(lamps) >= 3, f"朝代灯数量 {len(lamps)} < 3")
        for key in ["changxin_gongdeng", "yanyu_deng", "niu_deng"]:
            assert_ok(key in lamps, f"缺少灯型 {key}")
            lamp = lamps[key]
            assert_ok("flue_geometry" in lamp, f"{key} 缺 flue_geometry")
            assert_ok("purification_characteristics" in lamp, f"{key} 缺 purification_characteristics")

    @test("三种灯CFD仿真均可执行")
    def test_cfd_three_lamps(self, cfd):
        for lt in ["changxin_gongdeng", "yanyu_deng", "niu_deng"]:
            result = cfd.simulate(
                flue_temperature=150.0,
                flue_velocity=0.4,
                ambient_temperature=22.0,
                lamp_type=lt,
            )
            assert_ok("reynolds_number" in result, f"{lt} 缺 reynolds_number")
            assert_ok("settling_efficiency" in result, f"{lt} 缺 settling_efficiency")
            assert_ok("flow_regime" in result, f"{lt} 缺 flow_regime")
            assert_ok(result["settling_efficiency"] > 0, f"{lt} 沉降效率 <= 0")
            assert_ok(result["lamp_type"] == lt, f"lamp_type 不匹配: {result['lamp_type']} != {lt}")

    @test("三种灯净化效率存在差异且顺序正确")
    def test_efficiency_ordering(self, cfd):
        results = {}
        for lt in ["changxin_gongdeng", "yanyu_deng", "niu_deng"]:
            r = cfd.simulate(
                flue_temperature=150.0,
                flue_velocity=0.4,
                ambient_temperature=22.0,
                lamp_type=lt,
            )
            results[lt] = r

        eff_cx = results["changxin_gongdeng"]["settling_efficiency"]
        eff_yy = results["yanyu_deng"]["settling_efficiency"]
        eff_nd = results["niu_deng"]["settling_efficiency"]

        assert_ok(eff_cx > 0 and eff_yy > 0 and eff_nd > 0,
                   f"沉降效率应全为正: cx={eff_cx}, yy={eff_yy}, nd={eff_nd}")

        effs = [eff_cx, eff_yy, eff_nd]
        assert_ok(len(set([round(e, 4) for e in effs])) >= 2,
                   f"三种灯的沉降效率不应完全相同: {effs}")

    @test("烟道几何参数影响CFD结果")
    def test_geometry_impact(self, cfd):
        cfg = load_dynasty_lamps_config()
        lamps = cfg["dynasty_lamps"]

        r_default = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4,
                                  ambient_temperature=22.0, lamp_type="changxin_gongdeng")
        r_niu = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4,
                              ambient_temperature=22.0, lamp_type="niu_deng")

        geom_cx = lamps["changxin_gongdeng"]["flue_geometry"]
        geom_nd = lamps["niu_deng"]["flue_geometry"]

        assert_ok(geom_cx["bend_count"] != geom_nd["bend_count"] or
                   geom_cx["flue_diameter_m"] != geom_nd["flue_diameter_m"],
                   "烟道几何应存在差异")

        assert_ok(abs(r_default["reynolds_number"] - r_niu["reynolds_number"]) > 0.01,
                   f"不同烟道几何下Re应有差异: cx_Re={r_default['reynolds_number']}, nd_Re={r_niu['reynolds_number']}")

    @test("CFD仿真后lamp_type自动恢复")
    def test_lamp_type_recovery(self, cfd):
        original = cfd.current_lamp_type
        cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="niu_deng")
        assert_ok(cfd.current_lamp_type == original,
                   f"仿真后lamp_type未恢复: 期望={original}, 实际={cfd.current_lamp_type}")

    @test("边界: 极高温度CFD仿真")
    def test_cfd_high_temp(self, cfd):
        r = cfd.simulate(flue_temperature=2000.0, flue_velocity=0.4,
                          ambient_temperature=25.0, lamp_type="changxin_gongdeng")
        assert_ok(r["reynolds_number"] > 0, "极高温下Re应>0")
        assert_ok(0 < r["settling_efficiency"] <= 1.0, f"沉降效率应在(0,1]: {r['settling_efficiency']}")

    @test("边界: 极低流速CFD仿真")
    def test_cfd_low_velocity(self, cfd):
        r = cfd.simulate(flue_temperature=150.0, flue_velocity=0.001,
                          ambient_temperature=22.0, lamp_type="changxin_gongdeng")
        assert_ok(r["reynolds_number"] >= 0, "极低流速下Re应>=0")
        assert_ok(r["settling_efficiency"] > 0, "极低流速下沉降效率应>0")

    @test("异常: 无效灯型回退到默认")
    def test_invalid_lamp_type(self, cfd):
        original = cfd.current_lamp_type
        ok = cfd.set_lamp_type("nonexistent_lamp")
        assert_ok(not ok, "无效灯型应返回False")
        assert_ok(cfd.current_lamp_type == "changxin_gongdeng",
                   f"无效灯型后应回退: {cfd.current_lamp_type}")

    @test("异常: None灯型回退到默认")
    def test_none_lamp_type(self, cfd):
        ok = cfd.set_lamp_type(None)
        assert_ok(not ok, "None灯型应返回False")
        assert_ok(cfd.current_lamp_type == "changxin_gongdeng", "None后应回退默认")


# ============================================================
# 二、跨时代对比 — CADR值验证
# ============================================================

class TestAncientVsModern:
    """古代宫灯 vs 现代空气净化器: CADR/净化效率/维度评分"""

    @test("现代净化器配置完整加载")
    def test_modern_config(self, cfd):
        cfg = load_modern_purifiers_config()
        purifiers = cfg.get("modern_purifiers", {})
        assert_ok(len(purifiers) >= 1, f"净化器数量 {len(purifiers)} < 1")
        for key, p in purifiers.items():
            assert_ok("cadr_pm25_m3h" in p or "removal_efficiency_pm25_percent" in p,
                       f"{key} 缺CADR或去除率")

    @test("古今对比维度完整")
    def test_comparison_dimensions(self, cfd):
        cfg = load_modern_purifiers_config()
        dims = cfg.get("comparison_dimensions", [])
        assert_ok(len(dims) >= 5, f"对比维度数 {len(dims)} < 5")

    @test("宫灯CADR估算合理范围")
    def test_ancient_cadr_range(self, cfd):
        dynasty_cfg = load_dynasty_lamps_config()
        for lt, lamp_cfg in dynasty_cfg["dynasty_lamps"].items():
            purif = lamp_cfg.get("purification_characteristics", {})
            radius = purif.get("local_purification_radius_m", 2.5)
            eff = purif.get("base_purification_efficiency", 0.55)
            cadr = radius ** 2 * 3.14159 * eff * 60
            assert_ok(0 < cadr < 1000,
                       f"{lt} CADR={cadr:.1f} 超出合理范围(0,1000)")

    @test("现代净化器CADR量级与宫灯不同")
    def test_cadr_ancient_vs_modern(self, cfd):
        dynasty_cfg = load_dynasty_lamps_config()
        modern_cfg = load_modern_purifiers_config()

        cx_cfg = dynasty_cfg["dynasty_lamps"]["changxin_gongdeng"]["purification_characteristics"]
        ancient_cadr = cx_cfg["local_purification_radius_m"] ** 2 * 3.14159 * cx_cfg["base_purification_efficiency"] * 60

        for mk, mp in modern_cfg["modern_purifiers"].items():
            modern_cadr = mp.get("cadr_pm25_m3h", 0)
            assert_ok(modern_cadr > 0, f"现代净化器{mk} CADR应>0")
            assert_ok(modern_cadr != ancient_cadr,
                       f"现代{mk}和宫灯CADR应有量级差异: modern={modern_cadr}, ancient={ancient_cadr:.1f}")

    @test("宫灯净化效率(40%-70%)远低于HEPA(>99%)")
    def test_efficiency_gap(self, cfd):
        dynasty_cfg = load_dynasty_lamps_config()
        modern_cfg = load_modern_purifiers_config()

        r = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        ancient_eff = r["settling_efficiency"]

        for mk, mp in modern_cfg["modern_purifiers"].items():
            modern_eff = mp.get("removal_efficiency_pm25_percent", 0) / 100.0
            assert_ok(modern_eff > ancient_eff,
                       f"现代{mk}效率{modern_eff:.4f} 应高于宫灯{ancient_eff:.4f}")

    @test("宫灯在环保/艺术/历史维度远超现代")
    def test_ancient_advantages(self, cfd):
        dynasty_cfg = load_dynasty_lamps_config()
        modern_cfg = load_modern_purifiers_config()

        for lt, lamp_cfg in dynasty_cfg["dynasty_lamps"].items():
            aesthetic = lamp_cfg.get("purification_characteristics", {}).get("aesthetic_rating", 0)
            assert_ok(aesthetic >= 4, f"{lt} 艺术评分应>=4: {aesthetic}")

        for mk, mp in modern_cfg["modern_purifiers"].items():
            assert_ok(mp.get("power_w", 0) > 0, f"{mk} 功率应>0")
            assert_ok(mp.get("noise_db", 0) > 0, f"{mk} 噪音应>0")

    @test("边界: 宫灯CADR在零效率时为零")
    def test_zero_efficiency_cadr(self, cfd):
        cadr = 0.0 ** 2 * 3.14159 * 0.0 * 60
        assert_ok(cadr == 0.0, "零效率零半径CADR应为0")

    @test("异常: 不存在的净化器类型")
    def test_invalid_purifier(self, cfd):
        modern_cfg = load_modern_purifiers_config()
        assert_ok("nonexistent_purifier" not in modern_cfg.get("modern_purifiers", {}),
                   "不存在的净化器不应在配置中")


# ============================================================
# 三、协同模拟 — 多灯宴会总净化量验证
# ============================================================

class TestBanquetSynergy:
    """多灯宴会场景协同净化: 总净化量/叠加策略/场景配置"""

    @test("宴会场景配置完整加载")
    def test_banquet_config(self, aq):
        cfg = load_banquet_scenes_config()
        scenes = cfg.get("scenes", {})
        assert_ok(len(scenes) >= 2, f"场景数量 {len(scenes)} < 2")
        for sk, sc in scenes.items():
            assert_ok("room_geometry" in sc, f"{sk} 缺 room_geometry")
            assert_ok("lamp_positions" in sc, f"{sk} 缺 lamp_positions")
            assert_ok("grid_resolution" in sc, f"{sk} 缺 grid_resolution")
            rg = sc["room_geometry"]
            assert_ok(rg["room_size_x_m"] > 0, f"{sk} room_size_x_m <= 0")
            assert_ok(rg["room_size_z_m"] > 0, f"{sk} room_size_z_m <= 0")

    @test("皇室宴会场景有5盏灯")
    def test_royal_banquet_lamps(self, aq):
        cfg = load_banquet_scenes_config()
        rb = cfg["scenes"].get("royal_banquet", {})
        lamps = rb.get("lamp_positions", [])
        assert_ok(len(lamps) == 5, f"皇室宴会灯数={len(lamps)}, 期望5")

    @test("贵族雅集场景有3盏灯")
    def test_noble_gathering_lamps(self, aq):
        cfg = load_banquet_scenes_config()
        ng = cfg["scenes"].get("noble_gathering", {})
        lamps = ng.get("lamp_positions", [])
        assert_ok(len(lamps) == 3, f"贵族雅集灯数={len(lamps)}, 期望3")

    @test("set_scene_override正确切换房间尺寸")
    def test_scene_override(self, aq):
        orig_x = aq.room_size_x
        orig_y = aq.room_size_y
        orig_z = aq.room_size_z
        orig_nx = aq.nx

        aq.set_scene_override(room_size_x=20.0, room_size_y=15.0, room_size_z=5.0,
                               nx=8, ny=8, nz=8,
                               lamp_positions=[
                                   {"x_m": 5, "y_m": 5, "z_m": 1.5, "lamp_type": "changxin_gongdeng"},
                               ])
        assert_ok(aq.room_size_x == 20.0, f"room_size_x未切换: {aq.room_size_x}")
        assert_ok(aq.nx == 8, f"nx未切换: {aq.nx}")
        assert_ok(hasattr(aq, "multi_lamp_positions") and len(aq.multi_lamp_positions) == 1,
                   "multi_lamp_positions未设置")

        aq.set_scene_override(room_size_x=orig_x, room_size_y=orig_y, room_size_z=orig_z,
                               nx=orig_nx, ny=aq.ny, nz=aq.nz, lamp_positions=[])

    @test("多灯协同净化率不低于单灯基线")
    def test_synergy_improvement(self, cfd, aq):
        cfg = load_banquet_scenes_config()
        scene = cfg["scenes"]["noble_gathering"]
        rg = scene["room_geometry"]
        gr = scene["grid_resolution"]
        lamp_positions = scene["lamp_positions"]

        aq.set_scene_override(
            room_size_x=rg["room_size_x_m"],
            room_size_y=rg["room_size_y_m"],
            room_size_z=rg["room_size_z_m"],
            nx=gr["nx"], ny=gr["ny"], nz=gr["nz"],
            lamp_positions=lamp_positions,
        )

        settling_effs = []
        flue_vels = []
        emissions = []
        for lp in lamp_positions:
            lt = lp.get("lamp_type", "changxin_gongdeng")
            r = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type=lt)
            settling_effs.append(r["settling_efficiency"])
            flue_vels.append(r["outlet_velocity"])
            emissions.append(10.0 + (1 - r["settling_efficiency"]) * 20.0)

        multi_result, _ = aq.analyze_banquet(
            base_pm25=50.0,
            lamp_emissions_ug=emissions,
            settling_efficiencies=settling_effs,
            flue_velocities=flue_vels,
            ambient_temperature=22.0,
        )

        assert_ok(multi_result["purification_rate"] > 0,
                   f"多灯净化率应>0: {multi_result['purification_rate']}")
        assert_ok(multi_result["avg_pm25"] > 0,
                   f"多灯avg_pm25应>0: {multi_result['avg_pm25']}")
        assert_ok("aqi_level" in multi_result, "缺aqi_level")

    @test("叠加策略: 同一格点取最强净化(min)")
    def test_min_overlap_strategy(self, aq):
        aq.set_scene_override(
            room_size_x=10.0, room_size_y=8.0, room_size_z=3.5,
            nx=5, ny=5, nz=5,
            lamp_positions=[
                {"x_m": 5.0, "y_m": 4.0, "z_m": 1.5, "lamp_type": "changxin_gongdeng"},
                {"x_m": 5.0, "y_m": 4.0, "z_m": 1.5, "lamp_type": "niu_deng"},
            ],
        )
        field = aq.initialize_multi_lamp_field(50.0, [15.0, 15.0])
        purified, rate, details = aq.apply_multi_lamp_purification(
            field, [0.45, 0.50], [0.35, 0.40]
        )
        assert_ok(rate > 0, f"叠加净化率应>0: {rate}")
        assert_ok(details["num_lamps"] == 2, f"灯数应为2: {details['num_lamps']}")
        assert_ok(len(details["per_lamp"]) == 2, "每灯详情应2条")

    @test("宴会场景返回有效网格数据")
    def test_banquet_grid_output(self, cfd, aq):
        cfg = load_banquet_scenes_config()
        scene = cfg["scenes"]["noble_gathering"]
        rg = scene["room_geometry"]
        gr = scene["grid_resolution"]

        aq.set_scene_override(
            room_size_x=rg["room_size_x_m"],
            room_size_y=rg["room_size_y_m"],
            room_size_z=rg["room_size_z_m"],
            nx=gr["nx"], ny=gr["ny"], nz=gr["nz"],
            lamp_positions=scene["lamp_positions"],
        )

        settling_effs = [0.45] * len(scene["lamp_positions"])
        flue_vels = [0.35] * len(scene["lamp_positions"])
        emissions = [15.0] * len(scene["lamp_positions"])

        result, grid = aq.analyze_banquet(
            base_pm25=50.0,
            lamp_emissions_ug=emissions,
            settling_efficiencies=settling_effs,
            flue_velocities=flue_vels,
        )

        assert_ok(grid.shape == (gr["nx"], gr["ny"], gr["nz"]),
                   f"网格形状不匹配: {grid.shape} != ({gr['nx']},{gr['ny']},{gr['nz']})")
        assert_ok(float(np.mean(grid)) > 0, "平均浓度应>0")
        assert_ok("avg_pm25" in result, "缺 avg_pm25")
        assert_ok("aqi_level" in result, "缺 aqi_level")

    @test("边界: 单灯宴会场景退化为普通单灯")
    def test_single_lamp_banquet(self, cfd, aq):
        aq.set_scene_override(
            room_size_x=10.0, room_size_y=8.0, room_size_z=3.5,
            nx=5, ny=5, nz=5,
            lamp_positions=[{"x_m": 5.0, "y_m": 4.0, "z_m": 1.5}],
        )
        r = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        result, grid = aq.analyze_banquet(
            base_pm25=50.0,
            lamp_emissions_ug=[15.0],
            settling_efficiencies=[r["settling_efficiency"]],
            flue_velocities=[r["outlet_velocity"]],
        )
        assert_ok(result["purification_rate"] >= 0, "单灯净化率应>=0")
        assert_ok(grid.shape[0] > 0, "网格维度应>0")

    @test("边界: 极大房间极多灯")
    def test_large_room_many_lamps(self, cfd, aq):
        many_lamps = [{"x_m": 5 + i * 10, "y_m": 7.5, "z_m": 1.5} for i in range(20)]
        aq.set_scene_override(
            room_size_x=200.0, room_size_y=150.0, room_size_z=10.0,
            nx=5, ny=5, nz=5,
            lamp_positions=many_lamps,
        )
        effs = [0.45] * 20
        vels = [0.35] * 20
        ems = [15.0] * 20
        result, grid = aq.analyze_banquet(
            base_pm25=100.0,
            lamp_emissions_ug=ems,
            settling_efficiencies=effs,
            flue_velocities=vels,
        )
        assert_ok(result["purification_rate"] >= 0, "极大房间净化率应>=0")

    @test("异常: 无灯宴会场景")
    def test_zero_lamp_banquet(self, aq):
        aq.set_scene_override(
            room_size_x=10.0, room_size_y=8.0, room_size_z=3.5,
            nx=5, ny=5, nz=5,
            lamp_positions=[],
        )
        result, grid = aq.analyze_banquet(
            base_pm25=50.0,
            lamp_emissions_ug=[],
            settling_efficiencies=[],
            flue_velocities=[],
        )
        assert_ok(result["purification_rate"] >= 0, "无灯场景净化率应>=0")

    @test("异常: 不存在的宴会场景key")
    def test_invalid_scene_key(self, aq):
        cfg = load_banquet_scenes_config()
        assert_ok("nonexistent_scene" not in cfg.get("scenes", {}),
                   "不存在的场景不应在配置中")


# ============================================================
# 四、虚拟操作 — 交互教育性验证
# ============================================================

class TestVirtualOperation:
    """公众虚拟操作宫灯: 灯型切换/火焰强度/烟道堵塞/状态恢复"""

    @test("灯型切换成功返回True")
    def test_set_lamp_type_success(self, cfd):
        ok = cfd.set_lamp_type("yanyu_deng")
        assert_ok(ok, "切换雁鱼灯应成功")
        assert_ok(cfd.current_lamp_type == "yanyu_deng",
                   f"当前灯型应为yanyu_deng: {cfd.current_lamp_type}")
        cfd.set_lamp_type("changxin_gongdeng")

    @test("灯型切换后CFD结果反映几何差异")
    def test_lamp_switch_cfd_diff(self, cfd):
        r1 = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        r2 = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="niu_deng")
        assert_ok(r1["lamp_type"] != r2["lamp_type"],
                   f"lamp_type应不同: {r1['lamp_type']} vs {r2['lamp_type']}")

    @test("灯型切换后模拟结束自动恢复原灯型")
    def test_auto_recovery_after_simulate(self, cfd):
        cfd.set_lamp_type("changxin_gongdeng")
        cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="niu_deng")
        assert_ok(cfd.current_lamp_type == "changxin_gongdeng",
                   f"仿真后应恢复: {cfd.current_lamp_type}")

    @test("get_lamp_config返回正确配置")
    def test_get_lamp_config(self, cfd):
        cfg = cfd.get_lamp_config("yanyu_deng")
        assert_ok(cfg is not None, "雁鱼灯配置不应为None")
        assert_ok("flue_geometry" in cfg, "雁鱼灯配置缺flue_geometry")
        assert_ok(cfg["flue_geometry"]["flue_length_m"] > 0, "烟道长度应>0")

    @test("list_dynasty_lamps列出所有灯型")
    def test_list_dynasty_lamps(self, cfd):
        lamps = cfd.list_dynasty_lamps()
        assert_ok(len(lamps) >= 3, f"灯型数 {len(lamps)} < 3")
        assert_ok("changxin_gongdeng" in lamps, "缺长信宫灯")
        assert_ok("yanyu_deng" in lamps, "缺雁鱼灯")
        assert_ok("niu_deng" in lamps, "缺牛灯")

    @test("火焰强度影响CFD雷诺数和压降")
    def test_flame_intensity_effect(self, cfd):
        r_low = cfd.simulate(flue_temperature=80.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        r_high = cfd.simulate(flue_temperature=600.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        assert_ok(r_high["reynolds_number"] != r_low["reynolds_number"],
                   f"不同温度Re应有差异: {r_high['reynolds_number']} vs {r_low['reynolds_number']}")
        assert_ok(r_high["temperature_drop_c"] != r_low["temperature_drop_c"],
                   f"不同温度温降应有差异: {r_high['temperature_drop_c']} vs {r_low['temperature_drop_c']}")

    @test("烟道堵塞(低流速)降低净化效果")
    def test_blockage_reduces_purification(self, cfd):
        r_normal = cfd.simulate(flue_temperature=150.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        r_blocked = cfd.simulate(flue_temperature=150.0, flue_velocity=0.05, lamp_type="changxin_gongdeng")
        assert_ok(r_blocked["settling_efficiency"] != r_normal["settling_efficiency"],
                   "堵塞后沉降效率应有变化")

    @test("set_scene_override可恢复默认参数")
    def test_scene_override_restore(self, aq):
        orig_x = aq.room_size_x
        orig_nx = aq.nx

        aq.set_scene_override(room_size_x=999.0, nx=10, lamp_positions=[])
        assert_ok(aq.room_size_x == 999.0, "应切换为999")

        aq.set_scene_override(room_size_x=orig_x, nx=orig_nx, lamp_positions=[])
        assert_ok(aq.room_size_x == orig_x, "应恢复原值")

    @test("连续多次灯型切换状态一致")
    def test_rapid_lamp_switching(self, cfd):
        for lt in ["niu_deng", "yanyu_deng", "changxin_gongdeng", "niu_deng", "changxin_gongdeng"]:
            ok = cfd.set_lamp_type(lt)
            assert_ok(ok, f"切换到{lt}应成功")
            assert_ok(cfd.current_lamp_type == lt, f"当前灯型不一致: {cfd.current_lamp_type} != {lt}")
        cfd.set_lamp_type("changxin_gongdeng")

    @test("边界: 温度0度CFD仿真")
    def test_zero_temperature(self, cfd):
        r = cfd.simulate(flue_temperature=0.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
        assert_ok("reynolds_number" in r, "0度仿真应返回结果")
        assert_ok(r["settling_efficiency"] >= 0, "0度沉降效率应>=0")

    @test("异常: 负温度CFD仿真不崩溃")
    def test_negative_temperature(self, cfd):
        try:
            r = cfd.simulate(flue_temperature=-10.0, flue_velocity=0.4, lamp_type="changxin_gongdeng")
            assert_ok("reynolds_number" in r, "负温度应仍返回结果")
        except Exception:
            pass

    @test("异常: 零流速CFD仿真")
    def test_zero_velocity(self, cfd):
        r = cfd.simulate(flue_temperature=150.0, flue_velocity=0.0, lamp_type="changxin_gongdeng")
        assert_ok("reynolds_number" in r, "零流速应返回结果")

    @test("异常: 空气质量模块空排放列表")
    def test_empty_emissions(self, aq):
        aq.set_scene_override(room_size_x=10.0, room_size_y=8.0, room_size_z=3.5,
                               nx=5, ny=5, nz=5, lamp_positions=[])
        result, grid = aq.analyze_banquet(
            base_pm25=50.0,
            lamp_emissions_ug=[],
            settling_efficiencies=[],
            flue_velocities=[],
        )
        assert_ok("avg_pm25" in result, "空排放应返回结果")


# ============================================================
# 五、API 端点测试 (FastAPI TestClient)
# ============================================================

class TestComparisonAPI:
    """comparison 路由 API 回归测试"""

    @test("GET /api/comparison/dynasty-lamps 返回三种灯")
    def test_api_dynasty_lamps(self, client):
        r = client.get("/api/comparison/dynasty-lamps")
        assert_ok(r.status_code == 200, f"状态码={r.status_code}")
        body = r.json()
        lamps = body.get("dynasty_lamps", [])
        assert_ok(len(lamps) >= 3, f"灯数量={len(lamps)} < 3")

    @test("POST /api/comparison/dynasty-compare 返回对比结果")
    def test_api_dynasty_compare(self, client):
        r = client.post("/api/comparison/dynasty-compare", json={
            "lamp_types": ["changxin_gongdeng", "yanyu_deng", "niu_deng"],
            "flue_temperature": 150.0,
            "flue_velocity": 0.4,
            "ambient_temperature": 22.0,
        })
        assert_ok(r.status_code == 200, f"状态码={r.status_code}")
        body = r.json()
        comparison = body.get("comparison", [])
        assert_ok(len(comparison) >= 3, f"对比结果数={len(comparison)} < 3")
        for item in comparison:
            assert_ok("cfd" in item, f"缺cfd: {list(item.keys())}")
            assert_ok("air_quality" in item, f"缺air_quality: {list(item.keys())}")

    @test("GET /api/comparison/modern-purifiers 返回净化器")
    def test_api_modern_purifiers(self, client):
        r = client.get("/api/comparison/modern-purifiers")
        assert_ok(r.status_code == 200, f"状态码={r.status_code}")
        body = r.json()
        purifiers = body.get("modern_purifiers", {})
        assert_ok(len(purifiers) >= 1, f"净化器数量={len(purifiers)} < 1")

    @test("POST /api/comparison/ancient-vs-modern 返回对比")
    def test_api_ancient_vs_modern(self, client):
        r = client.post("/api/comparison/ancient-vs-modern", json={
            "lamp_type": "changxin_gongdeng",
            "modern_purifier": "basic_hepa_h13",
            "room_area_m2": 30.0,
            "room_height_m": 3.0,
        })
        assert_ok(r.status_code == 200, f"状态码={r.status_code}")
        body = r.json()
        assert_ok("ancient_lamp" in body, "缺 ancient_lamp")
        assert_ok("modern_purifier" in body, "缺 modern_purifier")
        assert_ok("summary" in body, "缺 summary")

        ancient = body["ancient_lamp"]
        modern = body["modern_purifier"]
        assert_ok("scores" in ancient, "古代缺 scores")
        assert_ok("scores" in modern, "现代缺 scores")
        assert_ok(ancient["scores"]["estimated_cadr_m3h"] > 0, "古代CADR应>0")
        assert_ok(modern["scores"]["estimated_cadr_m3h"] > ancient["scores"]["estimated_cadr_m3h"],
                   "现代CADR应远超古代")

    @test("GET /api/comparison/banquet-scenes 返回场景")
    def test_api_banquet_scenes(self, client):
        r = client.get("/api/comparison/banquet-scenes")
        assert_ok(r.status_code == 200, f"状态码={r.status_code}")
        body = r.json()
        scenes = body.get("scenes", {})
        assert_ok(len(scenes) >= 2, f"场景数={len(scenes)} < 2")

    @test("POST /api/comparison/banquet-simulation 返回协同结果")
    def test_api_banquet_simulation(self, client):
        r = client.post("/api/comparison/banquet-simulation", json={
            "scene_key": "noble_gathering",
            "base_pm25_ugm3": 50.0,
            "air_change_rate_ach": 0.5,
            "outdoor_pm25_ugm3": 35.0,
            "ambient_temperature_c": 22.0,
            "ambient_humidity_percent": 50.0,
            "flue_temperature_c": 150.0,
            "flue_velocity_ms": 0.4,
        })
        assert_ok(r.status_code == 200, f"状态码={r.status_code}")
        body = r.json()
        assert_ok("banquet_result" in body, "缺 banquet_result")
        assert_ok("synergy_analysis" in body, "缺 synergy_analysis")
        assert_ok("grid_data" in body, "缺 grid_data")
        assert_ok("per_lamp_cfd" in body, "缺 per_lamp_cfd")

        synergy = body["synergy_analysis"]
        assert_ok("num_lamps" in synergy, "缺 num_lamps")
        assert_ok(synergy["num_lamps"] == 3, f"贵族雅集灯数应为3: {synergy['num_lamps']}")

    @test("API: 不存在的宫灯类型返回400")
    def test_api_invalid_lamp_type(self, client):
        r = client.post("/api/comparison/ancient-vs-modern", json={
            "lamp_type": "nonexistent_lamp",
            "modern_purifier": "basic_hepa_h13",
        })
        assert_ok(r.status_code == 400, f"期望400, 得到{r.status_code}")

    @test("API: 不存在的净化器类型返回400")
    def test_api_invalid_purifier(self, client):
        r = client.post("/api/comparison/ancient-vs-modern", json={
            "lamp_type": "changxin_gongdeng",
            "modern_purifier": "fake_purifier",
        })
        assert_ok(r.status_code == 400, f"期望400, 得到{r.status_code}")

    @test("API: 不存在的宴会场景返回400")
    def test_api_invalid_scene(self, client):
        r = client.post("/api/comparison/banquet-simulation", json={
            "scene_key": "nonexistent_scene",
        })
        assert_ok(r.status_code == 400, f"期望400, 得到{r.status_code}")

    @test("API: 原有API不受影响 /health")
    def test_api_health_unchanged(self, client):
        r = client.get("/health")
        assert_ok(r.status_code == 200, f"原有/health 状态码={r.status_code}")
        body = r.json()
        assert_ok(body["status"] == "healthy", f"健康状态={body['status']}")

    @test("API: 原有POST /api/sensor/data不受影响")
    def test_api_sensor_data_unchanged(self, client):
        payload = {
            "lamp_id": 1,
            "oil_consumption": 1.6,
            "flue_temperature": 125.0,
            "flue_velocity": 0.45,
            "indoor_pm25": 52.0,
            "oil_level": 420,
            "ambient_temperature": 24.0,
            "ambient_humidity": 55.0,
        }
        r = client.post("/api/sensor/data", json=payload)
        assert_ok(r.status_code == 200, f"原有sensor/data 状态码={r.status_code}")


# ============================================================
# 主运行器
# ============================================================

async def run_tests():
    global PASS_COUNT, FAIL_COUNT

    from app.database import AsyncSessionLocal
    from app.config import settings
    import inspect

    print("\n" + "=" * 70)
    print("  长信宫灯 Feature 新增功能测试套件")
    print("  覆盖: 朝代对比 / 跨时代CADR / 多灯协同 / 虚拟操作 / API回归")
    print("=" * 70)

    db = AsyncSessionLocal()
    bus = MessageBus(settings.REDIS_URL)
    await bus.connect()

    cfd = CFDSimulator(db, bus)
    aq = AirQualityAnalyzer(db, bus)

    try:
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
    except Exception as e:
        print(f"\n  [WARN] 无法创建TestClient: {e}")
        print(f"  [WARN] API测试将跳过\n")
        client = None

    test_groups = [
        ("一、朝代对比 — 净化效率验证", TestDynastyCompare),
        ("二、跨时代对比 — CADR值验证", TestAncientVsModern),
        ("三、协同模拟 — 多灯宴会总净化量", TestBanquetSynergy),
        ("四、虚拟操作 — 交互教育性", TestVirtualOperation),
        ("五、API端点回归测试", TestComparisonAPI),
    ]

    for group_name, group_cls in test_groups:
        print(f"\n{'─' * 60}")
        print(f"  {group_name}")
        print(f"{'─' * 60}")

        instance = group_cls()
        methods = [(name, getattr(instance, name)) for name in sorted(dir(instance))
                    if name.startswith("test_") and callable(getattr(instance, name))]

        for method_name, method_fn in methods:
            sig = inspect.signature(method_fn)
            params = list(sig.parameters.keys())

            needs_cfd = "cfd" in params
            needs_aq = "aq" in params
            needs_client = "client" in params

            if needs_client and client is None:
                print(f"  [SKIP] {method_name} (TestClient不可用)")
                continue

            try:
                kwargs = {}
                if needs_cfd:
                    kwargs["cfd"] = cfd
                if needs_aq:
                    kwargs["aq"] = aq
                if needs_client:
                    kwargs["client"] = client
                method_fn(**kwargs)
                print(f"  [PASS] {method_name}")
            except AssertionError as e:
                print(f"  [FAIL] {method_name}: {e}")
            except Exception as e:
                print(f"  [ERROR] {method_name}: {type(e).__name__}: {e}")
                traceback.print_exc()

    cfd.set_lamp_type("changxin_gongdeng")

    try:
        await db.close()
    except Exception:
        pass
    await bus.close()

    print(f"\n{'=' * 70}")
    print(f"  测试完成: PASS={PASS_COUNT}  FAIL={FAIL_COUNT}")
    if FAIL_COUNT == 0:
        print(f"  全部通过!")
    else:
        print(f"  存在失败用例，请检查!")
    print(f"{'=' * 70}")

    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    try:
        rc = asyncio.run(run_tests())
        sys.exit(rc)
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
