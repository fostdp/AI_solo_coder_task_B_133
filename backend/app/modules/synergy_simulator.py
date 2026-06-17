"""
synergy_simulator: 多盏宫灯宴会场景协同净化仿真模块
职责：
  1. 场景加载与参数准备（房间/网格/灯位置/算法参数）
  2. 逐灯 CFD 计算
  3. 高斯排放源初始化 + 多灯净化叠加（4种策略：min/max/mean/sum）
  4. 协同指数计算（多灯 vs 单灯基线）
  5. 调试日志与算法文档（与 air_quality_analyzer 配合）
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class SynergyPerLampData:
    lamp_index: int
    lamp_type: str
    world_position: Tuple[float, float, float]
    grid_position: Tuple[int, int, int]
    cfd_result: Dict[str, Any] = field(default_factory=dict)
    settling_efficiency: float = 0.0
    local_purification_radius_m: float = 2.5
    affected_grid_points: int = 0
    avg_concentration_in_radius: float = 0.0
    min_concentration_in_radius: float = 0.0


@dataclass
class SynergySimulationResult:
    scene_key: str
    scene_name: str
    room_geometry: Dict[str, float]
    grid_resolution: Dict[str, int]
    lamp_positions: List[Dict]
    algorithm_parameters: Dict[str, Any]
    per_lamp_data: List[SynergyPerLampData]
    banquet_aq_result: Dict[str, Any]
    single_lamp_baseline: Dict[str, Any]
    synergy_analysis: Dict[str, Any]
    grid_data_3d: Optional[np.ndarray] = None
    grid_data_flat: List[Dict] = field(default_factory=list)
    overlap_strategy: str = "min"


# ---------------------------------------------------------------------------
# 协同仿真器
# ---------------------------------------------------------------------------
class SynergySimulator:
    """多盏宫灯宴会场景协同净化仿真器"""

    # 叠加策略选项说明
    OVERLAP_STRATEGIES = {
        "min": "取所有可达灯中的最低浓度（最乐观估计：最强净化主导）",
        "max": "取所有可达灯中的最高浓度（最保守估计：最弱净化主导）",
        "mean": "所有可达灯净化浓度的算术平均（折中估计）",
        "sum": "所有灯净化量线性叠加（假设各灯独立、净化量可累加）",
    }

    def __init__(self, banquet_scenes_cfg: Optional[Dict] = None):
        self.scenes_cfg = banquet_scenes_cfg or {}
        self.scenes = self.scenes_cfg.get("scenes", {})
        self.default_scene_key = self.scenes_cfg.get("default_scene", "royal_banquet")

    # ------------------------------------------------------------------
    # 1. 场景列表
    # ------------------------------------------------------------------
    def list_banquet_scenes(self) -> Dict[str, Any]:
        """返回所有宴会场景配置（含算法参数说明）"""
        return self.scenes_cfg

    def get_scene(self, scene_key: str) -> Optional[Dict]:
        return self.scenes.get(scene_key)

    # ------------------------------------------------------------------
    # 2. 场景准备：apply 到 air_quality_analyzer
    # ------------------------------------------------------------------
    @staticmethod
    def apply_scene(
        aq_analyzer: Any, scene_cfg: Dict,
    ) -> Tuple[Dict, Dict, List[Dict], Dict]:
        """
        把场景几何、网格、灯位置、算法参数应用到 AQ 分析器。
        返回 (room_geometry, grid_resolution, lamp_positions, algorithm_params)
        """
        rg = scene_cfg["room_geometry"]
        gr = scene_cfg["grid_resolution"]
        lp = scene_cfg["lamp_positions"]
        dp = scene_cfg.get("default_parameters", {})
        ap = scene_cfg.get("algorithm_parameters", {})
        aq_analyzer.set_scene_override(
            room_size_x=rg["room_size_x_m"],
            room_size_y=rg["room_size_y_m"],
            room_size_z=rg["room_size_z_m"],
            nx=gr["nx"],
            ny=gr["ny"],
            nz=gr["nz"],
            lamp_positions=lp,
        )
        return rg, gr, lp, {**dp, **ap}

    # ------------------------------------------------------------------
    # 3. 逐灯 CFD
    # ------------------------------------------------------------------
    def run_per_lamp_cfd(
        self,
        cfd_simulator: Any,
        lamp_positions: List[Dict],
        flue_temperature_c: float,
        flue_velocity_ms: float,
        ambient_temperature_c: float,
        ambient_humidity_percent: float,
        fuel_type: Optional[str] = "animal_fat",
    ) -> Tuple[List[Dict], List[float], List[float], List[float]]:
        """
        为每盏灯跑一次 CFD 仿真。
        返回 (per_lamp_cfd_list, settling_efficiencies, flue_velocities, lamp_emissions_ug)
        """
        per_lamp_cfd = []
        settling_efficiencies = []
        flue_velocities = []
        lamp_emissions = []
        for lp in lamp_positions:
            lamp_type = lp.get("lamp_type", "changxin_gongdeng")
            cfd_res = cfd_simulator.simulate(
                flue_temperature=flue_temperature_c,
                flue_velocity=flue_velocity_ms,
                ambient_temperature=ambient_temperature_c,
                ambient_humidity=ambient_humidity_percent,
                oil_consumption=1.5,
                fuel_type=fuel_type,
                lamp_type=lamp_type,
            )
            per_lamp_cfd.append({
                "lamp_type": lamp_type,
                "position": lp,
                "cfd": cfd_res,
            })
            se = cfd_res.get("settling_efficiency", 0.0)
            settling_efficiencies.append(se)
            flue_velocities.append(cfd_res.get("outlet_velocity", flue_velocity_ms))
            # 排放 = 基准 10 μg + (1-沉降率)×20 μg  （沉降越好则排放越少）
            lamp_emissions.append(10.0 + (1.0 - se) * 20.0)
        return per_lamp_cfd, settling_efficiencies, flue_velocities, lamp_emissions

    # ------------------------------------------------------------------
    # 4. 主接口：完整协同仿真
    # ------------------------------------------------------------------
    def run_synergy_simulation(
        self,
        cfd_simulator: Any,
        air_quality_analyzer: Any,
        scene_key: str,
        base_pm25_ugm3: float = 45.0,
        air_change_rate_ach: float = 0.5,
        outdoor_pm25_ugm3: float = 35.0,
        ambient_temperature_c: float = 22.0,
        ambient_humidity_percent: float = 50.0,
        flue_temperature_c: float = 150.0,
        flue_velocity_ms: float = 0.4,
        fuel_type: Optional[str] = "animal_fat",
        overlap_strategy_override: Optional[str] = None,
        debug_log: bool = False,
    ) -> SynergySimulationResult:
        """
        完整协同净化仿真流程：
        1) 加载场景 → 2) 应用到AQ → 3) 逐灯CFD → 4) 宴会AQ仿真
          → 5) 单灯基线 → 6) 协同分析 → 7) 恢复默认场景
        """
        scene = self.scenes.get(scene_key)
        if not scene:
            raise ValueError(f"未知场景: {scene_key}")

        try:
            # (1)(2)
            rg, gr, lp, algo_params = self.apply_scene(air_quality_analyzer, scene)
            overlap_strategy = overlap_strategy_override or algo_params.get(
                "overlap_strategy", "min"
            )
            if debug_log:
                logger.info(
                    f"[Synergy] 场景={scene_key} 房间={rg} 网格={gr} "
                    f"灯数={len(lp)} 叠加策略={overlap_strategy}"
                )

            # (3) 逐灯 CFD
            per_lamp_cfd, settling_effs, flue_vels, lamp_emissions = self.run_per_lamp_cfd(
                cfd_simulator, lp,
                flue_temperature_c=flue_temperature_c,
                flue_velocity_ms=flue_velocity_ms,
                ambient_temperature_c=ambient_temperature_c,
                ambient_humidity_percent=ambient_humidity_percent,
                fuel_type=fuel_type,
            )

            # (4) 宴会场景 AQ 仿真（内部会调用 apply_multi_lamp_purification）
            banquet_aq, grid_3d = air_quality_analyzer.analyze_banquet(
                base_pm25=base_pm25_ugm3,
                lamp_emissions_ug=lamp_emissions,
                settling_efficiencies=settling_effs,
                flue_velocities=flue_vels,
                ambient_temperature=ambient_temperature_c,
                ambient_humidity=ambient_humidity_percent,
                air_change_rate=air_change_rate_ach,
                outdoor_pm25=outdoor_pm25_ugm3,
                overlap_strategy=overlap_strategy,
                debug_log=debug_log,
            )

            # (5) 单灯基线（一盏灯放原点，其他条件相同）
            baseline_aq, _ = air_quality_analyzer.analyze(
                indoor_pm25=base_pm25_ugm3,
                flue_temperature=flue_temperature_c,
                flue_velocity=flue_velocity_ms,
                settling_efficiency=settling_effs[0] if settling_effs else 0.0,
                ambient_temperature=ambient_temperature_c,
                ambient_humidity=ambient_humidity_percent,
                oil_consumption=1.5,
                air_change_rate=air_change_rate_ach,
                outdoor_pm25=outdoor_pm25_ugm3,
            )
            baseline_simple = {
                "purification_rate": baseline_aq["purification_rate"],
                "avg_pm25": baseline_aq["avg_pm25"],
                "aqi_level": baseline_aq["aqi_level"],
            }

            # (6) 协同分析
            synergy = self._compute_synergy_analysis(
                banquet_aq, baseline_simple, len(lp), overlap_strategy
            )

            # 每灯详细数据（网格坐标/影响格点数等）
            per_lamp_data = self._build_per_lamp_details(
                lp, per_lamp_cfd, air_quality_analyzer, grid_3d
            )

            # 扁平化网格（3D → List[Dict]）
            grid_flat = self._flatten_grid(grid_3d, air_quality_analyzer)

            result = SynergySimulationResult(
                scene_key=scene_key,
                scene_name=scene.get("name", scene_key),
                room_geometry=rg,
                grid_resolution=gr,
                lamp_positions=lp,
                algorithm_parameters={**algo_params, "overlap_strategy": overlap_strategy},
                per_lamp_data=per_lamp_data,
                banquet_aq_result=banquet_aq,
                single_lamp_baseline=baseline_simple,
                synergy_analysis=synergy,
                grid_data_3d=grid_3d,
                grid_data_flat=grid_flat,
                overlap_strategy=overlap_strategy,
            )
        finally:
            # (7) 恢复默认场景
            self._restore_default_scene(air_quality_analyzer)
            # 恢复默认灯型
            try:
                cfd_simulator.set_lamp_type("changxin_gongdeng")
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # 5. 协同指数
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_synergy_analysis(
        banquet: Dict,
        baseline: Dict,
        num_lamps: int,
        strategy: str,
    ) -> Dict[str, Any]:
        """
        协同净化效果分析：多灯 vs 单灯基线
        synergy_index = 多灯净化率 / (单灯净化率 × 灯数)
          > 1: 协同增益（1+1>2）  < 1: 边际递减（1+1<2）
        """
        br = max(0.0, banquet.get("purification_rate", 0.0))
        sr = max(0.0, baseline.get("purification_rate", 0.0))
        bavg = max(0.0, banquet.get("avg_pm25", 0.0))
        savg = max(0.0, baseline.get("avg_pm25", 0.0))

        rate_delta = max(0.0, br - sr)
        pm25_delta = max(0.0, savg - bavg)
        synergy_index = (
            round(br / max(sr * num_lamps, 1e-6), 3)
            if num_lamps > 0 else 0.0
        )
        return {
            "purification_rate_improvement_pct_points": round(rate_delta * 100, 2),
            "avg_pm25_reduction_ugm3": round(pm25_delta, 2),
            "num_lamps": num_lamps,
            "overlap_strategy": strategy,
            "overlap_strategy_description": SynergySimulator.OVERLAP_STRATEGIES.get(
                strategy, "未知"
            ),
            "synergy_index": synergy_index,
            "synergy_interpretation": (
                "协同增益显著（1+1>2）" if synergy_index > 1.0 else
                "协同边际递减（覆盖重叠，1+1<2）"
            ),
            "conclusion": (
                f"{num_lamps} 盏灯{strategy}策略协同净化："
                f"净化速率+{round(rate_delta * 100, 2)}pct，"
                f"PM2.5下降{round(pm25_delta, 2)}μg/m³，"
                f"协同指数={synergy_index}"
            ),
        }

    # ------------------------------------------------------------------
    # 6. 每灯详细元数据
    # ------------------------------------------------------------------
    @staticmethod
    def _build_per_lamp_details(
        lamp_positions: List[Dict],
        per_lamp_cfd: List[Dict],
        aq: Any,
        grid: np.ndarray,
    ) -> List[SynergyPerLampData]:
        """从宴会结果中提取每盏灯的详细影响信息"""
        result = []
        for idx, lp in enumerate(lamp_positions):
            wx = lp.get("x_m", 0.0)
            wy = lp.get("y_m", 0.0)
            wz = lp.get("z_m", 0.5)
            gi, gj, gk = aq._world_to_grid(wx, wy, wz)
            cfd = per_lamp_cfd[idx] if idx < len(per_lamp_cfd) else {}
            radius = aq.purif_radius if hasattr(aq, "purif_radius") else 2.5
            se = cfd.get("cfd", {}).get("settling_efficiency", 0.0)

            # 统计影响格点数
            count = 0
            vals = []
            for i in range(aq.nx):
                for j in range(aq.ny):
                    for k in range(aq.nz):
                        d = aq._grid_distance(i, j, k, gi, gj, gk)
                        if d <= radius:
                            count += 1
                            vals.append(float(grid[i, j, k]))
            avg_c = float(np.mean(vals)) if vals else 0.0
            min_c = float(np.min(vals)) if vals else 0.0

            result.append(SynergyPerLampData(
                lamp_index=idx + 1,
                lamp_type=lp.get("lamp_type", "changxin_gongdeng"),
                world_position=(wx, wy, wz),
                grid_position=(gi, gj, gk),
                cfd_result=cfd.get("cfd", {}),
                settling_efficiency=se,
                local_purification_radius_m=radius,
                affected_grid_points=count,
                avg_concentration_in_radius=round(avg_c, 4),
                min_concentration_in_radius=round(min_c, 4),
            ))
        return result

    # ------------------------------------------------------------------
    # 7. 网格扁平化 + 默认场景恢复
    # ------------------------------------------------------------------
    @staticmethod
    def _flatten_grid(grid: np.ndarray, aq: Any) -> List[Dict]:
        flat = []
        for i in range(aq.nx):
            for j in range(aq.ny):
                for k in range(aq.nz):
                    wx, wy, wz = aq._grid_to_world(i, j, k)
                    flat.append({
                        "grid_x": i, "grid_y": j, "grid_z": k,
                        "world_x": round(wx, 3), "world_y": round(wy, 3), "world_z": round(wz, 3),
                        "concentration": round(float(grid[i, j, k]), 4),
                    })
        return flat

    def _restore_default_scene(self, aq_analyzer: Any) -> None:
        """把 AQ 分析器恢复为默认场景，避免状态污染"""
        scene = self.scenes.get(self.default_scene_key, {})
        rg_def = scene.get("room_geometry", {
            "room_size_x_m": 10.0, "room_size_y_m": 8.0, "room_size_z_m": 3.5,
        })
        gr_def = scene.get("grid_resolution", {"nx": 5, "ny": 5, "nz": 5})
        lp_def = scene.get("lamp_positions", [])
        aq_analyzer.set_scene_override(
            room_size_x=rg_def.get("room_size_x_m", 10.0),
            room_size_y=rg_def.get("room_size_y_m", 8.0),
            room_size_z=rg_def.get("room_size_z_m", 3.5),
            nx=gr_def.get("nx", 5),
            ny=gr_def.get("ny", 5),
            nz=gr_def.get("nz", 5),
            lamp_positions=lp_def,
        )

    # ------------------------------------------------------------------
    # 输出序列化
    # ------------------------------------------------------------------
    @staticmethod
    def result_to_dict(res: SynergySimulationResult) -> Dict[str, Any]:
        return {
            "scene_key": res.scene_key,
            "scene_name": res.scene_name,
            "room_geometry": res.room_geometry,
            "grid_resolution": res.grid_resolution,
            "lamp_positions": res.lamp_positions,
            "algorithm_parameters": res.algorithm_parameters,
            "per_lamp_cfd": [
                {
                    "lamp_index": p.lamp_index,
                    "lamp_type": p.lamp_type,
                    "world_position": {
                        "x": p.world_position[0],
                        "y": p.world_position[1],
                        "z": p.world_position[2],
                    },
                    "grid_position": {
                        "i": p.grid_position[0],
                        "j": p.grid_position[1],
                        "k": p.grid_position[2],
                    },
                    "cfd": p.cfd_result,
                    "settling_efficiency": p.settling_efficiency,
                    "local_purification_radius_m": p.local_purification_radius_m,
                    "affected_grid_points": p.affected_grid_points,
                    "avg_concentration_in_radius": p.avg_concentration_in_radius,
                    "min_concentration_in_radius": p.min_concentration_in_radius,
                }
                for p in res.per_lamp_data
            ],
            "banquet_result": res.banquet_aq_result,
            "single_lamp_baseline": res.single_lamp_baseline,
            "synergy_analysis": res.synergy_analysis,
            "grid_data": res.grid_data_flat,
        }
