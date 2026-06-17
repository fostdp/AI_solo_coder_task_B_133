"""
comparison 路由 v2：基于模块化重构后的薄路由层
职责：
  1. 接收 FastAPI 请求、做参数校验、返回响应
  2. 将业务逻辑完全委托给 4 个新模块：
     - DesignComparator（朝代灯设计对比）
     - EraComparator（跨时代古今对比）
     - SynergySimulator（多灯宴会协同净化）
     - VRGongDeng（虚拟操作体验）
  3. 不包含任何纯计算逻辑
  4. 保持向后兼容：API 端点路径、请求/响应字段完全不变
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..config_loader import (
    load_dynasty_lamps_config,
    load_modern_purifiers_config,
    load_banquet_scenes_config,
)
from ..modules.design_comparator import DesignComparator
from ..modules.era_comparator import EraComparator
from ..modules.synergy_simulator import SynergySimulator
from ..modules.vr_gong_deng import VRGongDeng

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comparison", tags=["comparison"])


# ---------------------------------------------------------------------------
# 请求/响应模型（与原版本保持一致，向后兼容）
# ---------------------------------------------------------------------------
class DynastyCompareRequest(BaseModel):
    lamp_types: List[str] = Field(default_factory=lambda: [
        "changxin_gongdeng", "yanyu_deng", "niu_deng"
    ])
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
    overlap_strategy: Optional[str] = None
    debug_log: Optional[bool] = False


class VRPredictDeltaRequest(BaseModel):
    parameter: str = "flame_intensity"
    old_value: float = 0.7
    new_value: float = 0.8
    base_settling_efficiency: float = 0.6
    base_purification_rate: float = 0.55
    base_avg_pm25: float = 35.0
    lamp_type: str = "changxin_gongdeng"


# ---------------------------------------------------------------------------
# 工具：从 request.app.state 或懒加载获取组件
# ---------------------------------------------------------------------------
def _get_cfd_and_aq(request: Request):
    return {
        "cfd": request.app.state.cfd_simulator,
        "aq": request.app.state.air_quality_analyzer,
    }


def _get_comparators(request: Request):
    """
    获取 4 个模块实例。
    优先从 app.state 取（单例复用），没有则懒加载构造。
    """
    app = request.app
    if not hasattr(app.state, "_comparators_inited"):
        cfg_lamps = load_dynasty_lamps_config()
        cfg_purifiers = load_modern_purifiers_config()
        cfg_banquet = load_banquet_scenes_config()
        app.state._dc = DesignComparator(cfg_lamps)
        app.state._ec = EraComparator(cfg_lamps, cfg_purifiers)
        app.state._ss = SynergySimulator(cfg_banquet)
        app.state._vr = VRGongDeng(cfg_lamps)
        app.state._comparators_inited = True
    return {
        "dc": app.state._dc,
        "ec": app.state._ec,
        "ss": app.state._ss,
        "vr": app.state._vr,
    }


# ===================================================================
# 第一组：朝代环保灯对比（委托给 DesignComparator）
# ===================================================================
@router.get("/dynasty-lamps")
async def get_dynasty_lamps(request: Request):
    """获取所有朝代环保灯配置（含考古信息）"""
    comps = _get_comparators(request)
    return {
        "dynasty_lamps": comps["dc"].list_dynasty_lamps(),
        "comparison_metrics": comps["dc"].get_comparison_metrics(),
    }


@router.post("/dynasty-compare")
async def compare_dynasty_lamps(request: Request, body: DynastyCompareRequest):
    """多盏朝代灯在相同工况下的 CFD + AQ 对比仿真"""
    comps = _get_comparators(request)
    mods = _get_cfd_and_aq(request)

    results, conditions = comps["dc"].run_design_comparison(
        lamp_types=body.lamp_types,
        cfd_simulator=mods["cfd"],
        air_quality_analyzer=mods["aq"],
        flue_temperature=body.flue_temperature,
        flue_velocity=body.flue_velocity,
        ambient_temperature=body.ambient_temperature,
        ambient_humidity=body.ambient_humidity,
        oil_consumption=body.oil_consumption,
        fuel_type=body.fuel_type,
    )

    insights = comps["dc"].generate_design_insights(results)
    return {
        "comparison": [DesignComparator.result_to_dict(r) for r in results],
        "conditions": conditions,
        "design_insights": insights,
    }


# ===================================================================
# 第二组：跨时代古今对比（委托给 EraComparator）
# ===================================================================
@router.get("/modern-purifiers")
async def get_modern_purifiers(request: Request):
    """获取所有现代净化器配置（含国家标准引用）"""
    comps = _get_comparators(request)
    return comps["ec"].list_modern_purifiers()


@router.post("/ancient-vs-modern")
async def ancient_vs_modern(request: Request, body: AncientModernCompareRequest):
    """古代宫灯 vs 现代空气净化器跨时代效率对比"""
    comps = _get_comparators(request)
    mods = _get_cfd_and_aq(request)

    ok, msg = comps["ec"].validate_input(body.lamp_type, body.modern_purifier)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    try:
        result = comps["ec"].compare_across_eras(
            lamp_type=body.lamp_type,
            modern_purifier=body.modern_purifier,
            cfd_simulator=mods["cfd"],
            room_area_m2=body.room_area_m2,
            room_height_m=body.room_height_m,
            ambient_temperature=body.ambient_temperature,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return EraComparator.result_to_dict(result)


# ===================================================================
# 第三组：多灯宴会协同净化（委托给 SynergySimulator）
# ===================================================================
@router.get("/banquet-scenes")
async def get_banquet_scenes(request: Request):
    """获取所有宴会场景配置"""
    comps = _get_comparators(request)
    return comps["ss"].list_banquet_scenes()


@router.post("/banquet-simulation")
async def banquet_simulation(request: Request, body: BanquetSimulationRequest):
    """多灯宴会场景协同净化仿真"""
    comps = _get_comparators(request)
    mods = _get_cfd_and_aq(request)

    if not comps["ss"].get_scene(body.scene_key):
        raise HTTPException(status_code=400, detail=f"未知场景: {body.scene_key}")

    try:
        result = comps["ss"].run_synergy_simulation(
            cfd_simulator=mods["cfd"],
            air_quality_analyzer=mods["aq"],
            scene_key=body.scene_key,
            base_pm25_ugm3=body.base_pm25_ugm3,
            air_change_rate_ach=body.air_change_rate_ach,
            outdoor_pm25_ugm3=body.outdoor_pm25_ugm3,
            ambient_temperature_c=body.ambient_temperature_c,
            ambient_humidity_percent=body.ambient_humidity_percent,
            flue_temperature_c=body.flue_temperature_c,
            flue_velocity_ms=body.flue_velocity_ms,
            fuel_type=body.fuel_type,
            overlap_strategy_override=body.overlap_strategy,
            debug_log=body.debug_log or False,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SynergySimulator.result_to_dict(result)


# ===================================================================
# 第四组：虚拟操作宫灯体验（委托给 VRGongDeng）
# （新增端点，原有对比端点不受影响）
# ===================================================================
@router.get("/vr/schema")
async def get_vr_parameter_schema(request: Request):
    """获取 VR 体验完整参数 Schema（给前端生成 UI Slider/Selector）"""
    comps = _get_comparators(request)
    return comps["vr"].get_vr_parameter_schema()


@router.get("/vr/validate")
async def validate_vr_parameters(
    request: Request,
    flame_intensity: float = Query(None, ge=0.0, le=1.5),
    blockage_degree: float = Query(None, ge=0.0, le=1.0),
    lamp_type: str = Query(None),
    fuel_type: str = Query(None),
):
    """逐个校验虚拟操作参数，返回分级建议"""
    comps = _get_comparators(request)
    vr = comps["vr"]
    out = {}
    if flame_intensity is not None:
        ok, label, suggest = vr.validate_flame_intensity(flame_intensity)
        out["flame_intensity"] = {
            "valid": ok, "grade_label": label, "suggestion": suggest,
        }
    if blockage_degree is not None:
        ok, label, suggest = vr.validate_blockage_degree(blockage_degree)
        out["blockage_degree"] = {
            "valid": ok, "grade_label": label, "suggestion": suggest,
        }
    if lamp_type is not None:
        out["lamp_type"] = {"valid": vr.validate_lamp_type(lamp_type)}
    if fuel_type is not None:
        out["fuel_type"] = {"valid": vr.validate_fuel_type(fuel_type)}
    return {"validation": out}


@router.get("/vr/education/{lamp_type}")
async def get_vr_education_facts(request: Request, lamp_type: str):
    """获取指定灯型的教育科普内容（历史/原理/考古/对比）"""
    comps = _get_comparators(request)
    if not comps["vr"].validate_lamp_type(lamp_type):
        raise HTTPException(status_code=400, detail=f"未知灯型: {lamp_type}")
    facts = comps["vr"].get_edu_facts(lamp_type)
    return VRGongDeng.facts_to_dict(facts)


@router.post("/vr/predict-delta")
async def predict_vr_purification_delta(request: Request, body: VRPredictDeltaRequest):
    """
    预测参数调整后的净化效果变化（快速估算，非 CFD 精确值）
    用于前端 slider 拖动时实时反馈。
    """
    comps = _get_comparators(request)
    vr = comps["vr"]
    if body.parameter not in ("flame_intensity", "blockage_degree", "fuel_type_switch"):
        raise HTTPException(status_code=400, detail="不支持的参数类型")
    delta = vr.predict_purification_delta(
        parameter=body.parameter,
        old_value=body.old_value,
        new_value=body.new_value,
        base_settling_efficiency=body.base_settling_efficiency,
        base_purification_rate=body.base_purification_rate,
        base_avg_pm25=body.base_avg_pm25,
        lamp_type=body.lamp_type,
    )
    return VRGongDeng.delta_to_dict(delta)
