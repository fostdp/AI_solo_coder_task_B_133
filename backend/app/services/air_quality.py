import math
import numpy as np
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class AirQualityAnalyzer:
    """
    空气质量分析与PM2.5扩散模型
    基于对流扩散方程评估宫灯对室内空气的净化效果
    支持室内通风换气率参数修正
    """

    def __init__(
        self,
        room_size_x: float = 10.0,
        room_size_y: float = 8.0,
        room_size_z: float = 3.0,
        grid_resolution: int = 5,
        air_change_rate: float = 0.5,
        outdoor_pm25: float = 35.0,
        inlet_position: tuple = (0.0, 4.0, 2.0),
        outlet_position: tuple = (10.0, 4.0, 2.0)
    ):
        self.room_size_x = room_size_x
        self.room_size_y = room_size_y
        self.room_size_z = room_size_z
        self.grid_resolution = grid_resolution

        self.D_pm25_base = 1.5e-7
        self.lamp_position = (room_size_x / 2, room_size_y / 2, 1.5)
        self.purification_efficiency = 0.3

        self.air_change_rate = air_change_rate
        self.outdoor_pm25 = outdoor_pm25
        self.inlet_position = inlet_position
        self.outlet_position = outlet_position

        self._ventilation_decay = air_change_rate / 60.0
        self._calculate_velocity_field()

    def _get_aqi_level(self, pm25: float) -> str:
        if pm25 <= 35:
            return "优"
        elif pm25 <= 75:
            return "良"
        elif pm25 <= 115:
            return "轻度污染"
        elif pm25 <= 150:
            return "中度污染"
        elif pm25 <= 250:
            return "重度污染"
        else:
            return "严重污染"

    def _get_health_risk(self, aqi_level: str) -> str:
        risks = {
            "优": "空气质量令人满意，基本无空气污染",
            "良": "空气质量可接受，某些污染物可能对极少数异常敏感人群健康有较弱影响",
            "轻度污染": "易感人群症状有轻度加剧，健康人群出现刺激症状",
            "中度污染": "进一步加剧易感人群症状，可能对健康人群心脏、呼吸系统有影响",
            "重度污染": "心脏病和肺病患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状",
            "严重污染": "健康人群运动耐受力降低，有明显强烈症状，提前出现某些疾病"
        }
        return risks.get(aqi_level, "未知")

    def set_ventilation_parameters(
        self,
        air_change_rate: Optional[float] = None,
        outdoor_pm25: Optional[float] = None,
        inlet_position: Optional[tuple] = None,
        outlet_position: Optional[tuple] = None
    ):
        """设置通风参数"""
        if air_change_rate is not None:
            self.air_change_rate = air_change_rate
            self._ventilation_decay = air_change_rate / 60.0
        if outdoor_pm25 is not None:
            self.outdoor_pm25 = outdoor_pm25
        if inlet_position is not None:
            self.inlet_position = inlet_position
        if outlet_position is not None:
            self.outlet_position = outlet_position

        self._calculate_velocity_field()
        logger.info(
            f"通风参数已更新: ACH={self.air_change_rate}, "
            f"室外PM2.5={self.outdoor_pm25}μg/m³"
        )

    def _calculate_velocity_field(self):
        """
        基于换气率和进出口位置计算室内速度场
        采用简化的势流模型 + 粘性衰减
        """
        nx, ny, nz = self.grid_resolution, self.grid_resolution, self.grid_resolution
        self.velocity_field = np.zeros((3, nx, ny, nz))

        if self.air_change_rate <= 0:
            return

        room_volume = self.room_size_x * self.room_size_y * self.room_size_z
        total_flow_rate = (self.air_change_rate / 3600.0) * room_volume

        dx = self.room_size_x / max(nx - 1, 1)
        dy = self.room_size_y / max(ny - 1, 1)
        dz = self.room_size_z / max(nz - 1, 1)

        inlet_gx = int(self.inlet_position[0] / self.room_size_x * (nx - 1))
        inlet_gy = int(self.inlet_position[1] / self.room_size_y * (ny - 1))
        inlet_gz = int(self.inlet_position[2] / self.room_size_z * (nz - 1))

        outlet_gx = int(self.outlet_position[0] / self.room_size_x * (nx - 1))
        outlet_gy = int(self.outlet_position[1] / self.room_size_y * (ny - 1))
        outlet_gz = int(self.outlet_position[2] / self.room_size_z * (nz - 1))

        inlet_gx = max(0, min(nx - 1, inlet_gx))
        inlet_gy = max(0, min(ny - 1, inlet_gy))
        inlet_gz = max(0, min(nz - 1, inlet_gz))
        outlet_gx = max(0, min(nx - 1, outlet_gx))
        outlet_gy = max(0, min(ny - 1, outlet_gy))
        outlet_gz = max(0, min(nz - 1, outlet_gz))

        avg_velocity = total_flow_rate / max(dx * dy * 10, 1e-6)

        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    wx = i * dx
                    wy = j * dy
                    wz = k * dz

                    dist_to_inlet = math.sqrt(
                        (wx - self.inlet_position[0]) ** 2 +
                        (wy - self.inlet_position[1]) ** 2 +
                        (wz - self.inlet_position[2]) ** 2
                    )
                    dist_to_outlet = math.sqrt(
                        (wx - self.outlet_position[0]) ** 2 +
                        (wy - self.outlet_position[1]) ** 2 +
                        (wz - self.outlet_position[2]) ** 2
                    )

                    dist_to_inlet = max(dist_to_inlet, 0.1)
                    dist_to_outlet = max(dist_to_outlet, 0.1)

                    vel_in_mag = avg_velocity * math.exp(-dist_to_inlet / 1.5)
                    vel_out_mag = avg_velocity * math.exp(-dist_to_outlet / 1.5)

                    if dist_to_inlet > 0:
                        vx_in = vel_in_mag * (wx - self.inlet_position[0]) / dist_to_inlet
                        vy_in = vel_in_mag * (wy - self.inlet_position[1]) / dist_to_inlet
                        vz_in = vel_in_mag * (wz - self.inlet_position[2]) / dist_to_inlet
                    else:
                        vx_in = vy_in = vz_in = 0

                    if dist_to_outlet > 0:
                        vx_out = -vel_out_mag * (wx - self.outlet_position[0]) / dist_to_outlet
                        vy_out = -vel_out_mag * (wy - self.outlet_position[1]) / dist_to_outlet
                        vz_out = -vel_out_mag * (wz - self.outlet_position[2]) / dist_to_outlet
                    else:
                        vx_out = vy_out = vz_out = 0

                    self.velocity_field[0, i, j, k] = 0.6 * vx_in + 0.4 * vx_out
                    self.velocity_field[1, i, j, k] = 0.6 * vy_in + 0.4 * vy_out
                    self.velocity_field[2, i, j, k] = 0.6 * vz_in + 0.4 * vz_out

        logger.debug(
            f"速度场计算完成: 最大速度={np.max(np.abs(self.velocity_field)):.4f}m/s, "
            f"换气率={self.air_change_rate}次/小时"
        )

    def _calculate_convective_term(
        self,
        concentration_field: np.ndarray,
        velocity_field: np.ndarray,
        dx: float,
        dy: float,
        dz: float
    ) -> np.ndarray:
        """
        计算对流项 u·∇C
        使用迎风格式提高数值稳定性
        """
        nx, ny, nz = concentration_field.shape
        convective = np.zeros_like(concentration_field)

        for i in range(1, nx - 1):
            for j in range(1, ny - 1):
                for k in range(1, nz - 1):
                    ux = velocity_field[0, i, j, k]
                    uy = velocity_field[1, i, j, k]
                    uz = velocity_field[2, i, j, k]

                    if ux > 0:
                        dC_dx = (concentration_field[i, j, k] - concentration_field[i - 1, j, k]) / dx
                    else:
                        dC_dx = (concentration_field[i + 1, j, k] - concentration_field[i, j, k]) / dx

                    if uy > 0:
                        dC_dy = (concentration_field[i, j, k] - concentration_field[i, j - 1, k]) / dy
                    else:
                        dC_dy = (concentration_field[i, j + 1, k] - concentration_field[i, j, k]) / dy

                    if uz > 0:
                        dC_dz = (concentration_field[i, j, k] - concentration_field[i, j, k - 1]) / dz
                    else:
                        dC_dz = (concentration_field[i, j, k + 1] - concentration_field[i, j, k]) / dz

                    convective[i, j, k] = ux * dC_dx + uy * dC_dy + uz * dC_dz

        return convective

    def _apply_ventilation_boundary_conditions(
        self,
        concentration_field: np.ndarray,
        inlet_gx: int,
        inlet_gy: int,
        inlet_gz: int,
        outlet_gx: int,
        outlet_gy: int,
        outlet_gz: int,
        dt: float
    ) -> np.ndarray:
        """
        应用通风边界条件：入口为室外PM2.5，出口强制排风
        """
        new_field = concentration_field.copy()

        inlet_radius = max(1, self.grid_resolution // 5)

        for di in range(-inlet_radius, inlet_radius + 1):
            for dj in range(-inlet_radius, inlet_radius + 1):
                for dk in range(-inlet_radius, inlet_radius + 1):
                    i = inlet_gx + di
                    j = inlet_gy + dj
                    k = inlet_gz + dk
                    if 0 <= i < self.grid_resolution and 0 <= j < self.grid_resolution and 0 <= k < self.grid_resolution:
                        dist = math.sqrt(di ** 2 + dj ** 2 + dk ** 2)
                        if dist <= inlet_radius:
                            weight = math.exp(-dist / inlet_radius)
                            new_field[i, j, k] = weight * self.outdoor_pm25 + (1 - weight) * new_field[i, j, k]

        exhaust_strength = min(1.0, self._ventilation_decay * dt * 10)
        for di in range(-inlet_radius, inlet_radius + 1):
            for dj in range(-inlet_radius, inlet_radius + 1):
                for dk in range(-inlet_radius, inlet_radius + 1):
                    i = outlet_gx + di
                    j = outlet_gy + dj
                    k = outlet_gz + dk
                    if 0 <= i < self.grid_resolution and 0 <= j < self.grid_resolution and 0 <= k < self.grid_resolution:
                        dist = math.sqrt(di ** 2 + dj ** 2 + dk ** 2)
                        if dist <= inlet_radius:
                            weight = math.exp(-dist / inlet_radius) * exhaust_strength
                            new_field[i, j, k] = (1 - weight) * new_field[i, j, k] + weight * self.outdoor_pm25

        return new_field

    def calculate_diffusion_coefficient(
        self,
        temperature: float = 25.0,
        humidity: float = 50.0
    ) -> float:
        T_kelvin = temperature + 273.15
        P = 101325.0
        T_ref = 273.15
        P_ref = 101325.0
        D = self.D_pm25_base * (T_kelvin / T_ref) ** 1.75 * (P_ref / P)

        humidity_factor = 1.0 - 0.002 * (humidity - 50.0)
        humidity_factor = max(0.8, min(1.2, humidity_factor))

        return D * humidity_factor

    def calculate_diffusion_gradient(
        self,
        concentration_field: np.ndarray,
        dx: float,
        dy: float,
        dz: float
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        grad_x = np.gradient(concentration_field, dx, axis=0)
        grad_y = np.gradient(concentration_field, dy, axis=1)
        grad_z = np.gradient(concentration_field, dz, axis=2)
        return grad_x, grad_y, grad_z

    def initialize_concentration_field(
        self,
        base_pm25: float,
        lamp_emission_rate: float,
        settling_efficiency: float = 0.0
    ) -> np.ndarray:
        nx, ny, nz = self.grid_resolution, self.grid_resolution, self.grid_resolution
        field = np.ones((nx, ny, nz)) * base_pm25

        dx = self.room_size_x / (nx - 1)
        dy = self.room_size_y / (ny - 1)
        dz = self.room_size_z / (nz - 1)

        lamp_gx = int(self.lamp_position[0] / self.room_size_x * (nx - 1))
        lamp_gy = int(self.lamp_position[1] / self.room_size_y * (ny - 1))
        lamp_gz = int(self.lamp_position[2] / self.room_size_z * (nz - 1))

        effective_emission = lamp_emission_rate * (1 - settling_efficiency / 100.0)

        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    dist = math.sqrt(
                        ((i - lamp_gx) * dx) ** 2 +
                        ((j - lamp_gy) * dy) ** 2 +
                        ((k - lamp_gz) * dz) ** 2
                    )
                    dist = max(dist, 0.1)
                    emission_contribution = effective_emission * math.exp(-dist / 2.0) / dist
                    field[i, j, k] += emission_contribution

        return field

    def solve_diffusion(
        self,
        initial_field: np.ndarray,
        D: float,
        dt: float = 1.0,
        num_steps: int = 10,
        air_change_rate: Optional[float] = None,
        outdoor_pm25: Optional[float] = None
    ) -> np.ndarray:
        """
        求解三维对流扩散方程：∂C/∂t = D·∇²C - u·∇C - λ·(C - C_out)
        包含：分子扩散项 + 对流项 + 通风稀释项
        """
        field = initial_field.copy()
        nx, ny, nz = field.shape

        dx = self.room_size_x / max(nx - 1, 1)
        dy = self.room_size_y / max(ny - 1, 1)
        dz = self.room_size_z / max(nz - 1, 1)

        if air_change_rate is not None or outdoor_pm25 is not None:
            self.set_ventilation_parameters(
                air_change_rate=air_change_rate,
                outdoor_pm25=outdoor_pm25
            )

        if not hasattr(self, 'velocity_field') or self.velocity_field.shape[1:] != (nx, ny, nz):
            self._calculate_velocity_field()

        inlet_gx = int(self.inlet_position[0] / self.room_size_x * (nx - 1))
        inlet_gy = int(self.inlet_position[1] / self.room_size_y * (ny - 1))
        inlet_gz = int(self.inlet_position[2] / self.room_size_z * (nz - 1))
        outlet_gx = int(self.outlet_position[0] / self.room_size_x * (nx - 1))
        outlet_gy = int(self.outlet_position[1] / self.room_size_y * (ny - 1))
        outlet_gz = int(self.outlet_position[2] / self.room_size_z * (nz - 1))

        inlet_gx = max(0, min(nx - 1, inlet_gx))
        inlet_gy = max(0, min(ny - 1, inlet_gy))
        inlet_gz = max(0, min(nz - 1, inlet_gz))
        outlet_gx = max(0, min(nx - 1, outlet_gx))
        outlet_gy = max(0, min(ny - 1, outlet_gy))
        outlet_gz = max(0, min(nz - 1, outlet_gz))

        lambda_vent = self._ventilation_decay
        C_out = self.outdoor_pm25

        for step in range(num_steps):
            new_field = field.copy()

            convective_term = self._calculate_convective_term(
                field, self.velocity_field, dx, dy, dz
            )

            for i in range(1, nx - 1):
                for j in range(1, ny - 1):
                    for k in range(1, nz - 1):
                        laplacian = (
                            (field[i + 1, j, k] - 2 * field[i, j, k] + field[i - 1, j, k]) / (dx ** 2) +
                            (field[i, j + 1, k] - 2 * field[i, j, k] + field[i, j - 1, k]) / (dy ** 2) +
                            (field[i, j, k + 1] - 2 * field[i, j, k] + field[i, j, k - 1]) / (dz ** 2)
                        )

                        diffusion_term = D * laplacian
                        convection_term = convective_term[i, j, k]
                        ventilation_term = -lambda_vent * (field[i, j, k] - C_out)

                        dC_dt = diffusion_term - convection_term + ventilation_term
                        new_field[i, j, k] = field[i, j, k] + dC_dt * dt

            new_field = self._apply_ventilation_boundary_conditions(
                new_field,
                inlet_gx, inlet_gy, inlet_gz,
                outlet_gx, outlet_gy, outlet_gz,
                dt
            )

            new_field = np.clip(new_field, 0, None)
            field = new_field

        logger.debug(
            f"扩散求解完成: 迭代{num_steps}步, "
            f"最终平均浓度={np.mean(field):.1f}μg/m³, "
            f"换气率={self.air_change_rate}ACH, 室外PM2.5={C_out}μg/m³"
        )

        return field

    def apply_purification(
        self,
        concentration_field: np.ndarray,
        settling_efficiency: float,
        flue_velocity: float
    ) -> np.ndarray:
        field = concentration_field.copy()
        nx, ny, nz = field.shape

        lamp_gx = int(self.lamp_position[0] / self.room_size_x * (nx - 1))
        lamp_gy = int(self.lamp_position[1] / self.room_size_y * (ny - 1))
        lamp_gz = int(self.lamp_position[2] / self.room_size_z * (nz - 1))

        purify_radius = max(1, int(nx * 0.3))
        local_efficiency = self.purification_efficiency * (settling_efficiency / 100.0)
        velocity_factor = min(2.0, flue_velocity / 0.3)

        for i in range(max(0, lamp_gx - purify_radius), min(nx, lamp_gx + purify_radius + 1)):
            for j in range(max(0, lamp_gy - purify_radius), min(ny, lamp_gy + purify_radius + 1)):
                for k in range(max(0, lamp_gz - purify_radius), min(nz, lamp_gz + purify_radius + 1)):
                    dist = math.sqrt(
                        (i - lamp_gx) ** 2 + (j - lamp_gy) ** 2 + (k - lamp_gz) ** 2
                    )
                    if dist <= purify_radius:
                        factor = 1.0 - (dist / purify_radius) ** 2
                        reduction = field[i, j, k] * local_efficiency * factor * velocity_factor
                        field[i, j, k] = max(0, field[i, j, k] - reduction)

        return field

    def calculate_purification_rate(
        self,
        before_field: np.ndarray,
        after_field: np.ndarray,
        time_interval_min: float = 1.0
    ) -> float:
        avg_before = np.mean(before_field)
        avg_after = np.mean(after_field)
        return (avg_before - avg_after) / max(time_interval_min, 0.1)

    def calculate_air_change_efficiency(
        self,
        concentration_field: np.ndarray,
        nominal_pm25: float = 35.0
    ) -> float:
        avg_concentration = np.mean(concentration_field)

        theoretical_ach_removal = 1.0 - math.exp(-self.air_change_rate / 60.0)
        max_achievable_efficiency = min(100.0, theoretical_ach_removal * 100)

        if avg_concentration <= nominal_pm25:
            ventilation_contribution = min(100.0, max_achievable_efficiency)
            efficiency = ventilation_contribution
        else:
            reduction_ratio = (avg_concentration - nominal_pm25) / max(avg_concentration, 1e-6)
            purification_efficiency = max(0.0, (1.0 - reduction_ratio) * 100.0)
            efficiency = 0.4 * purification_efficiency + 0.6 * max_achievable_efficiency

        return min(100.0, max(0.0, efficiency))

    def analyze(
        self,
        indoor_pm25: float,
        flue_temperature: float,
        flue_velocity: float,
        settling_efficiency: float,
        ambient_temperature: float = 25.0,
        ambient_humidity: float = 50.0,
        oil_consumption: Optional[float] = None,
        air_change_rate: Optional[float] = None,
        outdoor_pm25: Optional[float] = None
    ) -> Tuple[Dict, List[Dict]]:
        D = self.calculate_diffusion_coefficient(ambient_temperature, ambient_humidity)

        lamp_emission_rate = max(0, (oil_consumption or 2.0) * 5.0)

        initial_field = self.initialize_concentration_field(
            base_pm25=indoor_pm25,
            lamp_emission_rate=lamp_emission_rate,
            settling_efficiency=settling_efficiency
        )

        diffused_field = self.solve_diffusion(
            initial_field,
            D,
            dt=1.0,
            num_steps=5,
            air_change_rate=air_change_rate,
            outdoor_pm25=outdoor_pm25
        )

        purified_field = self.apply_purification(diffused_field, settling_efficiency, flue_velocity)

        dx = self.room_size_x / max(self.grid_resolution - 1, 1)
        dy = self.room_size_y / max(self.grid_resolution - 1, 1)
        dz = self.room_size_z / max(self.grid_resolution - 1, 1)

        grad_x, grad_y, grad_z = self.calculate_diffusion_gradient(purified_field, dx, dy, dz)

        avg_grad_x = float(np.mean(np.abs(grad_x)))
        avg_grad_y = float(np.mean(np.abs(grad_y)))
        avg_grad_z = float(np.mean(np.abs(grad_z)))

        purification_rate = self.calculate_purification_rate(initial_field, purified_field)
        air_change_efficiency = self.calculate_air_change_efficiency(purified_field)

        avg_pm25 = float(np.mean(purified_field))
        aqi_level = self._get_aqi_level(avg_pm25)
        health_risk = self._get_health_risk(aqi_level)

        analysis_result = {
            "time": datetime.now(),
            "pm25_diffusion_coeff": round(D, 10),
            "pm25_gradient_x": round(avg_grad_x, 6),
            "pm25_gradient_y": round(avg_grad_y, 6),
            "pm25_gradient_z": round(avg_grad_z, 6),
            "purification_rate": round(purification_rate, 4),
            "air_change_efficiency": round(air_change_efficiency, 2),
            "aqi_level": aqi_level,
            "health_risk": health_risk,
            "air_change_rate": round(self.air_change_rate, 2),
            "outdoor_pm25": round(self.outdoor_pm25, 1),
            "ventilation_decay": round(self._ventilation_decay, 6),
        }

        grid_data = []
        nx, ny, nz = purified_field.shape
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    grid_data.append({
                        "grid_x": i,
                        "grid_y": j,
                        "grid_z": k,
                        "concentration": round(float(purified_field[i, j, k]), 2)
                    })

        logger.info(
            f"空气质量分析: D={D:.2e}m²/s, 平均PM2.5={avg_pm25:.1f}μg/m³, "
            f"AQI={aqi_level}, 净化速率={purification_rate:.2f}μg/m³·min, "
            f"换气效率={air_change_efficiency:.1f}%"
        )

        return analysis_result, grid_data

    def get_pm25_cloud_data(
        self,
        base_pm25: float,
        settling_efficiency: float = 30.0,
        lamp_emission_rate: float = 10.0
    ) -> List[Dict]:
        initial_field = self.initialize_concentration_field(
            base_pm25=base_pm25,
            lamp_emission_rate=lamp_emission_rate,
            settling_efficiency=settling_efficiency
        )

        D = self.calculate_diffusion_coefficient()
        diffused_field = self.solve_diffusion(initial_field, D)

        grid_data = []
        nx, ny, nz = diffused_field.shape
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    grid_data.append({
                        "grid_x": i,
                        "grid_y": j,
                        "grid_z": k,
                        "concentration": round(float(diffused_field[i, j, k]), 2),
                        "world_x": round(i * self.room_size_x / max(nx - 1, 1), 2),
                        "world_y": round(j * self.room_size_y / max(ny - 1, 1), 2),
                        "world_z": round(k * self.room_size_z / max(nz - 1, 1), 2),
                    })

        return grid_data
