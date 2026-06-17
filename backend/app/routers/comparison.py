"""
comparison 路由：朝代环保灯对比、古今效率对比、多灯宴会协同净化
新增 Feature，不修改原有 sensor 路由。
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..config_loader import (
    load_dynasty_lamps_config,
    load_modern_purifiers_config,
    load_banquet_scenes_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comparison", tags=["comparison"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------
class DynastyCompareRequest(BaseModel):
    lamp_types: List[str] = ["changxin_gongdeng", "yanyu_deng", "niu_deng"]
    flue_temperature: float = 150.0
    flue_velocity: float = 0.4
    ambient_temperature: float = 22.0
    ambient_humidity: float = 50.0
    oil_consumption: float = 1.5
    fuel_type: Optional[str] = "animal_fat"


class AncientModernCompareRequest(BaseModel):
    lamp_type: str = "changxin_gongdeng"
    modern_purifier: str = "basic_hepa_h13"
    room_area_m2: float = 30.0
    room_height_m: float = 3.0
    ambient_temperature: float = 22.0


class BanquetSimulationRequest(BaseModel):
    scene_key: str = "royal_banquet"
    base_pm25_ugm3: float = 45.0
    air_change_rate_ach: float = 0.5
    outdoor_pm25_ugm3: float = 35.0
    ambient_temperature_c: float = 22.0
    ambient_humidity_percent: float = 50.0
    flue_temperature_c: float = 150.0
    flue_velocity_ms: float = 0.4
    fuel_type: Optional[str] = "animal_fat"


# ---------------------------------------------------------------------------
# 工具：从 request.app.state 获取模块
# ---------------------------------------------------------------------------
def _get_modules(request: Request):
    return {
        "cfd": request.app.state.cfd_simulator,
        "aq": request.app.state.air_quality_analyzer,
    }


# ---------------------------------------------------------------------------
# 1. 朝代灯参数列表
# ---------------------------------------------------------------------------
@router.get("/dynasty-lamps")
async def get_dynasty_lamps():
    """获取所有朝代环保灯的配置数据"""
    cfg = load_dynasty_lamps_config()
    lamps = cfg.get("dynasty_lamps", {})
    metrics = cfg.get("comparison_metrics", [])
    result = []
    for lamp_type, lamp_cfg in lamps.items():
        flue_geom = lamp_cfg.get("flue_geometry", {})
        purif = lamp_cfg.get("purification_characteristics", {})
        result.append({
            "lamp_type": lamp_type,
            "name": lamp_cfg.get("name"),
            "dynasty": lamp_cfg.get("dynasty"),
            "era": lamp_cfg.get("era"),
            "description": lamp_cfg.get("description"),
            "material": lamp_cfg.get("material"),
            "height_m": lamp_cfg.get("height_m"),
            "weight_kg": lamp_cfg.get("weight_kg"),
            "historical_significance": lamp_cfg.get("historical_significance"),
            "flue_geometry": flue_geom,
            "purification_characteristics": purif,
            "color_3d_model": lamp_cfg.get("color_3d_model", {}),
            "aesthetic_rating": purif.get("aesthetic_rating"),
        })
    return {"dynasty_lamps": result, "comparison_metrics": metrics}


# ---------------------------------------------------------------------------
# 2. 朝代灯 CFD + AQ 对比仿真
# ---------------------------------------------------------------------------
@router.post("/dynasty-compare")
async def compare_dynasty_lamps(request: Request, body: DynastyCompareRequest):
    """多盏朝代灯在相同工况下的 CFD + AQ 对比"""
    mods = _get_modules(request)
    cfd = mods["cfd"]
    aq = mods["aq"]

    results = []
    for lamp_type in body.lamp_types:
        lamp_cfg = cfd.get_lamp_config(lamp_type)
        if not lamp_cfg:
            continue
        cfd_result = cfd.simulate(
            flue_temperature=body.flue_temperature,
            flue_velocity=body.flue_velocity,
            ambient_temperature=body.ambient_temperature,
            ambient_humidity=body.ambient_humidity,
            oil_consumption=body.oil_consumption,
            fuel_type=body.fuel_type,
            lamp_type=lamp_type,
        )
        purif = lamp_cfg.get("purification_characteristics", {})
        aq_result, grid = aq.analyze(
            indoor_pm25=50.0,
            flue_temperature=body.flue_temperature,
            flue_velocity=body.flue_velocity,
            settling_efficiency=cfd_result.get("settling_efficiency", 0.0),
            ambient_temperature=body.ambient_temperature,
            ambient_humidity=body.ambient_humidity,
            oil_consumption=body.oil_consumption,
            air_change_rate=1.0,
            outdoor_pm25=35.0,
        )
        results.append({
            "lamp_type": lamp_type,
            "name": lamp_cfg.get("name"),
            "dynasty": lamp_cfg.get("dynasty"),
            "flue_geometry": lamp_cfg.get("flue_geometry"),
            "cfd": cfd_result,
            "air_quality": {
                "purification_rate": aq_result["purification_rate"],
                "avg_pm25": aq_result["avg_pm25"],
                "aqi_level": aq_result["aqi_level"],
                "air_change_efficiency": aq_result["air_change_efficiency"],
            },
            "purification_characteristics": purif,
        })
    cfd.set_lamp_type("changxin_gongdeng")
    return {"comparison": results, "conditions": body.dict()}


# ---------------------------------------------------------------------------
# 3. 现代净化器参数列表
# ---------------------------------------------------------------------------
@router.get("/modern-purifiers")
async def get_modern_purifiers():
    cfg = load_modern_purifiers_config()
    purifiers = cfg.get("modern_purifiers", {})
    dimensions = cfg.get("comparison_dimensions", [])
    return {"modern_purifiers": purifiers, "comparison_dimensions": dimensions}


# ---------------------------------------------------------------------------
# 4. 古今效率对比
# ---------------------------------------------------------------------------
@router.post("/ancient-vs-modern")
async def ancient_vs_modern(request: Request, body: AncientModernCompareRequest):
    """古代宫灯 vs 现代空气净化器跨时代效率对比"""
    mods = _get_modules(request)
    cfd = mods["cfd"]
    aq = mods["aq"]

    cfg_dynasty = load_dynasty_lamps_config()
    cfg_modern = load_modern_purifiers_config()
    lamps_db = cfg_dynasty.get("dynasty_lamps", {})
    purifiers_db = cfg_modern.get("modern_purifiers", {})

    if body.lamp_type not in lamps_db:
        raise HTTPException(status_code=400, detail=f"未知宫灯类型: {body.lamp_type}")
    if body.modern_purifier not in purifiers_db:
        raise HTTPException(status_code=400, detail=f"未知净化器类型: {body.modern_purifier}")

    lamp_cfg = lamps_db[body.lamp_type]
    purifier_cfg = purifiers_db[body.modern_purifier]
    purif = lamp_cfg.get("purification_characteristics", {})

    cfd_result = cfd.simulate(
        flue_temperature=150.0,
        flue_velocity=0.4,
        ambient_temperature=body.ambient_temperature,
        fuel_type="animal_fat",
        lamp_type=body.lamp_type,
    )

    lamp_cadr_m3h = purif.get("local_purification_radius_m", 2.5) ** 2 * 3.14159 * purif.get("base_purification_efficiency", 0.55) * 60

    ancient_score = {
        "purification_efficiency": round(cfd_result.get("settling_efficiency", 0.0) * 100, 2),
        "coverage_area_m2": round(purif.get("local_purification_radius_m", 2.5) ** 2 * 3.14159, 2),
        "energy_consumption_w": 0.0,
        "noise_level_db": 5.0,
        "environmental_impact_score": 95.0,
        "aesthetic_value_score": purif.get("aesthetic_rating", 5) * 20.0,
        "historical_significance_score": 100.0,
        "estimated_cadr_m3h": round(lamp_cadr_m3h, 2),
    }

    modern_score = {
        "purification_efficiency": purifier_cfg.get("removal_efficiency_pm25_percent", 99.97),
        "coverage_area_m2": purifier_cfg.get("coverage_area_m2", 30.0),
        "energy_consumption_w": purifier_cfg.get("power_w", 50.0),
        "noise_level_db": purifier_cfg.get("noise_db", 35.0),
        "environmental_impact_score": 50.0,
        "aesthetic_value_score": 20.0,
        "historical_significance_score": 10.0,
        "estimated_cadr_m3h": purifier_cfg.get("cadr_pm25_m3h", 350.0),
    }

    cfd.set_lamp_type("changxin_gongdeng")
    return {
        "ancient_lamp": {
            "lamp_type": body.lamp_type,
            "name": lamp_cfg.get("name"),
            "dynasty": lamp_cfg.get("dynasty"),
            "year_invented": -150,
            "description": lamp_cfg.get("description"),
            "technology": "水滤烟 + 烟道沉降 + 自然对流",
            "cfd_summary": cfd_result,
            "scores": ancient_score,
        },
        "modern_purifier": {
            "purifier_type": body.modern_purifier,
            "name": purifier_cfg.get("name"),
            "brand": purifier_cfg.get("brand"),
            "year_invented": purifier_cfg.get("year_invented", 1940),
            "technology": purifier_cfg.get("technology"),
            "features": purifier_cfg.get("modern_features", []),
            "specs": {
                "cadr_pm25_m3h": purifier_cfg.get("cadr_pm25_m3h"),
                "power_w": purifier_cfg.get("power_w"),
                "noise_db": purifier_cfg.get("noise_db"),
                "price_rmb": purifier_cfg.get("price_rmb"),
                "energy_class": purifier_cfg.get("energy_class"),
            },
            "scores": modern_score,
        },
        "summary": {
            "ancient_advantages": [
                "零能耗，纯物理原理",
                "无烟无味安静运行",
                "极高的艺术与历史价值",
                "对环境零污染零废弃物",
            ],
            "modern_advantages": [
                "更高的 PM2.5 去除效率 (>99%)",
                "更大的有效净化面积",
                "可去除甲醛、细菌等多种污染物",
                "智能传感器与自动控制",
            ],
            "cross_era_insight": "古代环保灯体现了汉代工匠『道法自然』的设计哲学，利用流体力学原理被动净化，在2000年前即达到约50-65%的烟尘沉降效率，是人类最早的空气净化工程实践。现代净化器虽然效率更高，但依赖电力与耗材，两者代表了不同文明阶段对空气质量的思考。"
        },
    }


# ---------------------------------------------------------------------------
# 5. 宴会场景列表
# ---------------------------------------------------------------------------
@router.get("/banquet-scenes")
async def get_banquet_scenes():
    cfg = load_banquet_scenes_config()
    return cfg


# ---------------------------------------------------------------------------
# 6. 多灯宴会协同净化仿真
# ---------------------------------------------------------------------------
@router.post("/banquet-simulation")
async def banquet_simulation(request: Request, body: BanquetSimulationRequest):
    """多灯宴会场景协同净化仿真"""
    mods = _get_modules(request)
    cfd = mods["cfd"]
    aq = mods["aq"]

    scenes_cfg = load_banquet_scenes_config()
    scene = scenes_cfg.get("scenes", {}).get(body.scene_key)
    if not scene:
        raise HTTPException(status_code=400, detail=f"未知场景: {body.scene_key}")

    rg = scene["room_geometry"]
    gr = scene["grid_resolution"]
    lamp_positions = scene["lamp_positions"]
    default_params = scene.get("default_parameters", {})

    aq.set_scene_override(
        room_size_x=rg["room_size_x_m"],
        room_size_y=rg["room_size_y_m"],
        room_size_z=rg["room_size_z_m"],
        nx=gr["nx"],
        ny=gr["ny"],
        nz=gr["nz"],
        lamp_positions=lamp_positions,
    )

    settling_efficiencies = []
    flue_velocities = []
    lamp_emissions = []
    per_lamp_cfd = []

    for lp in lamp_positions:
        lamp_type = lp.get("lamp_type", "changxin_gongdeng")
        cfd_res = cfd.simulate(
            flue_temperature=body.flue_temperature_c,
            flue_velocity=body.flue_velocity_ms,
            ambient_temperature=body.ambient_temperature_c,
            ambient_humidity=body.ambient_humidity_percent,
            oil_consumption=1.5,
            fuel_type=body.fuel_type,
            lamp_type=lamp_type,
        )
        per_lamp_cfd.append({
            "lamp_type": lamp_type,
            "position": lp,
            "cfd": cfd_res,
        })
        settling_efficiencies.append(cfd_res.get("settling_efficiency", 0.0))
        flue_velocities.append(cfd_res.get("outlet_velocity", body.flue_velocity_ms))
        lamp_emissions.append(10.0 + (1.0 - cfd_res.get("settling_efficiency", 0.0)) * 20.0)

    aq_result, grid = aq.analyze_banquet(
        base_pm25=body.base_pm25_ugm3,
        lamp_emissions_ug=lamp_emissions,
        settling_efficiencies=settling_efficiencies,
        flue_velocities=flue_velocities,
        ambient_temperature=body.ambient_temperature_c,
        ambient_humidity=body.ambient_humidity_percent,
        air_change_rate=body.air_change_rate_ach,
        outdoor_pm25=body.outdoor_pm25_ugm3,
    )

    grid_flat = []
    for i in range(aq.nx):
        for j in range(aq.ny):
            for k in range(aq.nz):
                wx, wy, wz = aq._grid_to_world(i, j, k)
                grid_flat.append({
                    "grid_x": i,
                    "grid_y": j,
                    "grid_z": k,
                    "world_x": wx,
                    "world_y": wy,
                    "world_z": wz,
                    "concentration": round(float(grid[i, j, k]), 4),
                })

    single_lamp_aq, _ = aq.analyze(
        indoor_pm25=body.base_pm25_ugm3,
        flue_temperature=body.flue_temperature_c,
        flue_velocity=body.flue_velocity_ms,
        settling_efficiency=settling_efficiencies[0] if settling_efficiencies else 0.0,
        ambient_temperature=body.ambient_temperature_c,
        ambient_humidity=body.ambient_humidity_percent,
        oil_consumption=1.5,
        air_change_rate=body.air_change_rate_ach,
        outdoor_pm25=body.outdoor_pm25_ugm3,
    )

    cfd.set_lamp_type("changxin_gongdeng")
    default_room = load_banquet_scenes_config()
    default_scene = default_room.get("scenes", {}).get(default_room.get("default_scene", "royal_banquet"), {})
    rg_def = default_scene.get("room_geometry", {})
    gr_def = default_scene.get("grid_resolution", {"nx": 5, "ny": 5, "nz": 5})
    lp_def = default_scene.get("lamp_positions", [])
    aq.set_scene_override(
        room_size_x=rg_def.get("room_size_x_m", 10.0),
        room_size_y=rg_def.get("room_size_y_m", 8.0),
        room_size_z=rg_def.get("room_size_z_m", 3.5),
        nx=gr_def.get("nx", 5),
        ny=gr_def.get("ny", 5),
        nz=gr_def.get("nz", 5),
        lamp_positions=lp_def,
    )

    return {
        "scene_key": body.scene_key,
        "scene_name": scene.get("name"),
        "room_geometry": rg,
        "grid_resolution": gr,
        "lamp_positions": lamp_positions,
        "per_lamp_cfd": per_lamp_cfd,
        "banquet_result": aq_result,
        "single_lamp_baseline": {
            "purification_rate": single_lamp_aq["purification_rate"],
            "avg_pm25": single_lamp_aq["avg_pm25"],
            "aqi_level": single_lamp_aq["aqi_level"],
        },
        "synergy_analysis": {
            "purification_rate_improvement": round(
                max(0.0, aq_result["purification_rate"] - single_lamp_aq["purification_rate"]) * 100, 2
            ),
            "avg_pm25_reduction": round(
                max(0.0, single_lamp_aq["avg_pm25"] - aq_result["avg_pm25"]), 2
            ),
            "num_lamps": len(lamp_positions),
            "conclusion": (
                f"{len(lamp_positions)} 盏灯协同净化使净化速率提升 "
                f"{round(max(0.0, aq_result['purification_rate'] - single_lamp_aq['purification_rate']) * 100, 2)} 个百分点，"
                f"平均 PM2.5 降低 {round(max(0.0, single_lamp_aq['avg_pm25'] - aq_result['avg_pm25']), 2)} μg/m³"
            ),
        },
        "grid_data": grid_flat,
    }
