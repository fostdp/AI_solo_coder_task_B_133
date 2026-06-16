import math
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


FUEL_TYPES = {
    "animal_fat": {
        "name": "动物脂肪（汉代常用）",
        "heating_value": 37.5,
        "density": 0.92,
        "smoke_particle_density": 2200.0,
        "co2_emission_factor": 2.85,
        "h2o_emission_factor": 1.15,
        "soot_emission_factor": 0.015,
        "molar_mass": 282.0,
        "combustion_efficiency": 0.88,
    },
    "sesame_oil": {
        "name": "麻油",
        "heating_value": 37.0,
        "density": 0.92,
        "smoke_particle_density": 2000.0,
        "co2_emission_factor": 2.8,
        "h2o_emission_factor": 1.1,
        "soot_emission_factor": 0.012,
        "molar_mass": 276.0,
        "combustion_efficiency": 0.90,
    },
    "beeswax": {
        "name": "蜜蜡",
        "heating_value": 42.0,
        "density": 0.95,
        "smoke_particle_density": 1800.0,
        "co2_emission_factor": 3.0,
        "h2o_emission_factor": 1.4,
        "soot_emission_factor": 0.008,
        "molar_mass": 352.0,
        "combustion_efficiency": 0.92,
    },
    "mineral_oil": {
        "name": "矿物油（参照）",
        "heating_value": 44.0,
        "density": 0.85,
        "smoke_particle_density": 2500.0,
        "co2_emission_factor": 3.15,
        "h2o_emission_factor": 1.35,
        "soot_emission_factor": 0.025,
        "molar_mass": 170.0,
        "combustion_efficiency": 0.85,
    },
    "tallow": {
        "name": "牛油",
        "heating_value": 39.0,
        "density": 0.94,
        "smoke_particle_density": 2300.0,
        "co2_emission_factor": 2.9,
        "h2o_emission_factor": 1.18,
        "soot_emission_factor": 0.018,
        "molar_mass": 284.0,
        "combustion_efficiency": 0.87,
    },
}


@dataclass
class FlueParams:
    flue_diameter: float = 0.05
    flue_length: float = 0.8
    flue_area: float = 0.0
    flue_cross_section_area: float = 0.0
    fuel_type: str = "animal_fat"

    def __post_init__(self):
        self.flue_cross_section_area = math.pi * (self.flue_diameter / 2) ** 2
        self.flue_area = math.pi * self.flue_diameter * self.flue_length
        if self.fuel_type not in FUEL_TYPES:
            logger.warning(f"未知燃料类型 {self.fuel_type}，使用默认动物脂肪")
            self.fuel_type = "animal_fat"


class FlueFluidSimulator:
    """
    烟道流体仿真模型
    基于层流和自然对流理论，计算烟气在烟道内的流动和冷却沉降
    支持多种燃料类型（动物脂肪、麻油、蜜蜡等）的热值与物性修正
    """

    def __init__(self, params: Optional[FlueParams] = None):
        self.params = params or FlueParams()
        self.current_fuel_type = self.params.fuel_type

        self.g = 9.81
        self.k_air = 0.026
        self.cp_air = 1005.0
        self.rho_air_ref = 1.204
        self.mu_air_ref = 1.81e-5
        self.T_ref = 293.15

    def get_fuel_properties(self, fuel_type: Optional[str] = None) -> dict:
        """获取指定燃料的热物理性质参数"""
        ft = fuel_type or self.current_fuel_type
        return FUEL_TYPES.get(ft, FUEL_TYPES["animal_fat"])

    def set_fuel_type(self, fuel_type: str):
        """设置当前燃料类型"""
        if fuel_type not in FUEL_TYPES:
            raise ValueError(f"不支持的燃料类型: {fuel_type}. 可用类型: {list(FUEL_TYPES.keys())}")
        self.current_fuel_type = fuel_type
        self.params.fuel_type = fuel_type
        logger.info(f"已切换燃料类型为: {FUEL_TYPES[fuel_type]['name']}")

    def _flue_gas_viscosity(self, T: float, fuel_type: Optional[str] = None) -> float:
        """
        烟气动力粘度，考虑燃料燃烧产物成分
        基于经验公式: μ_mix = Σ(x_i * μ_i * sqrt(M_i)) / Σ(x_i * sqrt(M_i))
        """
        fuel = self.get_fuel_properties(fuel_type)
        T_kelvin = T + 273.15

        x_co2 = min(0.15, 0.03 + fuel["co2_emission_factor"] * 0.02)
        x_h2o = min(0.12, 0.02 + fuel["h2o_emission_factor"] * 0.015)
        x_n2 = 1.0 - x_co2 - x_h2o

        mu_n2 = 1.663e-6 * (T_kelvin ** 0.666)
        mu_co2 = 1.370e-6 * (T_kelvin ** 0.79)
        mu_h2o = 0.961e-6 * (T_kelvin ** 0.81)

        M_n2, M_co2, M_h2o = 28.01, 44.01, 18.016
        sqrt_M_n2, sqrt_M_co2, sqrt_M_h2o = math.sqrt(M_n2), math.sqrt(M_co2), math.sqrt(M_h2o)

        numerator = (x_n2 * mu_n2 * sqrt_M_n2 +
                     x_co2 * mu_co2 * sqrt_M_co2 +
                     x_h2o * mu_h2o * sqrt_M_h2o)
        denominator = (x_n2 * sqrt_M_n2 +
                       x_co2 * sqrt_M_co2 +
                       x_h2o * sqrt_M_h2o)

        mu = numerator / max(denominator, 1e-10)
        return mu

    def _flue_gas_density(self, T: float, fuel_type: Optional[str] = None, P: float = 101325.0) -> float:
        """
        烟气密度，考虑燃烧产物平均分子量
        """
        fuel = self.get_fuel_properties(fuel_type)
        T_kelvin = T + 273.15

        x_co2 = min(0.15, 0.03 + fuel["co2_emission_factor"] * 0.02)
        x_h2o = min(0.12, 0.02 + fuel["h2o_emission_factor"] * 0.015)
        x_n2 = 1.0 - x_co2 - x_h2o

        M_n2, M_co2, M_h2o = 28.01, 44.01, 18.016
        M_mix = x_n2 * M_n2 + x_co2 * M_co2 + x_h2o * M_h2o

        R_mix = 8314.0 / M_mix
        rho = P / (R_mix * T_kelvin)
        return rho

    def _flue_gas_thermal_conductivity(self, T: float, fuel_type: Optional[str] = None) -> float:
        """
        烟气导热系数，考虑CO2和H2O的辐射与导热耦合效应
        """
        fuel = self.get_fuel_properties(fuel_type)
        T_kelvin = T + 273.15

        x_co2 = min(0.15, 0.03 + fuel["co2_emission_factor"] * 0.02)
        x_h2o = min(0.12, 0.02 + fuel["h2o_emission_factor"] * 0.015)
        x_n2 = 1.0 - x_co2 - x_h2o

        k_n2 = 0.024 * (T_kelvin / 273.15) ** 0.8
        k_co2 = 0.0146 * (T_kelvin / 273.15) ** 0.95
        k_h2o = 0.0173 * (T_kelvin / 273.15) ** 0.9

        k_mix = x_n2 * k_n2 + x_co2 * k_co2 + x_h2o * k_h2o
        radiation_correction = 1.0 + 0.1 * x_co2 + 0.15 * x_h2o
        return k_mix * radiation_correction

    def _flue_gas_specific_heat(self, T: float, fuel_type: Optional[str] = None) -> float:
        """
        烟气定压比热容，考虑燃烧产物成分
        """
        fuel = self.get_fuel_properties(fuel_type)
        T_kelvin = T + 273.15

        x_co2 = min(0.15, 0.03 + fuel["co2_emission_factor"] * 0.02)
        x_h2o = min(0.12, 0.02 + fuel["h2o_emission_factor"] * 0.015)
        x_n2 = 1.0 - x_co2 - x_h2o

        cp_n2 = 1030.0 - 0.15 * (T_kelvin - 300.0)
        cp_co2 = 820.0 + 1.2 * (T_kelvin - 300.0)
        cp_h2o = 1850.0 + 0.5 * (T_kelvin - 300.0)

        cp_mix = x_n2 * cp_n2 + x_co2 * cp_co2 + x_h2o * cp_h2o
        return cp_mix

    def _calculate_buoyancy_correction(
        self,
        T_flue: float,
        T_ambient: float,
        fuel_type: Optional[str] = None
    ) -> float:
        """
        计算基于实际烟气成分的浮力修正系数
        由于烟气分子量与空气不同，自然对流的驱动力需要修正
        """
        fuel = self.get_fuel_properties(fuel_type)
        rho_flue = self._flue_gas_density(T_flue, fuel_type)
        rho_amb = self._flue_gas_density(T_ambient, fuel_type)

        rho_air_amb = self._air_density(T_ambient)

        molecular_weight_correction = rho_flue / max(rho_air_amb, 1e-6)
        density_ratio = (rho_amb - rho_flue) / max(rho_air_amb, 1e-6)

        correction_factor = 1.0 + 0.3 * (molecular_weight_correction - 1.0) + 0.5 * abs(density_ratio)
        correction_factor = max(0.8, min(1.5, correction_factor))

        logger.debug(
            f"浮力修正: 燃料={fuel['name']}, "
            f"烟气密度={rho_flue:.3f}kg/m³, 修正系数={correction_factor:.3f}"
        )

        return correction_factor

    def _air_viscosity(self, T: float) -> float:
        T_kelvin = T + 273.15
        S = 110.4
        mu_ref = 1.716e-5
        T_ref_suth = 273.15
        return mu_ref * (T_kelvin / T_ref_suth) ** 1.5 * (T_ref_suth + S) / (T_kelvin + S)

    def _air_density(self, T: float, P: float = 101325.0) -> float:
        T_kelvin = T + 273.15
        R_air = 287.0
        return P / (R_air * T_kelvin)

    def _air_thermal_conductivity(self, T: float) -> float:
        T_kelvin = T + 273.15
        return 0.026 * (T_kelvin / 300.0) ** 0.8

    def _air_specific_heat(self, T: float) -> float:
        T_kelvin = T + 273.15
        return 1005.0 + 0.1 * (T_kelvin - 300.0)

    def calculate_reynolds(
        self,
        velocity: float,
        T_flue: float,
        T_ambient: float = 25.0,
        fuel_type: Optional[str] = None
    ) -> float:
        T_avg = (T_flue + T_ambient) / 2
        rho = self._flue_gas_density(T_avg, fuel_type)
        mu = self._flue_gas_viscosity(T_avg, fuel_type)
        Re = rho * velocity * self.params.flue_diameter / mu
        return max(1.0, Re)

    def calculate_prandtl(
        self,
        T_flue: float,
        T_ambient: float = 25.0,
        fuel_type: Optional[str] = None
    ) -> float:
        T_avg = (T_flue + T_ambient) / 2
        mu = self._flue_gas_viscosity(T_avg, fuel_type)
        cp = self._flue_gas_specific_heat(T_avg, fuel_type)
        k = self._flue_gas_thermal_conductivity(T_avg, fuel_type)
        Pr = mu * cp / k
        return max(0.1, Pr)

    def calculate_grashof(
        self,
        T_flue: float,
        T_ambient: float = 25.0,
        fuel_type: Optional[str] = None
    ) -> float:
        T_avg = (T_flue + T_ambient) / 2
        beta = 1.0 / (T_avg + 273.15)
        delta_T = abs(T_flue - T_ambient)
        mu = self._flue_gas_viscosity(T_avg, fuel_type)
        rho = self._flue_gas_density(T_avg, fuel_type)
        nu = mu / max(rho, 1e-6)

        buoyancy_correction = self._calculate_buoyancy_correction(T_flue, T_ambient, fuel_type)

        Gr = self.g * beta * delta_T * (self.params.flue_length ** 3) / (nu ** 2)
        Gr = Gr * buoyancy_correction

        return max(1.0, Gr)

    def calculate_rayleigh(self, Gr: float, Pr: float) -> float:
        return Gr * Pr

    def _laminar_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        L_over_D = self.params.flue_length / self.params.flue_diameter
        Ra = self.calculate_rayleigh(Gr, Pr)

        if Ra < 1e9:
            Nu_natural = 0.59 * Ra ** 0.25
        else:
            Nu_natural = 0.10 * Ra ** (1.0 / 3.0)

        if Re < 2300:
            Nu_forced = 3.66 + (0.0668 * (self.params.flue_diameter / self.params.flue_length) * Re * Pr) / \
                        (1 + 0.04 * ((self.params.flue_diameter / self.params.flue_length) * Re * Pr) ** (2.0 / 3.0))
        else:
            Nu_forced = 0.023 * Re ** 0.8 * Pr ** 0.4

        Nu = (Nu_natural ** 3 + Nu_forced ** 3) ** (1.0 / 3.0)
        return max(1.0, Nu)

    def _transitional_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        Nu_laminar = self._laminar_nusselt(Re, Pr, Gr)
        Re_c = 2300
        Re_t = 4000
        w = (Re - Re_c) / (Re_t - Re_c)
        Nu_turbulent = 0.023 * Re ** 0.8 * Pr ** 0.4
        return (1 - w) * Nu_laminar + w * Nu_turbulent

    def _turbulent_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        Ra = self.calculate_rayleigh(Gr, Pr)
        if Ra < 1e9:
            Nu_natural = 0.59 * Ra ** 0.25
        else:
            Nu_natural = 0.10 * Ra ** (1.0 / 3.0)
        Nu_forced = 0.023 * Re ** 0.8 * Pr ** 0.4
        return (Nu_natural ** 3 + Nu_forced ** 3) ** (1.0 / 3.0)

    def calculate_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        if Re < 2300:
            return self._laminar_nusselt(Re, Pr, Gr)
        elif Re < 4000:
            return self._transitional_nusselt(Re, Pr, Gr)
        else:
            return self._turbulent_nusselt(Re, Pr, Gr)

    def calculate_flow_regime(self, Re: float) -> str:
        if Re < 2300:
            return "laminar"
        elif Re < 4000:
            return "transitional"
        else:
            return "turbulent"

    def calculate_heat_transfer_coefficient(
        self,
        Nu: float,
        T_flue: float,
        T_ambient: float = 25.0,
        fuel_type: Optional[str] = None
    ) -> float:
        T_avg = (T_flue + T_ambient) / 2
        k = self._flue_gas_thermal_conductivity(T_avg, fuel_type)
        return Nu * k / self.params.flue_diameter

    def calculate_pressure_drop(
        self,
        velocity: float,
        T_flue: float,
        T_ambient: float = 25.0,
        Re: Optional[float] = None,
        fuel_type: Optional[str] = None
    ) -> float:
        if Re is None:
            Re = self.calculate_reynolds(velocity, T_flue, T_ambient, fuel_type)
        T_avg = (T_flue + T_ambient) / 2
        rho = self._flue_gas_density(T_avg, fuel_type)

        if Re < 2300:
            f = 64.0 / Re
        elif Re < 4000:
            f_lam = 64.0 / 2300
            f_turb = 0.3164 * 4000 ** (-0.25)
            w = (Re - 2300) / (4000 - 2300)
            f = (1 - w) * f_lam + w * f_turb
        elif Re < 1e5:
            f = 0.3164 * Re ** (-0.25)
        else:
            f = 0.184 * Re ** (-0.2)

        delta_P = f * (self.params.flue_length / self.params.flue_diameter) * 0.5 * rho * velocity ** 2
        return max(0.0, delta_P)

    def calculate_outlet_temperature(
        self,
        T_inlet: float,
        T_ambient: float,
        velocity: float,
        h: Optional[float] = None,
        Re: Optional[float] = None,
        Pr: Optional[float] = None,
        Gr: Optional[float] = None,
        fuel_type: Optional[str] = None
    ) -> float:
        if h is None:
            if Re is None:
                Re = self.calculate_reynolds(velocity, T_inlet, T_ambient, fuel_type)
            if Pr is None:
                Pr = self.calculate_prandtl(T_inlet, T_ambient, fuel_type)
            if Gr is None:
                Gr = self.calculate_grashof(T_inlet, T_ambient, fuel_type)
            Nu = self.calculate_nusselt(Re, Pr, Gr)
            h = self.calculate_heat_transfer_coefficient(Nu, T_inlet, T_ambient, fuel_type)

        T_avg = (T_inlet + T_ambient) / 2
        rho = self._flue_gas_density(T_avg, fuel_type)
        cp = self._flue_gas_specific_heat(T_avg, fuel_type)
        A = self.params.flue_cross_section_area
        m_dot = rho * velocity * A

        if m_dot <= 0:
            return T_inlet

        P_perimeter = math.pi * self.params.flue_diameter
        exponent = -(h * P_perimeter * self.params.flue_length) / (m_dot * cp)
        exponent = max(-10.0, min(0.0, exponent))

        T_outlet = T_ambient + (T_inlet - T_ambient) * math.exp(exponent)
        return T_outlet

    def calculate_settling_efficiency(
        self,
        T_inlet: float,
        T_outlet: float,
        velocity: float,
        residence_time: Optional[float] = None,
        fuel_type: Optional[str] = None
    ) -> float:
        fuel = self.get_fuel_properties(fuel_type)

        if residence_time is None:
            residence_time = self.params.flue_length / max(velocity, 0.01)

        cooling_ratio = (T_inlet - T_outlet) / max(T_inlet - 25.0, 1.0)
        cooling_ratio = max(0.0, min(1.0, cooling_ratio))

        d_particle = 2.5e-6
        rho_particle = fuel["smoke_particle_density"]
        T_avg = (T_inlet + T_outlet) / 2
        mu = self._flue_gas_viscosity(T_avg, fuel_type)

        v_settling = (rho_particle * self.g * d_particle ** 2) / (18.0 * mu)

        flue_height = self.params.flue_length * 0.3
        settling_time = flue_height / max(v_settling, 1e-9)

        time_ratio = residence_time / max(settling_time, 1e-6)
        time_ratio = max(0.0, min(1.0, time_ratio))

        efficiency = 0.4 * cooling_ratio + 0.6 * time_ratio
        efficiency = efficiency * 100.0
        return max(0.0, min(95.0, efficiency))

    def simulate(
        self,
        flue_temperature: float,
        flue_velocity: float,
        ambient_temperature: float = 25.0,
        ambient_humidity: float = 50.0,
        oil_consumption: Optional[float] = None,
        fuel_type: Optional[str] = None
    ) -> Dict:
        T_inlet = flue_temperature
        T_ambient = ambient_temperature

        if fuel_type and fuel_type != self.current_fuel_type:
            self.set_fuel_type(fuel_type)

        fuel = self.get_fuel_properties()

        combustion_correction = fuel["combustion_efficiency"]
        T_inlet_corrected = T_inlet * combustion_correction + T_ambient * (1 - combustion_correction)

        Re = self.calculate_reynolds(flue_velocity, T_inlet_corrected, T_ambient, fuel_type)
        Pr = self.calculate_prandtl(T_inlet_corrected, T_ambient, fuel_type)
        Gr = self.calculate_grashof(T_inlet_corrected, T_ambient, fuel_type)
        Nu = self.calculate_nusselt(Re, Pr, Gr)
        h = self.calculate_heat_transfer_coefficient(Nu, T_inlet_corrected, T_ambient, fuel_type)
        delta_P = self.calculate_pressure_drop(flue_velocity, T_inlet_corrected, T_ambient, Re, fuel_type)
        T_outlet = self.calculate_outlet_temperature(
            T_inlet_corrected, T_ambient, flue_velocity, h, Re, Pr, Gr, fuel_type
        )
        flow_regime = self.calculate_flow_regime(Re)

        mass_flow_in = self._flue_gas_density(T_inlet_corrected, fuel_type) * flue_velocity * self.params.flue_cross_section_area
        mass_flow_out = self._flue_gas_density(T_outlet, fuel_type) * flue_velocity * self.params.flue_cross_section_area
        outlet_velocity = flue_velocity * (mass_flow_in / max(mass_flow_out, 1e-9))

        settling_efficiency = self.calculate_settling_efficiency(
            T_inlet_corrected, T_outlet, flue_velocity, None, fuel_type
        )

        result = {
            "time": datetime.now(),
            "fuel_type": fuel_type or self.current_fuel_type,
            "fuel_name": fuel["name"],
            "heating_value": fuel["heating_value"],
            "reynolds_number": round(Re, 2),
            "prandtl_number": round(Pr, 4),
            "nusselt_number": round(Nu, 4),
            "heat_transfer_coeff": round(h, 4),
            "pressure_drop": round(delta_P, 4),
            "settling_efficiency": round(settling_efficiency, 2),
            "outlet_temperature": round(T_outlet, 2),
            "outlet_velocity": round(outlet_velocity, 4),
            "flow_regime": flow_regime,
        }

        logger.debug(
            f"烟道仿真完成: 燃料={fuel['name']}, "
            f"Re={Re:.1f}, Pr={Pr:.3f}, Nu={Nu:.2f}, "
            f"h={h:.2f}W/m²·K, ΔP={delta_P:.2f}Pa, "
            f"T_out={T_outlet:.1f}°C, 沉降效率={settling_efficiency:.1f}%, 流型={flow_regime}"
        )

        return result

    def get_flow_path_points(self, num_points: int = 50) -> list:
        points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            x = 0.0
            y = t * self.params.flue_length
            z = 0.0
            points.append((x, y, z))
        return points

    def get_particle_trajectory(
        self,
        start_pos: tuple,
        flue_velocity: float,
        T_inlet: float,
        T_ambient: float = 25.0,
        dt: float = 0.01,
        num_steps: int = 200,
        fuel_type: Optional[str] = None
    ) -> list:
        trajectory = [start_pos]
        x, y, z = start_pos

        fuel = self.get_fuel_properties(fuel_type)
        rho_particle = fuel["smoke_particle_density"]

        for _ in range(num_steps):
            T_local = T_inlet - (T_inlet - T_ambient) * (y / max(self.params.flue_length, 0.01))
            T_local = max(T_ambient, T_local)
            Re = self.calculate_reynolds(flue_velocity, T_local, T_ambient, fuel_type)
            T_avg = (T_local + T_ambient) / 2
            rho = self._flue_gas_density(T_avg, fuel_type)
            mu = self._flue_gas_viscosity(T_avg, fuel_type)

            d_particle = 2.5e-6
            v_rel_x = 0
            v_rel_y = flue_velocity - 0
            v_rel_z = 0
            drag_coeff = 6.0 * math.pi * mu * (d_particle / 2.0)
            F_drag_x = drag_coeff * v_rel_x
            F_drag_y = drag_coeff * v_rel_y
            F_drag_z = drag_coeff * v_rel_z
            F_buoyancy = (4.0 / 3.0) * math.pi * (d_particle / 2.0) ** 3 * (rho - rho_particle) * self.g

            mass_particle = (4.0 / 3.0) * math.pi * (d_particle / 2.0) ** 3 * rho_particle
            ax = F_drag_x / max(mass_particle, 1e-20)
            ay = (F_drag_y + F_buoyancy) / max(mass_particle, 1e-20)
            az = F_drag_z / max(mass_particle, 1e-20)

            vx = 0 + ax * dt
            vy = flue_velocity * 0.8 + ay * dt
            vz = 0 + az * dt

            x += vx * dt
            y += vy * dt
            z += vz * dt

            r_max = self.params.flue_diameter / 2
            r = math.sqrt(x ** 2 + z ** 2)
            if r > r_max:
                scale = r_max / r
                x *= scale
                z *= scale

            if y >= self.params.flue_length:
                trajectory.append((x, self.params.flue_length, z))
                break

            trajectory.append((x, y, z))

        return trajectory
