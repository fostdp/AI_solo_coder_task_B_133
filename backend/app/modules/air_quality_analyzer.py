"""
air_quality_analyzer 模块：PM2.5扩散与净化效果评估

职责：
  1. 订阅 CFD_RESULT
  2. 基于 JSON 外置配置求解对流扩散方程
     ∂C/∂t = D·∇²C - u·∇C - λ·(C - C_out)
  3. 计算宫灯净化效果、空气质量等级、健康风险
  4. 结果持久化 air_quality_analysis 与 pm25_grid 超表
  5. 发布 AIR_QUALITY_RESULT（含完整网格和评估指标，供告警使用）

订阅：CFD_RESULT
发布：AIR_QUALITY_RESULT
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from ..bus import MessageBus, CFD_RESULT, AIR_QUALITY_INPUT, AIR_QUALITY_RESULT
from ..models.lamp import AirQualityAnalysis, PM25Grid
from ..config_loader import load_air_quality_config, load_dynasty_lamps_config, load_banquet_scenes_config

logger = logging.getLogger(__name__)


class AirQualityAnalyzer:
    def __init__(self, db: AsyncSession, bus: MessageBus, override: Optional[Dict[str, Any]] = None):
        self.db = db
        self.bus = bus
        cfg = load_air_quality_config()
        if override:
            for section, values in override.items():
                if isinstance(values, dict):
                    cfg.setdefault(section, {}).update(values)
                else:
                    cfg[section] = values
        self.cfg = cfg

        # 房间几何
        rg = cfg["room_geometry"]
        self.room_size_x = rg["room_size_x_m"]
        self.room_size_y = rg["room_size_y_m"]
        self.room_size_z = rg["room_size_z_m"]
        self.lamp_pos = np.array([
            rg["lamp_position_x_m"], rg["lamp_position_y_m"], rg["lamp_position_z_m"]
        ], dtype=np.float64)

        # 网格
        gr = cfg["grid_resolution"]
        self.nx = gr["nx"]
        self.ny = gr["ny"]
        self.nz = gr["nz"]

        # 扩散模型
        dm = cfg["diffusion_model"]
        self.D_base = dm["base_diffusion_coefficient_m2s"]
        self.T_ref = dm["reference_temperature_k"]
        self.T_exp = dm["temperature_exponent"]
        self.humidity_corr = dm["humidity_correction_coefficient"]
        self.humidity_ref = dm["humidity_reference_percent"]
        self.diff_steps = dm["numerical_diffusion_steps"]
        self.dt = dm["dt_s"]

        # 通风
        v = cfg["ventilation"]
        self.air_change_rate = v["default_air_change_rate_ach"]
        self.outdoor_pm25 = v["default_outdoor_pm25_ugm3"]
        self._inlet_ratio = np.array([
            v["inlet_position"]["x_ratio"],
            v["inlet_position"]["y_ratio"],
            v["inlet_position"]["z_ratio"],
        ])
        self._outlet_ratio = np.array([
            v["outlet_position"]["x_ratio"],
            v["outlet_position"]["y_ratio"],
            v["outlet_position"]["z_ratio"],
        ])
        self._vel_in_w = v["inlet_velocity_weight"]
        self._vel_out_w = v["outlet_velocity_weight"]
        self._inlet_sigma = v["inlet_gaussian_sigma"]
        self._max_vel = v["max_velocity_magnitude_ms"]

        # 净化
        p = cfg["purification_model"]
        self.base_purification = p["base_purification_efficiency"]
        self.w_settle = p["settling_weight"]
        self.w_vel = p["velocity_weight"]
        self.min_settle = p["min_settling_threshold"]
        self.min_vel = p["min_velocity_threshold_ms"]
        self.purif_radius = p["local_purification_radius_m"]
        self.purif_strength = p["local_purification_strength"]
        self.decay_exp = p["decay_exponent"]

        # 排放
        e = cfg["emission_model"]
        self.base_emission = e["base_emission_rate_ug_per_kg_oil"]
        self.temp_corr_coef = e["emission_temperature_correction_coefficient"]
        self.temp_ref_c = e["emission_temperature_reference_c"]
        self.lamp_sigma = e["lamp_gaussian_sigma"]
        self.lamp_src_strength = e["lamp_source_strength"]

        # AQI阈值
        self.aqi = cfg["aqi_thresholds"]

        # 计算物理网格坐标和速度场
        self._grid_coords = self._compute_grid_coordinates()
        self._velocity_field = self._calculate_velocity_field()
        self._grid_index_to_world = self._compute_grid_index_to_world()
        self._bus_bound = False

    # ------------------------------------------------------------------
    # 总线绑定
    # ------------------------------------------------------------------
    async def bind_to_bus(self):
        if self._bus_bound:
            return
        await self.bus.subscribe(CFD_RESULT, self._on_cfd_result)
        self._bus_bound = True

    async def _on_cfd_result(self, payload: Dict[str, Any]):
        try:
            lamp_id = payload.get("lamp_id", 0)
            t_str = payload.get("time", datetime.now().isoformat())
            t = datetime.fromisoformat(t_str) if isinstance(t_str, str) else t_str
            cfd = payload.get("cfd", {})
            ach = payload.get("air_change_rate", self.air_change_rate)
            outdoor = payload.get("outdoor_pm25", self.outdoor_pm25)

            result, grid3d = self.analyze(
                indoor_pm25=payload["indoor_pm25"],
                flue_temperature=payload["flue_temperature"],
                flue_velocity=payload["flue_velocity"],
                settling_efficiency=cfd.get("settling_efficiency", 0.0),
                ambient_temperature=payload.get("ambient_temperature", 22.0),
                ambient_humidity=payload.get("ambient_humidity", 50.0),
                oil_consumption=payload.get("oil_consumption", 0.0),
                air_change_rate=ach,
                outdoor_pm25=outdoor,
            )

            # 持久化（失败不阻断管线）
            try:
                stmt_aq = insert(AirQualityAnalysis).values(
                    time=t,
                    lamp_id=lamp_id,
                    pm25_diffusion_coeff=result["pm25_diffusion_coeff"],
                    pm25_gradient_x=result["pm25_gradient_x"],
                    pm25_gradient_y=result["pm25_gradient_y"],
                    pm25_gradient_z=result["pm25_gradient_z"],
                    purification_rate=result["purification_rate"],
                    air_change_efficiency=result["air_change_efficiency"],
                    aqi_level=result["aqi_level"],
                    health_risk=result["health_risk"],
                )
                await self.db.execute(stmt_aq)

                # 网格批量入库
                grid_rows = []
                for i in range(self.nx):
                    for j in range(self.ny):
                        for k in range(self.nz):
                            wx, wy, wz = self._grid_to_world(i, j, k)
                            grid_rows.append({
                                "time": t,
                                "lamp_id": lamp_id,
                                "grid_x": i,
                                "grid_y": j,
                                "grid_z": k,
                                "world_x": wx,
                                "world_y": wy,
                                "world_z": wz,
                                "pm25_concentration": round(float(grid3d[i, j, k]), 4),
                            })
                if grid_rows:
                    await self.db.execute(insert(PM25Grid), grid_rows)
                await self.db.commit()
            except Exception as db_e:
                logger.warning(f"[air_quality_analyzer] 持久化失败 (DB未就绪？): {db_e}")

            # 发布给告警模块
            out_payload = {
                "correlation_id": payload.get("correlation_id"),
                "lamp_id": lamp_id,
                "time": payload["time"],
                **payload,
                "air_quality": result,
                "grid_shape": list(grid3d.shape),
                "grid_flat": grid3d.flatten().tolist(),
            }
            await self.bus.publish(AIR_QUALITY_RESULT, out_payload)
            logger.info(f"[air_quality] lamp#{lamp_id} avgPM25={np.mean(grid3d):.1f} "
                        f"purif={result['purification_rate']*100:.1f}% AQI={result['aqi_level']}")
        except Exception as e:
            logger.exception(f"[air_quality] 处理失败: {e}")
            await self.db.rollback()

    # ------------------------------------------------------------------
    # 坐标与速度场
    # ------------------------------------------------------------------
    def _compute_grid_coordinates(self) -> Dict[str, np.ndarray]:
        xs = np.linspace(0, self.room_size_x, self.nx)
        ys = np.linspace(0, self.room_size_y, self.ny)
        zs = np.linspace(0, self.room_size_z, self.nz)
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        return {"x": xs, "y": ys, "z": zs, "X": X, "Y": Y, "Z": Z}

    def _compute_grid_index_to_world(self):
        return

    def _grid_to_world(self, i: int, j: int, k: int) -> Tuple[float, float, float]:
        if self.nx > 1:
            x = (i / (self.nx - 1)) * self.room_size_x - self.room_size_x / 2
        else:
            x = 0.0
        if self.ny > 1:
            y = (j / (self.ny - 1)) * self.room_size_y - self.room_size_y / 2
        else:
            y = 0.0
        if self.nz > 1:
            z = (k / (self.nz - 1)) * self.room_size_z
        else:
            z = self.room_size_z / 2
        return (x, y, z)

    def set_ventilation_parameters(self, air_change_rate: float, outdoor_pm25: float):
        self.air_change_rate = air_change_rate
        self.outdoor_pm25 = outdoor_pm25
        self._velocity_field = self._calculate_velocity_field()

    def _calculate_velocity_field(self) -> np.ndarray:
        """基于势流模型的三维速度场"""
        vel = np.zeros((self.nx, self.ny, self.nz, 3), dtype=np.float64)
        if self.air_change_rate <= 0:
            return vel
        ach_per_s = self.air_change_rate / 3600.0
        inlet_world = np.array([
            self._inlet_ratio[0] * self.room_size_x - self.room_size_x / 2,
            self._inlet_ratio[1] * self.room_size_y - self.room_size_y / 2,
            self._inlet_ratio[2] * self.room_size_z,
        ])
        outlet_world = np.array([
            self._outlet_ratio[0] * self.room_size_x - self.room_size_x / 2,
            self._outlet_ratio[1] * self.room_size_y - self.room_size_y / 2,
            self._outlet_ratio[2] * self.room_size_z,
        ])
        room_volume = self.room_size_x * self.room_size_y * self.room_size_z
        flow_rate = ach_per_s * room_volume
        inlet_area = 0.5
        base_inlet_speed = flow_rate / max(inlet_area, 1e-6)

        for i in range(self.nx):
            for j in range(self.ny):
                for k in range(self.nz):
                    wx, wy, wz = self._grid_to_world(i, j, k)
                    cell = np.array([wx, wy, wz])
                    # 入口送风（高斯衰减，指向出口方向）
                    to_outlet = outlet_world - inlet_world
                    to_outlet_dir = to_outlet / (np.linalg.norm(to_outlet) + 1e-9)
                    dist_inlet = np.linalg.norm(cell - inlet_world)
                    gauss_in = np.exp(-0.5 * (dist_inlet / max(self._inlet_sigma, 1e-6)) ** 2)
                    v_in = self._vel_in_w * base_inlet_speed * gauss_in * to_outlet_dir

                    # 出口抽吸（1/r²衰减）
                    to_cell = cell - outlet_world
                    d_out = max(np.linalg.norm(to_cell), 0.5)
                    suction_dir = -to_cell / d_out
                    v_out = (
                        self._vel_out_w
                        * flow_rate
                        * suction_dir
                        / (4.0 * np.pi * d_out ** 2 + 1e-6)
                    )
                    v = v_in + v_out
                    v_norm = np.linalg.norm(v)
                    if v_norm > self._max_vel:
                        v = v * (self._max_vel / v_norm)
                    vel[i, j, k, :] = v
        return vel

    # ------------------------------------------------------------------
    # 扩散系数
    # ------------------------------------------------------------------
    def calculate_diffusion_coefficient(
        self,
        temperature_c: float,
        humidity: float,
        atmospheric_pressure_pa: float = 101325.0,
    ) -> float:
        T_K = temperature_c + 273.15
        D_T = self.D_base * (T_K / self.T_ref) ** self.T_exp
        humidity_factor = 1.0 + self.humidity_corr * (humidity - self.humidity_ref)
        D = D_T * (101325.0 / atmospheric_pressure_pa) * humidity_factor
        return max(D, 1e-8)

    # ------------------------------------------------------------------
    # 对流扩散方程求解
    # ------------------------------------------------------------------
    def _calculate_convective_term(
        self, C: np.ndarray, vf: np.ndarray, dx: float, dy: float, dz: float
    ) -> np.ndarray:
        """一阶迎风格式计算 u·∇C"""
        conv = np.zeros_like(C)
        nx, ny, nz = C.shape
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    u = vf[i, j, k, 0]
                    dcdx = 0.0
                    if u > 0:
                        if i > 0:
                            dcdx = (C[i, j, k] - C[i - 1, j, k]) / max(dx, 1e-9)
                    else:
                        if i < nx - 1:
                            dcdx = (C[i + 1, j, k] - C[i, j, k]) / max(dx, 1e-9)
                    v = vf[i, j, k, 1]
                    dcdy = 0.0
                    if v > 0:
                        if j > 0:
                            dcdy = (C[i, j, k] - C[i, j - 1, k]) / max(dy, 1e-9)
                    else:
                        if j < ny - 1:
                            dcdy = (C[i, j + 1, k] - C[i, j, k]) / max(dy, 1e-9)
                    w = vf[i, j, k, 2]
                    dcdz = 0.0
                    if w > 0:
                        if k > 0:
                            dcdz = (C[i, j, k] - C[i, j, k - 1]) / max(dz, 1e-9)
                    else:
                        if k < nz - 1:
                            dcdz = (C[i, j, k + 1] - C[i, j, k]) / max(dz, 1e-9)
                    conv[i, j, k] = u * dcdx + v * dcdy + w * dcdz
        return conv

    def _apply_ventilation_boundary_conditions(
        self, field: np.ndarray
    ) -> np.ndarray:
        out = field.copy()
        # 入口格点设为室外PM2.5
        gx = min(max(round(self._inlet_ratio[0] * (self.nx - 1)), 0), self.nx - 1)
        gy = min(max(round(self._inlet_ratio[1] * (self.ny - 1)), 0), self.ny - 1)
        gz = min(max(round(self._inlet_ratio[2] * (self.nz - 1)), 0), self.nz - 1)
        out[gx, gy, gz] = self.outdoor_pm25
        return out

    def solve_diffusion(
        self,
        initial_field: np.ndarray,
        D: float,
        temperature_c: float = 22.0,
        air_change_rate: Optional[float] = None,
    ) -> np.ndarray:
        """显式Euler求解对流扩散方程"""
        if air_change_rate is not None:
            self.air_change_rate = air_change_rate
            self._velocity_field = self._calculate_velocity_field()

        C = initial_field.copy()
        dx = self.room_size_x / max(self.nx - 1, 1)
        dy = self.room_size_y / max(self.ny - 1, 1)
        dz = self.room_size_z / max(self.nz - 1, 1)
        lambda_vent = self.air_change_rate / 60.0  # 转换为 1/min
        C_out = self.outdoor_pm25
        vf = self._velocity_field

        for _ in range(self.diff_steps):
            # 扩散（7点中心差分）
            lap = np.zeros_like(C)
            C_pad = np.pad(C, 1, mode="edge")
            lap = (
                (C_pad[2:, 1:-1, 1:-1] - 2 * C_pad[1:-1, 1:-1, 1:-1] + C_pad[:-2, 1:-1, 1:-1]) / max(dx ** 2, 1e-12)
                + (C_pad[1:-1, 2:, 1:-1] - 2 * C_pad[1:-1, 1:-1, 1:-1] + C_pad[1:-1, :-2, 1:-1]) / max(dy ** 2, 1e-12)
                + (C_pad[1:-1, 1:-1, 2:] - 2 * C_pad[1:-1, 1:-1, 1:-1] + C_pad[1:-1, 1:-1, :-2]) / max(dz ** 2, 1e-12)
            )
            diffusion_term = D * lap
            convection_term = self._calculate_convective_term(C, vf, dx, dy, dz)
            ventilation_term = -lambda_vent * (C - C_out)
            dC_dt = diffusion_term - convection_term + ventilation_term
            C = C + self.dt * dC_dt
            C = np.clip(C, 0, None)
            C = self._apply_ventilation_boundary_conditions(C)
        return C

    # ------------------------------------------------------------------
    # 初始化与净化
    # ------------------------------------------------------------------
    def initialize_concentration_field(
        self,
        base_pm25: float,
        lamp_emission_ug: float,
    ) -> np.ndarray:
        C = np.full((self.nx, self.ny, self.nz), float(base_pm25), dtype=np.float64)
        if lamp_emission_ug > 0:
            lamp_gx = int(round(self.lamp_pos[0] / self.room_size_x * (self.nx - 1)))
            lamp_gy = int(round(self.lamp_pos[1] / self.room_size_y * (self.ny - 1)))
            lamp_gz = int(round(self.lamp_pos[2] / self.room_size_z * (self.nz - 1)))
            lamp_gx = np.clip(lamp_gx, 0, self.nx - 1)
            lamp_gy = np.clip(lamp_gy, 0, self.ny - 1)
            lamp_gz = np.clip(lamp_gz, 0, self.nz - 1)
            sigma_sq = (self.lamp_sigma / max(self.room_size_x, 1)) ** 2 * self.nx ** 2
            for i in range(self.nx):
                for j in range(self.ny):
                    for k in range(self.nz):
                        dist_sq = (i - lamp_gx) ** 2 + (j - lamp_gy) ** 2 + (k - lamp_gz) ** 2
                        gauss = np.exp(-dist_sq / (2 * sigma_sq + 1e-12))
                        C[i, j, k] += self.lamp_src_strength * lamp_emission_ug * gauss
        return C

    def apply_purification(
        self,
        field: np.ndarray,
        settling_efficiency: float,
        flue_velocity: float,
    ) -> Tuple[np.ndarray, float, Dict[str, float]]:
        before = float(np.mean(field))
        settling_factor = min(max(settling_efficiency / max(self.min_settle, 1e-9), 0.0), 1.0)
        velocity_factor = min(max(flue_velocity / max(self.min_vel, 1e-9), 0.0), 1.0)
        purification_efficiency = self.base_purification * (
            self.w_settle * settling_factor + self.w_vel * velocity_factor
        )
        lamp_gx = int(round(self.lamp_pos[0] / self.room_size_x * (self.nx - 1)))
        lamp_gy = int(round(self.lamp_pos[1] / self.room_size_y * (self.ny - 1)))
        lamp_gz = int(round(self.lamp_pos[2] / self.room_size_z * (self.nz - 1)))
        lamp_gx = np.clip(lamp_gx, 0, self.nx - 1)
        lamp_gy = np.clip(lamp_gy, 0, self.ny - 1)
        lamp_gz = np.clip(lamp_gz, 0, self.nz - 1)

        purified = field.copy()
        for i in range(self.nx):
            for j in range(self.ny):
                for k in range(self.nz):
                    wx, wy, wz = self._grid_to_world(i, j, k)
                    dist = np.sqrt(
                        (wx - (self.lamp_pos[0] - self.room_size_x / 2)) ** 2
                        + (wy - (self.lamp_pos[1] - self.room_size_y / 2)) ** 2
                        + (wz - self.lamp_pos[2]) ** 2
                    )
                    if dist <= self.purif_radius:
                        falloff = (1 - dist / self.purif_radius) ** self.decay_exp
                        local_eff = self.purif_strength * purification_efficiency * falloff
                        purified[i, j, k] = field[i, j, k] * (1 - local_eff)
        after = float(np.mean(purified))
        purification_rate = max(0.0, (before - after) / max(before, 1e-9))
        details = {
            "purification_efficiency": purification_efficiency,
            "settling_factor": settling_factor,
            "velocity_factor": velocity_factor,
            "avg_before": before,
            "avg_after": after,
        }
        return purified, purification_rate, details

    # ------------------------------------------------------------------
    # AQI评估
    # ------------------------------------------------------------------
    def evaluate_aqi(self, avg_concentration: float) -> Tuple[str, str]:
        if avg_concentration <= self.aqi["excellent_max"]:
            return "EXCELLENT", "NONE"
        elif avg_concentration <= self.aqi["good_max"]:
            return "GOOD", "LOW"
        elif avg_concentration <= self.aqi["light_pollution_max"]:
            return "LIGHT_POLLUTION", "MODERATE"
        elif avg_concentration <= self.aqi["moderate_pollution_max"]:
            return "MODERATE_POLLUTION", "HIGH"
        elif avg_concentration <= self.aqi["heavy_pollution_max"]:
            return "HEAVY_POLLUTION", "VERY_HIGH"
        return "SEVERE_POLLUTION", "EXTREME"

    # ------------------------------------------------------------------
    # 主分析入口
    # ------------------------------------------------------------------
    def analyze(
        self,
        indoor_pm25: float,
        flue_temperature: float,
        flue_velocity: float,
        settling_efficiency: float,
        ambient_temperature: float = 22.0,
        ambient_humidity: float = 50.0,
        oil_consumption: float = 1.0,
        air_change_rate: Optional[float] = None,
        outdoor_pm25: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], np.ndarray]:
        if air_change_rate is not None:
            self.air_change_rate = air_change_rate
            self._velocity_field = self._calculate_velocity_field()
        if outdoor_pm25 is not None:
            self.outdoor_pm25 = outdoor_pm25

        D = self.calculate_diffusion_coefficient(ambient_temperature, ambient_humidity)
        temp_factor = 1.0 + self.temp_corr_coef * max(flue_temperature - self.temp_ref_c, 0)
        lamp_emission_ug = self.base_emission * oil_consumption / 1000.0 * temp_factor
        initial = self.initialize_concentration_field(indoor_pm25, lamp_emission_ug)
        diffused = self.solve_diffusion(initial, D, ambient_temperature)
        purified, purification_rate, purif_details = self.apply_purification(
            diffused, settling_efficiency, flue_velocity
        )
        avg_conc = float(np.mean(purified))
        gx, gy, gz = np.gradient(purified)
        grad_x = float(np.mean(np.abs(gx)))
        grad_y = float(np.mean(np.abs(gy)))
        grad_z = float(np.mean(np.abs(gz)))
        aqi_level, health_risk = self.evaluate_aqi(avg_conc)
        air_change_efficiency = (
            0.4 * purification_rate
            + 0.6 * min(self.air_change_rate / 4.0, 1.0)
        )
        ventilation_decay = 1.0 - np.exp(-self.air_change_rate / 60.0)

        result = {
            "pm25_diffusion_coeff": D,
            "pm25_gradient_x": grad_x,
            "pm25_gradient_y": grad_y,
            "pm25_gradient_z": grad_z,
            "purification_rate": purification_rate,
            "air_change_efficiency": air_change_efficiency,
            "aqi_level": aqi_level,
            "health_risk": health_risk,
            "air_change_rate": self.air_change_rate,
            "outdoor_pm25": self.outdoor_pm25,
            "ventilation_decay": ventilation_decay,
            "avg_pm25": avg_conc,
            "purification_details": purif_details,
        }
        return result, purified

    # ------------------------------------------------------------------
    # Feature: 多灯宴会协同净化
    # ------------------------------------------------------------------
    def set_scene_override(
        self,
        room_size_x: Optional[float] = None,
        room_size_y: Optional[float] = None,
        room_size_z: Optional[float] = None,
        nx: Optional[int] = None,
        ny: Optional[int] = None,
        nz: Optional[int] = None,
        lamp_positions: Optional[List[Dict[str, Any]]] = None,
    ):
        """覆写房间尺寸和网格分辨率（用于宴会场景，不改变原单灯实例的其他参数）"""
        if room_size_x is not None:
            self.room_size_x = room_size_x
        if room_size_y is not None:
            self.room_size_y = room_size_y
        if room_size_z is not None:
            self.room_size_z = room_size_z
        if nx is not None:
            self.nx = nx
        if ny is not None:
            self.ny = ny
        if nz is not None:
            self.nz = nz
        if lamp_positions:
            self.multi_lamp_positions = [
                np.array([lp["x_m"], lp["y_m"], lp["z_m"]], dtype=np.float64)
                for lp in lamp_positions
            ]
            self.multi_lamp_types = [lp.get("lamp_type", "changxin_gongdeng") for lp in lamp_positions]
        self._grid_coords = self._compute_grid_coordinates()
        self._velocity_field = self._calculate_velocity_field()

    def initialize_multi_lamp_field(
        self,
        base_pm25: float,
        lamp_emissions: List[float],
    ) -> np.ndarray:
        """多灯源初始化浓度场：每个灯位置叠加高斯源"""
        C = np.full((self.nx, self.ny, self.nz), float(base_pm25), dtype=np.float64)
        positions = getattr(self, "multi_lamp_positions", None) or [self.lamp_pos]
        lamp_types = getattr(self, "multi_lamp_types", None) or ["changxin_gongdeng"]

        try:
            dynasty_cfg = load_dynasty_lamps_config()
            lamps_db = dynasty_cfg.get("dynasty_lamps", {})
        except Exception:
            lamps_db = {}

        for idx, lamp_pos in enumerate(positions):
            emission = lamp_emissions[idx] if idx < len(lamp_emissions) else 0.0
            if emission <= 0:
                continue
            lamp_type = lamp_types[idx] if idx < len(lamp_types) else "changxin_gongdeng"
            lamp_cfg = lamps_db.get(lamp_type, {})
            purif_cfg = lamp_cfg.get("purification_characteristics", {})
            sigma = purif_cfg.get("local_purification_radius_m", self.lamp_sigma)
            src_strength = self.lamp_src_strength

            lamp_gx = int(round(lamp_pos[0] / self.room_size_x * (self.nx - 1)))
            lamp_gy = int(round(lamp_pos[1] / self.room_size_y * (self.ny - 1)))
            lamp_gz = int(round(lamp_pos[2] / self.room_size_z * (self.nz - 1)))
            lamp_gx = int(np.clip(lamp_gx, 0, self.nx - 1))
            lamp_gy = int(np.clip(lamp_gy, 0, self.ny - 1))
            lamp_gz = int(np.clip(lamp_gz, 0, self.nz - 1))
            sigma_sq = (sigma / max(self.room_size_x, 1)) ** 2 * self.nx ** 2
            for i in range(self.nx):
                for j in range(self.ny):
                    for k in range(self.nz):
                        dist_sq = (i - lamp_gx) ** 2 + (j - lamp_gy) ** 2 + (k - lamp_gz) ** 2
                        gauss = np.exp(-dist_sq / (2 * sigma_sq + 1e-12))
                        C[i, j, k] += src_strength * emission * gauss
        return C

    def apply_multi_lamp_purification(
        self,
        field: np.ndarray,
        settling_efficiencies: List[float],
        flue_velocities: List[float],
    ) -> Tuple[np.ndarray, float, Dict[str, Any]]:
        """多灯协同净化：每个灯在其净化半径内独立净化，叠加效果取最强衰减"""
        before = float(np.mean(field))
        positions = getattr(self, "multi_lamp_positions", None) or [self.lamp_pos]
        lamp_types = getattr(self, "multi_lamp_types", None) or ["changxin_gongdeng"]

        try:
            dynasty_cfg = load_dynasty_lamps_config()
            lamps_db = dynasty_cfg.get("dynasty_lamps", {})
        except Exception:
            lamps_db = {}

        purified = field.copy()
        per_lamp_details = []

        for idx, lamp_pos in enumerate(positions):
            lamp_type = lamp_types[idx] if idx < len(lamp_types) else "changxin_gongdeng"
            lamp_cfg = lamps_db.get(lamp_type, {})
            purif_cfg = lamp_cfg.get("purification_characteristics", {})

            base_purif = purif_cfg.get("base_purification_efficiency", self.base_purification)
            w_settle = purif_cfg.get("settling_weight", self.w_settle)
            w_vel = purif_cfg.get("velocity_weight", self.w_vel)
            radius = purif_cfg.get("local_purification_radius_m", self.purif_radius)
            strength = purif_cfg.get("local_purification_strength", self.purif_strength)
            decay = self.decay_exp

            settle_eff = settling_efficiencies[idx] if idx < len(settling_efficiencies) else 0.0
            flue_vel = flue_velocities[idx] if idx < len(flue_velocities) else 0.0
            settling_factor = min(max(settle_eff / max(self.min_settle, 1e-9), 0.0), 1.0)
            velocity_factor = min(max(flue_vel / max(self.min_vel, 1e-9), 0.0), 1.0)
            purification_efficiency = base_purif * (
                w_settle * settling_factor + w_vel * velocity_factor
            )

            lamp_world_x = lamp_pos[0] - self.room_size_x / 2
            lamp_world_y = lamp_pos[1] - self.room_size_y / 2
            lamp_world_z = lamp_pos[2]

            for i in range(self.nx):
                for j in range(self.ny):
                    for k in range(self.nz):
                        wx, wy, wz = self._grid_to_world(i, j, k)
                        dist = np.sqrt(
                            (wx - lamp_world_x) ** 2
                            + (wy - lamp_world_y) ** 2
                            + (wz - lamp_world_z) ** 2
                        )
                        if dist <= radius:
                            falloff = (1 - dist / radius) ** decay
                            local_eff = strength * purification_efficiency * falloff
                            candidate = field[i, j, k] * (1 - local_eff)
                            if candidate < purified[i, j, k]:
                                purified[i, j, k] = candidate

            per_lamp_details.append({
                "lamp_index": idx,
                "lamp_type": lamp_type,
                "purification_efficiency": purification_efficiency,
                "settling_factor": settling_factor,
                "velocity_factor": velocity_factor,
                "radius_m": radius,
            })

        after = float(np.mean(purified))
        purification_rate = max(0.0, (before - after) / max(before, 1e-9))
        details = {
            "avg_before": before,
            "avg_after": after,
            "purification_rate": purification_rate,
            "num_lamps": len(positions),
            "per_lamp": per_lamp_details,
        }
        return purified, purification_rate, details

    def analyze_banquet(
        self,
        base_pm25: float,
        lamp_emissions_ug: List[float],
        settling_efficiencies: List[float],
        flue_velocities: List[float],
        flue_temperatures: Optional[List[float]] = None,
        ambient_temperature: float = 22.0,
        ambient_humidity: float = 50.0,
        air_change_rate: Optional[float] = None,
        outdoor_pm25: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], np.ndarray]:
        """多灯宴会场景综合分析"""
        if air_change_rate is not None:
            self.air_change_rate = air_change_rate
            self._velocity_field = self._calculate_velocity_field()
        if outdoor_pm25 is not None:
            self.outdoor_pm25 = outdoor_pm25

        D = self.calculate_diffusion_coefficient(ambient_temperature, ambient_humidity)
        initial = self.initialize_multi_lamp_field(base_pm25, lamp_emissions_ug)
        diffused = self.solve_diffusion(initial, D, ambient_temperature)
        purified, purification_rate, details = self.apply_multi_lamp_purification(
            diffused, settling_efficiencies, flue_velocities
        )
        avg_conc = float(np.mean(purified))
        gx, gy, gz = np.gradient(purified)
        grad_x = float(np.mean(np.abs(gx)))
        grad_y = float(np.mean(np.abs(gy)))
        grad_z = float(np.mean(np.abs(gz)))
        aqi_level, health_risk = self.evaluate_aqi(avg_conc)
        air_change_efficiency = (
            0.4 * purification_rate
            + 0.6 * min(self.air_change_rate / 4.0, 1.0)
        )
        ventilation_decay = 1.0 - np.exp(-self.air_change_rate / 60.0)

        result = {
            "pm25_diffusion_coeff": D,
            "pm25_gradient_x": grad_x,
            "pm25_gradient_y": grad_y,
            "pm25_gradient_z": grad_z,
            "purification_rate": purification_rate,
            "air_change_efficiency": air_change_efficiency,
            "aqi_level": aqi_level,
            "health_risk": health_risk,
            "air_change_rate": self.air_change_rate,
            "outdoor_pm25": self.outdoor_pm25,
            "ventilation_decay": ventilation_decay,
            "avg_pm25": avg_conc,
            "purification_details": details,
            "scene_type": "banquet_multi_lamp",
        }
        return result, purified
