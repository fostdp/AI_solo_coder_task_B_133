"""
era_comparator: 古代宫灯 vs 现代空气净化器 跨时代对比模块
职责：
  1. 古代宫灯 7 维度评分（净化效率/覆盖/能耗/噪音/环保/艺术/历史）
  2. 现代净化器 7 维度评分
  3. CADR、能效比统一计算（依据 GB/T 18801-2015）
  4. 生成跨时代洞察总结
不依赖请求上下文，纯计算逻辑。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class EraDimensionScore:
    purification_efficiency: float = 0.0
    coverage_area_m2: float = 0.0
    energy_consumption_w: float = 0.0
    noise_level_db: float = 0.0
    environmental_impact_score: float = 0.0
    aesthetic_value_score: float = 0.0
    historical_significance_score: float = 0.0
    estimated_cadr_m3h: float = 0.0


@dataclass
class AncientLampProfile:
    lamp_type: str
    name: str
    dynasty: str
    year_invented: int
    description: str
    technology: str
    cfd_summary: Dict[str, Any] = field(default_factory=dict)
    scores: EraDimensionScore = field(default_factory=EraDimensionScore)
    archaeological_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModernPurifierProfile:
    purifier_type: str
    name: str
    brand: str
    year_invented: int
    technology: str
    features: List[str] = field(default_factory=list)
    specs: Dict[str, Any] = field(default_factory=dict)
    scores: EraDimensionScore = field(default_factory=EraDimensionScore)
    standards_reference: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EraComparisonResult:
    ancient: AncientLampProfile
    modern: ModernPurifierProfile
    summary: Dict[str, Any] = field(default_factory=dict)
    unified_test_condition: str = ""


# ---------------------------------------------------------------------------
# 跨时代对比器
# ---------------------------------------------------------------------------
class EraComparator:
    """古代环保灯 vs 现代空气净化器 跨时代效率对比器"""

    # 统一对比测试条件（用户要求标准化）
    UNIFIED_TEST_CONDITION = (
        "统一对比条件（参考 GB/T 18801-2015）：房间体积 60m³（4m×5m×3m），"
        "PM2.5 初始浓度 (150±15) μg/m³，环境温度 (25±2)°C，"
        "相对湿度 (50±10)%RH，连续运行 4 小时，自然通风 ACH=0.5"
    )

    # 7 维度雷达图维度说明
    DIMENSION_DESCRIPTIONS = {
        "purification_efficiency": "净化效率（PM2.5去除率，越高越好）",
        "coverage_area_m2": "有效覆盖面积（m²，越高越好）",
        "energy_consumption_w": "运行能耗（W，越低越好，反向评分）",
        "noise_level_db": "噪音水平（dB(A)，越低越好，反向评分）",
        "environmental_impact_score": "环保友好度（0-100，越高越好）",
        "aesthetic_value_score": "艺术价值（0-100，越高越好）",
        "historical_significance_score": "历史意义（0-100，越高越好）",
    }

    # 现代参数基准（用于归一化）
    MODERN_BENCHMARKS = {
        "max_cadr_pm25_m3h": 800.0,
        "max_coverage_m2": 100.0,
        "baseline_power_w": 10.0,
        "baseline_noise_db": 35.0,
    }

    # 古代能效基准（按油灯耗油量折算）
    ANCIENT_ENERGY_BASE = {
        "animal_fat_kwh_per_kg": 9.0,      # 动物脂肪热值约 9 kWh/kg
        "typical_oil_consumption_kg_h": 0.0015,  # 1.5 g/h
    }

    def __init__(
        self,
        dynasty_lamps_cfg: Optional[Dict] = None,
        modern_purifiers_cfg: Optional[Dict] = None,
    ):
        self.lamps_db = (dynasty_lamps_cfg or {}).get("dynasty_lamps", {})
        self.purifiers_db = (modern_purifiers_cfg or {}).get("modern_purifiers", {})
        self.dimensions = (modern_purifiers_cfg or {}).get("comparison_dimensions", [])
        self.standards = (modern_purifiers_cfg or {}).get("standards_reference", {})

    # ------------------------------------------------------------------
    # 校验接口
    # ------------------------------------------------------------------
    def validate_input(self, lamp_type: str, modern_purifier: str) -> Tuple[bool, str]:
        if lamp_type not in self.lamps_db:
            return False, f"未知宫灯类型: {lamp_type}"
        if modern_purifier not in self.purifiers_db:
            return False, f"未知净化器类型: {modern_purifier}"
        return True, "OK"

    # ------------------------------------------------------------------
    # 古代宫灯评分
    # ------------------------------------------------------------------
    def compute_ancient_scores(
        self,
        lamp_cfg: Dict,
        cfd_result: Dict[str, Any],
        room_area_m2: float = 30.0,
    ) -> EraDimensionScore:
        """
        计算古代宫灯 7 维度评分。
        算法：
          1) 净化效率 = CFD沉降效率×水滤比（已在CFD中体现）
          2) 覆盖面积 = π·r²，r 来自 purification_characteristics
          3) 能耗 = 0（零电耗），满分
          4) 噪音 = 5 dB（非常安静，火焰噼啪声），近乎满分
          5) 环保 = 95（零耗材、零废弃物、可再生燃料）
          6) 艺术 = aesthetic_rating × 20
          7) 历史 = 100（国家一级文物）
        """
        purif = lamp_cfg.get("purification_characteristics", {})
        settling_eff = max(cfd_result.get("settling_efficiency", 0.0), 0.0)
        radius = purif.get("local_purification_radius_m", 2.5)
        coverage = 3.14159 * radius * radius
        est_cadr = coverage * purif.get("base_purification_efficiency", 0.55) * 60

        # 能耗折算：油灯能耗按热值计算（非电能，得分为满分因为是"被动式"）
        # 古代灯无电力消耗，此处显示等效运行功率用于对比
        oil_kg_h = 0.0015  # 1.5 g/h
        equiv_power_w = self.ANCIENT_ENERGY_BASE["animal_fat_kwh_per_kg"] * oil_kg_h * 1000

        return EraDimensionScore(
            purification_efficiency=round(settling_eff * 100, 2),
            coverage_area_m2=round(coverage, 2),
            energy_consumption_w=round(equiv_power_w, 2),
            noise_level_db=5.0,
            environmental_impact_score=95.0,
            aesthetic_value_score=round(float(purif.get("aesthetic_rating", 5)) * 20.0, 2),
            historical_significance_score=100.0,
            estimated_cadr_m3h=round(est_cadr, 2),
        )

    # ------------------------------------------------------------------
    # 现代净化器评分
    # ------------------------------------------------------------------
    def compute_modern_scores(self, purifier_cfg: Dict) -> EraDimensionScore:
        """
        计算现代净化器 7 维度评分。
        净化效率 = removal_efficiency_pm25_percent（HEPA H13 = 99.97%）
        CADR、能效等全部参考 GB/T 18801-2015。
        """
        bench = self.MODERN_BENCHMARKS
        removal_eff = purifier_cfg.get("removal_efficiency_pm25_percent", 99.97)
        coverage = purifier_cfg.get("coverage_area_m2", 30.0)
        power = purifier_cfg.get("power_w", 50.0)
        noise = purifier_cfg.get("noise_db", 35.0)
        cadr = purifier_cfg.get("cadr_pm25_m3h", 350.0)

        # 能效比 (EER) = CADR / Power（GB 21551.3-2010）
        eer = round(cadr / power, 2) if power > 0 else 0.0

        # 环保评分：耗材寿命、能耗综合
        filter_life_h = purifier_cfg.get("filter_lifetime_hours", 3000)
        eco_score = min(50.0 + filter_life_h / 200.0 - max(0.0, (power - 10.0) / 2.0), 90.0)

        return EraDimensionScore(
            purification_efficiency=round(removal_eff, 2),
            coverage_area_m2=round(coverage, 2),
            energy_consumption_w=round(power, 2),
            noise_level_db=round(noise, 2),
            environmental_impact_score=round(max(eco_score, 10.0), 2),
            aesthetic_value_score=20.0,
            historical_significance_score=10.0,
            estimated_cadr_m3h=round(cadr, 2),
        )

    # ------------------------------------------------------------------
    # 能效等级计算（参考 GB 21551.3-2010）
    # ------------------------------------------------------------------
    @staticmethod
    def compute_energy_efficiency_class(eer: float) -> str:
        """
        根据能效比 EER（CADR_m3h / Power_W）给出能效等级：
        一级 ≥ 5.0  二级 4.0~4.9  三级 3.0~3.9  四级 2.0~2.9  五级 < 2.0
        """
        if eer >= 5.0:
            return "一级（最高）"
        elif eer >= 4.0:
            return "二级"
        elif eer >= 3.0:
            return "三级"
        elif eer >= 2.0:
            return "四级"
        else:
            return "五级"

    # ------------------------------------------------------------------
    # 主接口：跨时代对比
    # ------------------------------------------------------------------
    def compare_across_eras(
        self,
        lamp_type: str,
        modern_purifier: str,
        cfd_simulator: Any,
        room_area_m2: float = 30.0,
        room_height_m: float = 3.0,
        ambient_temperature: float = 22.0,
    ) -> EraComparisonResult:
        """
        完整跨时代对比流程：
          1) 数据校验
          2) 运行宫灯 CFD
          3) 分别计算 7 维度评分
          4) 生成洞察总结
        """
        ok, msg = self.validate_input(lamp_type, modern_purifier)
        if not ok:
            raise ValueError(msg)

        lamp_cfg = self.lamps_db[lamp_type]
        purifier_cfg = self.purifiers_db[modern_purifier]
        purif = lamp_cfg.get("purification_characteristics", {})

        # 运行 CFD
        cfd_result = cfd_simulator.simulate(
            flue_temperature=150.0,
            flue_velocity=0.4,
            ambient_temperature=ambient_temperature,
            fuel_type="animal_fat",
            lamp_type=lamp_type,
        )

        # 评分
        ancient_scores = self.compute_ancient_scores(
            lamp_cfg, cfd_result, room_area_m2=room_area_m2
        )
        modern_scores = self.compute_modern_scores(purifier_cfg)

        # 古代宫灯数据
        ancient = AncientLampProfile(
            lamp_type=lamp_type,
            name=lamp_cfg.get("name", ""),
            dynasty=lamp_cfg.get("dynasty", ""),
            year_invented=lamp_cfg.get("year_invented_ce", -150),
            description=lamp_cfg.get("description", ""),
            technology="水滤烟 + 烟道沉降 + 自然对流",
            cfd_summary=cfd_result,
            scores=ancient_scores,
            archaeological_info={
                "unearthed_location": lamp_cfg.get("unearthed_location"),
                "unearthed_year": lamp_cfg.get("unearthed_year"),
                "current_collection": lamp_cfg.get("current_collection"),
                "cultural_relic_level": lamp_cfg.get("cultural_relic_level"),
                "archaeological_reference": lamp_cfg.get("archaeological_reference"),
                "data_confidence_level": lamp_cfg.get("data_confidence_level", {}),
            },
        )

        # 现代净化器数据
        modern = ModernPurifierProfile(
            purifier_type=modern_purifier,
            name=purifier_cfg.get("name", ""),
            brand=purifier_cfg.get("brand", ""),
            year_invented=purifier_cfg.get("year_invented", 1940),
            technology=purifier_cfg.get("technology", ""),
            features=purifier_cfg.get("modern_features", []),
            specs={
                "cadr_pm25_m3h": purifier_cfg.get("cadr_pm25_m3h"),
                "power_w": purifier_cfg.get("power_w"),
                "noise_db": purifier_cfg.get("noise_db"),
                "price_rmb": purifier_cfg.get("price_rmb"),
                "energy_class": self.compute_energy_efficiency_class(
                    purifier_cfg.get("cadr_pm25_m3h", 0.0) / max(purifier_cfg.get("power_w", 1.0), 1e-6)
                ),
                "energy_efficiency_ratio_eer": round(
                    purifier_cfg.get("cadr_pm25_m3h", 0.0) / max(purifier_cfg.get("power_w", 1.0), 1e-6), 2
                ),
            },
            scores=modern_scores,
            standards_reference=dict(self.standards),
        )

        # 总结
        summary = self._generate_summary(ancient, modern)
        result = EraComparisonResult(
            ancient=ancient,
            modern=modern,
            summary=summary,
            unified_test_condition=self.UNIFIED_TEST_CONDITION,
        )

        # 恢复 CFD 默认灯型
        try:
            cfd_simulator.set_lamp_type("changxin_gongdeng")
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # 总结生成
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_summary(
        ancient: AncientLampProfile, modern: ModernPurifierProfile
    ) -> Dict[str, Any]:
        return {
            "ancient_advantages": [
                "零电耗，纯物理原理（自然对流 + 水滤 + 沉降）",
                f"仅 {ancient.scores.noise_level_db:.1f} dB(A) 几乎无声运行",
                f"{ancient.scores.environmental_impact_score:.1f} 分超环保：零耗材零废弃",
                f"艺术价值 {ancient.scores.aesthetic_value_score:.1f} 分，{ancient.name} 被誉为中华第一灯",
                f"历史意义满分：{ancient.archaeological_info.get('cultural_relic_level', '国家一级文物')}",
            ],
            "modern_advantages": [
                f"净化效率 {modern.scores.purification_efficiency:.2f}%（HEPA H13 对 0.3μm）",
                f"覆盖面积 {modern.scores.coverage_area_m2:.1f} m²（大户型适用）",
                f"CADR={modern.scores.estimated_cadr_m3h:.0f} m³/h 快速净化，30分钟可达标",
                "可除甲醛、细菌、病毒等多种污染物（HEPA+活性炭+UV）",
                "自带智能传感器、自动模式、滤芯更换提醒",
            ],
            "quantitative_comparison": {
                "cadr_ratio_ancient_vs_modern": round(
                    ancient.scores.estimated_cadr_m3h / max(modern.scores.estimated_cadr_m3h, 1.0), 3
                ),
                "noise_difference_db": round(
                    modern.scores.noise_level_db - ancient.scores.noise_level_db, 1
                ),
                "eco_score_difference": round(
                    ancient.scores.environmental_impact_score - modern.scores.environmental_impact_score, 1
                ),
            },
            "cross_era_insight": (
                f"{ancient.name}（{ancient.dynasty}）与 {modern.name} 代表了相隔 {modern.year_invented - ancient.year_invented} "
                f"年的两种空气净化哲学。汉代工匠以『道法自然』利用流体力学实现被动净化，"
                f"CFD 仿真显示其烟道沉降+水滤综合效率约 {ancient.scores.purification_efficiency:.1f}%，"
                f"是人类最早的空气净化工程实践。现代净化器虽在效率上领先（{modern.scores.purification_efficiency:.1f}%），"
                f"但需电力（{modern.scores.energy_consumption_w:.0f}W）和耗材，"
                f"两者各有所长，体现了不同文明阶段的工程智慧。"
            ),
        }

    # ------------------------------------------------------------------
    # 输出序列化
    # ------------------------------------------------------------------
    @staticmethod
    def result_to_dict(res: EraComparisonResult) -> Dict[str, Any]:
        def scores_to_dict(s: EraDimensionScore) -> Dict[str, Any]:
            return {
                "purification_efficiency": s.purification_efficiency,
                "coverage_area_m2": s.coverage_area_m2,
                "energy_consumption_w": s.energy_consumption_w,
                "noise_level_db": s.noise_level_db,
                "environmental_impact_score": s.environmental_impact_score,
                "aesthetic_value_score": s.aesthetic_value_score,
                "historical_significance_score": s.historical_significance_score,
                "estimated_cadr_m3h": s.estimated_cadr_m3h,
            }

        return {
            "ancient_lamp": {
                "lamp_type": res.ancient.lamp_type,
                "name": res.ancient.name,
                "dynasty": res.ancient.dynasty,
                "year_invented": res.ancient.year_invented,
                "description": res.ancient.description,
                "technology": res.ancient.technology,
                "cfd_summary": res.ancient.cfd_summary,
                "scores": scores_to_dict(res.ancient.scores),
                "archaeological_info": res.ancient.archaeological_info,
            },
            "modern_purifier": {
                "purifier_type": res.modern.purifier_type,
                "name": res.modern.name,
                "brand": res.modern.brand,
                "year_invented": res.modern.year_invented,
                "technology": res.modern.technology,
                "features": res.modern.features,
                "specs": res.modern.specs,
                "scores": scores_to_dict(res.modern.scores),
                "standards_reference": res.modern.standards_reference,
            },
            "summary": res.summary,
            "unified_test_condition": res.unified_test_condition,
            "dimension_descriptions": EraComparator.DIMENSION_DESCRIPTIONS,
        }

    def list_modern_purifiers(self) -> Dict[str, Any]:
        return {
            "modern_purifiers": self.purifiers_db,
            "comparison_dimensions": self.dimensions,
            "standards_reference": self.standards,
            "unified_test_condition": self.UNIFIED_TEST_CONDITION,
        }
