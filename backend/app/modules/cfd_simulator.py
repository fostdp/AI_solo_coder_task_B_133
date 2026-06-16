"""
cfd_simulator 模块：烟道流场和温度计算

职责：
  1. 从消息总线订阅 CFD_INPUT
  2. 基于外置 JSON 配置的几何/物性/传热参数运行层流/湍流/过渡流分区仿真
  3. 计算结果持久化到 flue_simulation 超表
  4. 向消息总线发布：
     - CFD_RESULT: 完整仿真结果 + 原始输入字段（供后续 AQ 模块使用）

订阅：CFD_INPUT
发布：CFD_RESULT
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select

from ..bus import MessageBus, CFD_INPUT, CFD_RESULT
from ..models.lamp import FlueSimulation
from ..config_loader import load_fuel_config, load_cfd_config

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 数据类
# ----------------------------------------------------------------------
class CFDGeometryParams:
    def __init__(self, cfg: Dict[str, Any]):
        self.flue_length = cfg["flue_geometry"]["flue_length_m"]
        self.flue_diameter = cfg["flue_geometry"]["flue_diameter_m"]
        self.wall_thickness = cfg["flue_geometry"]["flue_wall_thickness_m"]
        self.bend_count = cfg["flue_geometry"]["bend_count"]
        self.bend_angle = cfg["flue_geometry"]["bend_angle_deg"]


class CFDFluidConstants:
    def __init__(self, cfg: Dict[str, Any]):
        d = cfg["fluid_properties"]
        self.T_ref = d["reference_temperature_k"]
        self.M_air = d["air_molar_mass_gmol"]
        self.R = d["universal_gas_constant_jkmol"]
        self.P_atm = d["standard_atmosphere_pa"]
        self.Suth_C = d["sutherland_constant_c_k"]
        self.Suth_T0 = d["sutherland_reference_temperature_k"]
        self.Suth_mu0 = d["sutherland_reference_viscosity_pas"]
        self.beta_inv = d["thermal_expansion_coefficient_ideal_gas_inv"]


class CFDHeatTransferConstants:
    def __init__(self, cfg: Dict[str, Any]):
        d = cfg["heat_transfer"]
        self.k_wall = d["wall_thermal_conductivity_wmk"]
        self.h_amb = d["natural_convection_coefficient_ambient_wm2k"]
        self.eps_rad = d["radiation_emissivity"]
        self.sigma = d["stefan_boltzmann_constant_wm2k4"]
        self.Nu_forced_lam = d["nusselt_laminar_forced_constant"]
        self.Nu_db_coeff = d["nusselt_turbulent_dittus_boelter_coeff"]
        self.n_heat = d["dittus_boelter_exponent_heating"]
        self.n_cool = d["dittus_boelter_exponent_cooling"]
        self.Nu_nat_lam = d["nusselt_natural_laminar_coeff"]
        self.Nu_nat_turb = d["nusselt_natural_turbulent_coeff"]
        self.Ra_crit = d["nusselt_natural_laminar_rayleigh_max"]
        self.Re_lower = d["critical_reynolds_lower"]
        self.Re_upper = d["critical_reynolds_upper"]
        self.Pr_air_ref = d["prandtl_number_air_reference"]


# ----------------------------------------------------------------------
# 主模块类
# ----------------------------------------------------------------------
class CFDSimulator:
    g = 9.81

    def __init__(self, db: AsyncSession, bus: MessageBus):
        self.db = db
        self.bus = bus

        cfd_cfg = load_cfd_config()
        fuel_cfg = load_fuel_config()

        self.params = CFDGeometryParams(cfd_cfg)
        self.fluid = CFDFluidConstants(cfd_cfg)
        self.heat = CFDHeatTransferConstants(cfd_cfg)
        self.pressure_cfg = cfd_cfg["pressure_loss"]
        self.settle_cfg = cfd_cfg["particle_settling"]
        self.traj_cfg = cfd_cfg["trajectory_simulation"]

        self.FUEL_TYPES = fuel_cfg["fuel_types"]
        self.MODBUS_TO_FUEL = fuel_cfg["modbus_mapping"]
        self.current_fuel_type = "animal_fat"
        self._bus_bound = False

    # ------------------------------------------------------------------
    # 消息总线绑定
    # ------------------------------------------------------------------
    async def bind_to_bus(self):
        if self._bus_bound:
            return
        await self.bus.subscribe(CFD_INPUT, self._on_cfd_input)
        self._bus_bound = True

    async def _on_cfd_input(self, payload: Dict[str, Any]):
        try:
            lamp_id = payload.get("lamp_id", 0)
            t_str = payload.get("time", datetime.now().isoformat())
            t = datetime.fromisoformat(t_str) if isinstance(t_str, str) else t_str
            result = self.simulate(
                flue_temperature=payload["flue_temperature"],
                flue_velocity=payload["flue_velocity"],
                ambient_temperature=payload.get("ambient_temperature", 22.0),
                ambient_humidity=payload.get("ambient_humidity", 50.0),
                oil_consumption=payload.get("oil_consumption", 0.0),
                fuel_type=payload.get("fuel_type", self.current_fuel_type),
            )
            # 持久化（失败不阻断管线）
            try:
                stmt = insert(FlueSimulation).values(
                    time=t,
                    lamp_id=lamp_id,
                    reynolds_number=result["reynolds_number"],
                    prandtl_number=result["prandtl_number"],
                    nusselt_number=result["nusselt_number"],
                    heat_transfer_coeff=result["heat_transfer_coeff"],
                    pressure_drop=result["pressure_drop"],
                    settling_efficiency=result["settling_efficiency"],
                    outlet_temperature=result["outlet_temperature"],
                    outlet_velocity=result["outlet_velocity"],
                    flow_regime=result["flow_regime"],
                )
                await self.db.execute(stmt)
                await self.db.commit()
            except Exception as db_e:
                logger.warning(f"[cfd_simulator] 持久化失败 (DB未就绪？): {db_e}")

            # 发布结果 + 传递原始字段给下游 AQ
            out_payload = {
                "correlation_id": payload.get("correlation_id"),
                "lamp_id": lamp_id,
                "time": payload["time"],
                **payload,
                "cfd": result,
            }
            await self.bus.publish(CFD_RESULT, out_payload)
            logger.info(f"[cfd_simulator] lamp#{lamp_id} Re={result['reynolds_number']:.1f} "
                        f"settling={result['settling_efficiency']*100:.1f}% "
                        f"flow={result['flow_regime']}")
        except Exception as e:
            logger.exception(f"[cfd_simulator] 处理失败: {e}")
            await self.db.rollback()

    # ------------------------------------------------------------------
    # 燃料查询
    # ------------------------------------------------------------------
    def get_fuel_properties(self, fuel_type: Optional[str] = None) -> Dict[str, Any]:
        key = fuel_type or self.current_fuel_type
        if key not in self.FUEL_TYPES:
            key = self.current_fuel_type
        return self.FUEL_TYPES[key]

    def set_fuel_type(self, fuel_type: str):
        if fuel_type in self.FUEL_TYPES:
            self.current_fuel_type = fuel_type

    # ------------------------------------------------------------------
    # 烟气混合物性
    # ------------------------------------------------------------------
    def _flue_gas_molar_fractions(self, fuel_type: Optional[str]) -> Dict[str, float]:
        """估算 N₂/CO₂/H₂O 的摩尔分数（简化，基于排放因子）"""
        fuel = self.get_fuel_properties(fuel_type)
        co2_factor = fuel["co2_emission_factor_kgkg"]
        h2o_factor = fuel["h2o_emission_factor_kgkg"]
        # 空气助燃近似: 每kg燃料需要 ~12kg 空气
        n2_from_air = 12.0 * 0.77 / 28.01
        o2_for_combus = co2_factor / 44.01 * 1.0 + h2o_factor / 18.016 * 0.5
        total = n2_from_air + (12.0 * 0.23 / 32.0 - o2_for_combus) * 0.0 + co2_factor / 44.01 + h2o_factor / 18.016
        total = max(total, 1e-9)
        x_co2 = (co2_factor / 44.01) / total
        x_h2o = (h2o_factor / 18.016) / total
        x_n2 = max(0.0, 1.0 - x_co2 - x_h2o)
        return {"N2": x_n2, "CO2": x_co2, "H2O": x_h2o}

    def _sutherland_viscosity(self, T: float, species: str) -> float:
        """Sutherland 公式计算单组分粘度"""
        if species == "N2":
            C, T0, mu0 = 111.0, 300.55, 17.81e-6
        elif species == "CO2":
            C, T0, mu0 = 222.0, 273.15, 13.80e-6
        elif species == "H2O":
            C, T0, mu0 = 673.0, 373.15, 12.11e-6
        else:
            C, T0, mu0 = 110.4, 273.15, 1.716e-5
        return mu0 * (T / T0) ** 1.5 * (T0 + C) / (T + C)

    def _flue_gas_viscosity(self, T_c: float, fuel_type: Optional[str] = None) -> float:
        T = T_c + 273.15
        x = self._flue_gas_molar_fractions(fuel_type)
        M = {"N2": 28.01, "CO2": 44.01, "H2O": 18.016}
        numerator, denominator = 0.0, 0.0
        for sp, xi in x.items():
            if xi <= 0:
                continue
            mu_i = self._sutherland_viscosity(T, sp)
            Mi_sqrt = math.sqrt(M[sp])
            numerator += xi * mu_i * Mi_sqrt
            denominator += xi * Mi_sqrt
        return numerator / max(denominator, 1e-15)

    def _flue_gas_density(self, T_c: float, fuel_type: Optional[str] = None, P_pa: Optional[float] = None) -> float:
        P = P_pa or self.fluid.P_atm
        x = self._flue_gas_molar_fractions(fuel_type)
        M_mix = x["N2"] * 28.01 + x["CO2"] * 44.01 + x["H2O"] * 18.016
        R_mix = self.fluid.R / max(M_mix, 1e-9)
        return P / max(R_mix * (T_c + 273.15), 1e-6)

    def _flue_gas_thermal_conductivity(self, T_c: float, fuel_type: Optional[str] = None) -> float:
        T = T_c + 273.15
        x = self._flue_gas_molar_fractions(fuel_type)
        k_N2 = 0.0241 * (T / 273.15) ** 0.8
        k_CO2 = 0.0146 * (T / 273.15) ** 0.9
        k_H2O = 0.0181 * (T / 273.15) ** 1.0
        k_mix = x["N2"] * k_N2 + x["CO2"] * k_CO2 + x["H2O"] * k_H2O
        k_corr = 1.0 + 0.1 * x["CO2"] + 0.15 * x["H2O"]
        return k_mix * k_corr

    def _flue_gas_specific_heat(self, T_c: float, fuel_type: Optional[str] = None) -> float:
        T = T_c + 273.15
        x = self._flue_gas_molar_fractions(fuel_type)
        Cp_N2 = 1039.0 - 0.157 * T + 3.14e-4 * T ** 2
        Cp_CO2 = 597.0 + 1.33 * T - 8.20e-4 * T ** 2
        Cp_H2O = 1854.0 + 0.620 * T + 2.00e-4 * T ** 2
        return x["N2"] * Cp_N2 + x["CO2"] * Cp_CO2 + x["H2O"] * Cp_H2O

    def _calculate_buoyancy_correction(
        self, T_flue: float, T_ambient: float, fuel_type: Optional[str] = None
    ) -> float:
        rho_amb_air = self._flue_gas_density(T_ambient, fuel_type=None)
        rho_flue = self._flue_gas_density(T_flue, fuel_type)
        rho_amb_flue = self._flue_gas_density(T_ambient, fuel_type)
        ideal = (rho_amb_air - rho_flue) / max(rho_amb_flue - rho_flue, 1e-9)
        corr = max(0.8, min(1.5, ideal))
        return corr

    # ------------------------------------------------------------------
    # 无量纲数
    # ------------------------------------------------------------------
    def calculate_reynolds(
        self, velocity: float, T_local: float, T_ambient: float, fuel_type: Optional[str] = None
    ) -> float:
        T_avg = (T_local + T_ambient) / 2.0
        rho = self._flue_gas_density(T_avg, fuel_type)
        mu = self._flue_gas_viscosity(T_avg, fuel_type)
        return rho * velocity * self.params.flue_diameter / max(mu, 1e-15)

    def calculate_prandtl(self, T_local: float, T_ambient: float, fuel_type: Optional[str] = None) -> float:
        T_avg = (T_local + T_ambient) / 2.0
        mu = self._flue_gas_viscosity(T_avg, fuel_type)
        Cp = self._flue_gas_specific_heat(T_avg, fuel_type)
        k = self._flue_gas_thermal_conductivity(T_avg, fuel_type)
        return mu * Cp / max(k, 1e-15)

    def calculate_grashof(
        self, T_flue: float, T_ambient: float, fuel_type: Optional[str] = None
    ) -> float:
        T_avg = (T_flue + T_ambient) / 2.0
        L = self.params.flue_length
        beta = 1.0 / max(T_avg + 273.15, 1e-6)
        nu = self._flue_gas_viscosity(T_avg, fuel_type) / max(
            self._flue_gas_density(T_avg, fuel_type), 1e-9
        )
        dT = max(abs(T_flue - T_ambient), 0.1)
        beta_correction = self._calculate_buoyancy_correction(T_flue, T_ambient, fuel_type)
        return self.g * beta * dT * L ** 3 / max(nu ** 2, 1e-25) * beta_correction

    def _laminar_nusselt(self, Re, Pr, Gr):
        GrPr = max(Gr * Pr, 1e-12)
        Nu_natural = self.heat.Nu_nat_lam * GrPr ** 0.25
        Ra_crit = self.heat.Ra_crit
        if GrPr > Ra_crit:
            Nu_natural = self.heat.Nu_nat_turb * GrPr ** (1.0 / 3.0)
        Nu_forced = self.heat.Nu_forced_lam
        return (Nu_natural ** 3 + Nu_forced ** 3) ** (1.0 / 3.0)

    def _turbulent_nusselt(self, Re, Pr, Gr, heating=True):
        n = self.heat.n_heat if heating else self.heat.n_cool
        Nu_forced = self.heat.Nu_db_coeff * (max(Re, 1.0) ** 0.8) * (max(Pr, 0.1) ** n)
        GrPr = max(Gr * Pr, 1e-12)
        Nu_natural = self.heat.Nu_nat_lam * GrPr ** 0.25
        if GrPr > self.heat.Ra_crit:
            Nu_natural = self.heat.Nu_nat_turb * GrPr ** (1.0 / 3.0)
        return (Nu_natural ** 3 + Nu_forced ** 3) ** (1.0 / 3.0)

    def _transitional_nusselt(self, Re, Pr, Gr, Re_low, Re_high):
        Nu_lam = self._laminar_nusselt(Re_low + 10, Pr, Gr)
        Nu_turb = self._turbulent_nusselt(Re_high - 10, Pr, Gr)
        w = (Re - Re_low) / max(Re_high - Re_low, 1e-6)
        return (1 - w) * Nu_lam + w * Nu_turb

    def calculate_nusselt(self, Re, Pr, Gr, T_flue, T_ambient):
        Re_low, Re_high = self.heat.Re_lower, self.heat.Re_upper
        heating = T_flue > T_ambient
        if Re < Re_low:
            return self._laminar_nusselt(Re, Pr, Gr)
        elif Re < Re_high:
            return self._transitional_nusselt(Re, Pr, Gr, Re_low, Re_high)
        else:
            return self._turbulent_nusselt(Re, Pr, Gr, heating)

    def flow_regime(self, Re: float) -> str:
        if Re < self.heat.Re_lower:
            return "LAMINAR"
        elif Re < self.heat.Re_upper:
            return "TRANSITIONAL"
        return "TURBULENT"

    # ------------------------------------------------------------------
    # 仿真主入口
    # ------------------------------------------------------------------
    def simulate(
        self,
        flue_temperature: float,
        flue_velocity: float,
        ambient_temperature: float = 22.0,
        ambient_humidity: float = 50.0,
        oil_consumption: float = 1.0,
        fuel_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        if fuel_type:
            self.set_fuel_type(fuel_type)
        fuel = self.get_fuel_properties(fuel_type)
        eta_comb = fuel["combustion_efficiency"]
        T_in = flue_temperature * eta_comb + ambient_temperature * (1 - eta_comb)

        Re = self.calculate_reynolds(flue_velocity, T_in, ambient_temperature, fuel_type)
        Pr = self.calculate_prandtl(T_in, ambient_temperature, fuel_type)
        Gr = self.calculate_grashof(T_in, ambient_temperature, fuel_type)
        Nu = self.calculate_nusselt(Re, Pr, Gr, T_in, ambient_temperature)
        T_avg = (T_in + ambient_temperature) / 2
        k = self._flue_gas_thermal_conductivity(T_avg, fuel_type)
        h = Nu * k / max(self.params.flue_diameter, 1e-6)

        # 压力降
        D = self.params.flue_diameter
        L = self.params.flue_length
        rho = self._flue_gas_density(T_avg, fuel_type)
        mu = self._flue_gas_viscosity(T_avg, fuel_type)
        if Re < self.heat.Re_lower:
            f = self.pressure_cfg["darcy_friction_laminar_constant"] / max(Re, 1e-6)
        elif Re < self.heat.Re_upper:
            w = (Re - self.heat.Re_lower) / max(self.heat.Re_upper - self.heat.Re_lower, 1e-6)
            f_lam = self.pressure_cfg["darcy_friction_laminar_constant"] / max(Re, 1e-6)
            f_turb = 0.3164 * (max(Re, 1.0) ** -0.25)
            f = (1 - w) * f_lam + w * f_turb
        else:
            f = 0.3164 * (Re ** -0.25)
        K_bends = self.pressure_cfg["bend_loss_coefficient_90deg"] * self.params.bend_count * (self.params.bend_angle / 90.0)
        K_total = self.pressure_cfg["entrance_loss_coefficient"] + self.pressure_cfg["exit_loss_coefficient"] + K_bends
        dP_friction = f * (L / max(D, 1e-6)) * 0.5 * rho * flue_velocity ** 2
        dP_minor = K_total * 0.5 * rho * flue_velocity ** 2
        dP = dP_friction + dP_minor

        # 出口温度
        Cp = self._flue_gas_specific_heat(T_avg, fuel_type)
        A_cross = math.pi * (D / 2.0) ** 2
        P_wet = math.pi * D
        mass_flow = rho * flue_velocity * A_cross
        if mass_flow > 1e-9 and Cp > 0:
            exponent = h * P_wet * L / max(mass_flow * Cp, 1e-12)
            T_out = ambient_temperature + (T_in - ambient_temperature) * math.exp(-exponent)
        else:
            T_out = T_in

        # 沉降效率
        cooling_ratio = (T_in - max(T_out, ambient_temperature)) / max(T_in - ambient_temperature, 1e-6)
        mean_velocity = max(flue_velocity, 1e-3)
        residence_time = L / max(mean_velocity, 1e-9)
        time_ratio = min(residence_time / max(self.settle_cfg["settling_max_residence_time_s"], 1e-6), 1.0)
        efficiency = (
            self.settle_cfg["settling_efficiency_cooling_weight"] * cooling_ratio
            + self.settle_cfg["settling_efficiency_time_weight"] * time_ratio
        )
        efficiency = max(self.settle_cfg["settling_min_efficiency_floor"], min(efficiency, 0.98))

        # 出口流速 (质量守恒)
        rho_out = self._flue_gas_density(T_out, fuel_type)
        v_out = flue_velocity * (rho / max(rho_out, 1e-9))

        return {
            "reynolds_number": round(Re, 4),
            "prandtl_number": round(Pr, 4),
            "grashof_number": round(Gr, 4),
            "nusselt_number": round(Nu, 4),
            "heat_transfer_coeff": round(h, 4),
            "pressure_drop": round(dP, 4),
            "settling_efficiency": round(efficiency, 6),
            "outlet_temperature": round(T_out, 4),
            "outlet_velocity": round(v_out, 6),
            "flow_regime": self.flow_regime(Re),
            "fuel_type": fuel_type or self.current_fuel_type,
            "fuel_name": fuel["name"],
            "heating_value_mjkg": fuel["heating_value_mjkg"],
            "combustion_efficiency": eta_comb,
            "mass_flow_rate_kg_s": round(mass_flow, 8),
            "temperature_drop_c": round(T_in - T_out, 4),
        }

    # ------------------------------------------------------------------
    # 粒子轨迹（用于前端可视化 API）
    # ------------------------------------------------------------------
    def get_particle_trajectory(
        self,
        start_pos: Tuple[float, float, float],
        flue_velocity: float,
        T_inlet: float,
        T_ambient: float = 25.0,
        dt: Optional[float] = None,
        num_steps: Optional[int] = None,
        fuel_type: Optional[str] = None,
    ) -> List[Tuple[float, float, float]]:
        dt = dt or self.traj_cfg["default_dt_s"]
        num_steps = num_steps or self.traj_cfg["default_num_steps"]
        fuel = self.get_fuel_properties(fuel_type)
        rho_particle = fuel["smoke_particle_density_kgm3"]

        trajectory: List[Tuple[float, float, float]] = [start_pos]
        x, y, z = start_pos
        r_max = self.params.flue_diameter / 2
        d_particle = self.traj_cfg["particle_stokes_diameter_m"]

        for _ in range(num_steps):
            T_local = T_inlet - (T_inlet - T_ambient) * (y / max(self.params.flue_length, 0.01))
            T_local = max(T_ambient, T_local)
            Re = self.calculate_reynolds(flue_velocity, T_local, T_ambient, fuel_type)
            T_avg = (T_local + T_ambient) / 2
            rho = self._flue_gas_density(T_avg, fuel_type)
            mu = self._flue_gas_viscosity(T_avg, fuel_type)

            v_rel_x = 0.0
            v_rel_y = flue_velocity
            v_rel_z = 0.0
            drag_coeff = 6.0 * math.pi * mu * (d_particle / 2.0)
            F_drag_y = drag_coeff * v_rel_y
            F_buoyancy = (
                (4.0 / 3.0) * math.pi * (d_particle / 2.0) ** 3
                * (rho - rho_particle) * self.g
            )
            mass_particle = (4.0 / 3.0) * math.pi * (d_particle / 2.0) ** 3 * rho_particle
            ay = (F_drag_y + F_buoyancy) / max(mass_particle, 1e-20)
            vy = flue_velocity * self.traj_cfg["particle_initial_velocity_factor"] + ay * dt
            vx, vz = 0.0, 0.0

            x += vx * dt
            y += vy * dt
            z += vz * dt

            r = math.sqrt(x ** 2 + z ** 2)
            if r > r_max:
                scale = r_max / max(r, 1e-9)
                x *= scale
                z *= scale

            if y >= self.params.flue_length:
                trajectory.append((x, self.params.flue_length, z))
                break
            trajectory.append((x, y, z))

        return trajectory
