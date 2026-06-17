"""
design_comparator: 朝代环保灯设计参数对比模块
职责：封装多盏宫灯的设计参数对比、CFD结果对比、净化特性对比的纯计算逻辑
不依赖请求上下文，可被路由层和测试层直接调用。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class DesignComparisonResult:
    lamp_type: str
    name: str
    dynasty: str
    flue_geometry: Dict[str, Any] = field(default_factory=dict)
    purification_characteristics: Dict[str, Any] = field(default_factory=dict)
    cfd_result: Dict[str, Any] = field(default_factory=dict)
    air_quality_result: Dict[str, Any] = field(default_factory=dict)
    design_score: Optional[float] = None
    rank: Optional[int] = None


# ---------------------------------------------------------------------------
# 核心功能
# ---------------------------------------------------------------------------
class DesignComparator:
    """朝代灯设计对比器"""

    # 设计评分权重（各维度占比，总和=1.0）
    WEIGHTS = {
        "base_purification_efficiency": 0.30,
        "local_purification_radius_m": 0.20,
        "flue_sedimentation_ratio": 0.25,
        "water_filter_ratio": 0.15,
        "aesthetic_rating": 0.10,
    }

    # 评分基准（最大值），用于归一化
    BENCHMARKS = {
        "base_purification_efficiency": 0.80,
        "local_purification_radius_m": 4.0,
        "flue_sedimentation_ratio": 0.85,
        "water_filter_ratio": 0.95,
        "aesthetic_rating": 5.0,
    }

    def __init__(self, dynasty_lamps_cfg: Optional[Dict] = None):
        self.lamps_db = (dynasty_lamps_cfg or {}).get("dynasty_lamps", {})
        self.metrics = (dynasty_lamps_cfg or {}).get("comparison_metrics", [])

    # ------------------------------------------------------------------
    # 1. 参数列表
    # ------------------------------------------------------------------
    def list_dynasty_lamps(self) -> List[Dict[str, Any]]:
        """获取所有朝代环保灯的配置数据（考古+参数）"""
        result = []
        for lamp_type, lamp_cfg in self.lamps_db.items():
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
                "archaeological_info": self._extract_archaeological(lamp_cfg),
            })
        return result

    def get_comparison_metrics(self) -> List[Dict[str, Any]]:
        return self.metrics

    # ------------------------------------------------------------------
    # 2. CFD + AQ 对比计算
    # ------------------------------------------------------------------
    def run_design_comparison(
        self,
        lamp_types: List[str],
        cfd_simulator: Any,
        air_quality_analyzer: Any,
        flue_temperature: float = 150.0,
        flue_velocity: float = 0.4,
        ambient_temperature: float = 22.0,
        ambient_humidity: float = 50.0,
        oil_consumption: float = 1.5,
        fuel_type: Optional[str] = "animal_fat",
    ) -> Tuple[List[DesignComparisonResult], Dict[str, Any]]:
        """
        核心方法：多盏灯在相同工况下的设计对比仿真
        返回 (对比结果列表, 工况条件)
        """
        conditions = {
            "lamp_types": list(lamp_types),
            "flue_temperature": flue_temperature,
            "flue_velocity": flue_velocity,
            "ambient_temperature": ambient_temperature,
            "ambient_humidity": ambient_humidity,
            "oil_consumption": oil_consumption,
            "fuel_type": fuel_type,
        }

        results: List[DesignComparisonResult] = []
        original_lamp = None
        try:
            for lamp_type in lamp_types:
                lamp_cfg = cfd_simulator.get_lamp_config(lamp_type)
                if not lamp_cfg:
                    logger.warning(f"跳过未知灯类型: {lamp_type}")
                    continue
                cfd_result = cfd_simulator.simulate(
                    flue_temperature=flue_temperature,
                    flue_velocity=flue_velocity,
                    ambient_temperature=ambient_temperature,
                    ambient_humidity=ambient_humidity,
                    oil_consumption=oil_consumption,
                    fuel_type=fuel_type,
                    lamp_type=lamp_type,
                )
                purif = lamp_cfg.get("purification_characteristics", {})
                aq_result, _ = air_quality_analyzer.analyze(
                    indoor_pm25=50.0,
                    flue_temperature=flue_temperature,
                    flue_velocity=flue_velocity,
                    settling_efficiency=cfd_result.get("settling_efficiency", 0.0),
                    ambient_temperature=ambient_temperature,
                    ambient_humidity=ambient_humidity,
                    oil_consumption=oil_consumption,
                    air_change_rate=1.0,
                    outdoor_pm25=35.0,
                )
                res = DesignComparisonResult(
                    lamp_type=lamp_type,
                    name=lamp_cfg.get("name", ""),
                    dynasty=lamp_cfg.get("dynasty", ""),
                    flue_geometry=lamp_cfg.get("flue_geometry", {}),
                    purification_characteristics=purif,
                    cfd_result=cfd_result,
                    air_quality_result={
                        "purification_rate": aq_result["purification_rate"],
                        "avg_pm25": aq_result["avg_pm25"],
                        "aqi_level": aq_result["aqi_level"],
                        "air_change_efficiency": aq_result["air_change_efficiency"],
                    },
                )
                res.design_score = self._compute_design_score(res)
                results.append(res)
            self._rank_results(results)
        finally:
            # 恢复默认灯类型，防状态污染
            try:
                cfd_simulator.set_lamp_type("changxin_gongdeng")
            except Exception:
                pass
        return results, conditions

    # ------------------------------------------------------------------
    # 3. 设计评分算法（加权归一化评分，满分100）
    # ------------------------------------------------------------------
    def _compute_design_score(self, res: DesignComparisonResult) -> float:
        """
        根据净化特性多维度加权计算综合设计评分（0-100）
        各维度先归一化到 [0,1] 再乘以权重，最后×100
        """
        purif = res.purification_characteristics
        score = 0.0
        for metric, weight in self.WEIGHTS.items():
            raw = purif.get(metric, 0.0)
            if metric == "aesthetic_rating":
                raw = float(raw) if raw else 0.0
            bench = self.BENCHMARKS[metric]
            norm = min(max(raw / bench, 0.0), 1.0) if bench > 0 else 0.0
            score += norm * weight
        # CFD 沉降效率额外加成（0-10分）
        settling = res.cfd_result.get("settling_efficiency", 0.0)
        score += min(settling, 0.5) * 0.10
        return round(score * 100.0, 2)

    @staticmethod
    def _rank_results(results: List[DesignComparisonResult]) -> None:
        """按设计评分从高到低设置 rank 字段"""
        sorted_res = sorted(
            results, key=lambda r: r.design_score or 0.0, reverse=True
        )
        for idx, r in enumerate(sorted_res, start=1):
            r.rank = idx

    # ------------------------------------------------------------------
    # 4. 洞察生成
    # ------------------------------------------------------------------
    def generate_design_insights(self, results: List[DesignComparisonResult]) -> List[str]:
        """基于对比结果自动生成工程洞察"""
        insights = []
        if not results:
            return ["无数据可对比"]

        best = max(results, key=lambda r: r.design_score or 0.0)
        worst = min(results, key=lambda r: r.design_score or 0.0)
        best_settle = max(results, key=lambda r: r.cfd_result.get("settling_efficiency", 0.0))
        best_radius = max(
            results,
            key=lambda r: r.purification_characteristics.get("local_purification_radius_m", 0.0),
        )

        insights.append(
            f"综合设计评分最高：{best.name}（{best.dynasty}），"
            f"得分 {best.design_score}，排名第 {best.rank}"
        )
        insights.append(
            f"CFD 沉降效率最佳：{best_settle.name}，"
            f"沉降率 {round(best_settle.cfd_result.get('settling_efficiency', 0) * 100, 2)}%"
        )
        insights.append(
            f"局部净化覆盖最大：{best_radius.name}，"
            f"半径 {best_radius.purification_characteristics.get('local_purification_radius_m')} m"
        )
        if best != worst:
            insights.append(
                f"设计分差分析：{best.name} 比 {worst.name} 高 "
                f"{round((best.design_score or 0) - (worst.design_score or 0), 2)} 分，"
                f"主要差距在 {'烟道设计' if best.purification_characteristics.get('flue_sedimentation_ratio', 0) > worst.purification_characteristics.get('flue_sedimentation_ratio', 0) else '水滤效率'}"
            )
        return insights

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_archaeological(lamp_cfg: Dict) -> Dict[str, Any]:
        return {
            "unearthed_location": lamp_cfg.get("unearthed_location"),
            "unearthed_year": lamp_cfg.get("unearthed_year"),
            "current_collection": lamp_cfg.get("current_collection"),
            "cultural_relic_level": lamp_cfg.get("cultural_relic_level"),
            "archaeological_reference": lamp_cfg.get("archaeological_reference"),
            "data_confidence_level": lamp_cfg.get("data_confidence_level", {}),
        }

    @staticmethod
    def result_to_dict(res: DesignComparisonResult) -> Dict[str, Any]:
        """转换为 JSON 可序列化格式"""
        return {
            "lamp_type": res.lamp_type,
            "name": res.name,
            "dynasty": res.dynasty,
            "flue_geometry": res.flue_geometry,
            "cfd": res.cfd_result,
            "air_quality": res.air_quality_result,
            "purification_characteristics": res.purification_characteristics,
            "design_score": res.design_score,
            "rank": res.rank,
        }
