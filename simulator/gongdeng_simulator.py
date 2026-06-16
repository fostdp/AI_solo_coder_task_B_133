#!/usr/bin/env python3
"""
长信宫灯传感器模拟器 - Modbus TCP协议
模拟灯油消耗、烟道温度、烟气流速、室内PM2.5浓度等传感器数据
每分钟上报一次数据
"""

import asyncio
import random
import math
import logging
import json
import os
from datetime import datetime
from pyModbusTCP.server import ModbusServer, DataBank
from pyModbusTCP.client import ModbusClient
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("GongdengSimulator")


FUEL_TYPES = {
    "animal_fat": {"name": "动物脂肪", "heating_value": 37.5, "modbus_value": 1, "temp_factor": 1.0},
    "sesame_oil": {"name": "麻油", "heating_value": 39.3, "modbus_value": 2, "temp_factor": 1.03},
    "beeswax": {"name": "蜜蜡", "heating_value": 40.6, "modbus_value": 3, "temp_factor": 1.05},
    "mineral_oil": {"name": "矿物油", "heating_value": 44.0, "modbus_value": 4, "temp_factor": 1.12},
    "tallow": {"name": "牛油", "heating_value": 39.0, "modbus_value": 5, "temp_factor": 1.02},
}

MODBUS_TO_FUEL = {v["modbus_value"]: k for k, v in FUEL_TYPES.items()}


class GongdengSensorSimulator:
    """长信宫灯传感器模拟器"""

    def __init__(
        self,
        lamp_id: int = 1,
        modbus_host: str = "0.0.0.0",
        modbus_port: int = 502,
        api_url: str = "http://localhost:8000",
        enable_modbus: bool = True,
        enable_http: bool = True,
        fuel_type: str = "animal_fat",
        air_change_rate: float = 1.0,
        outdoor_pm25: float = 25.0
    ):
        self.lamp_id = lamp_id
        self.modbus_host = modbus_host
        self.modbus_port = modbus_port
        self.api_url = api_url
        self.enable_modbus = enable_modbus
        self.enable_http = enable_http

        self.fuel_type = fuel_type
        self.air_change_rate = air_change_rate
        self.outdoor_pm25 = outdoor_pm25

        self.oil_level = 500.0
        self.base_flue_temp = 25.0
        self.base_flue_velocity = 0.5
        self.base_pm25 = 35.0
        self.base_oil_consumption = 2.0

        self.flame_intensity = 0.8
        self.blockage_factor = 1.0
        self.blockage_degree = 0.0

        self.modbus_server = None
        self._init_modbus_registers()

    def _init_modbus_registers(self):
        self.registers = {
            0: 0,
            1: 0,
            2: 0,
            3: 0,
            4: 0,
            5: 0,
            6: 0,
            7: 0,
            8: 0,
            9: 0,
            10: 0,
            11: 0,
            12: 0,
        }

    def _update_modbus_registers(self, data: dict):
        scale = 100
        try:
            self.registers[0] = int(data['oil_consumption'] * scale)
            self.registers[1] = int(data['flue_temperature'] * scale)
            self.registers[2] = int(data['flue_velocity'] * scale)
            self.registers[3] = int(data['indoor_pm25'] * scale)
            self.registers[4] = int(data['oil_level'] * scale)
            self.registers[5] = int(data['ambient_temperature'] * scale)
            self.registers[6] = int(data['ambient_humidity'] * scale)
            self.registers[7] = int(data['lamp_id'])
            self.registers[8] = int(data['timestamp'] % 65536)
            self.registers[9] = int(data['timestamp'] / 65536)
            self.registers[10] = int(FUEL_TYPES.get(data['fuel_type'], {}).get('modbus_value', 1))
            self.registers[11] = int(data['air_change_rate'] * scale)
            self.registers[12] = int(data['outdoor_pm25'] * scale)

            if self.modbus_server:
                for addr, value in self.registers.items():
                    self.modbus_server.data_bank.set_holding_registers(addr, [max(0, min(65535, value))])
        except Exception as e:
            logger.error(f"更新Modbus寄存器失败: {e}")

    def set_fuel_type(self, fuel_type: str):
        """设置燃料类型"""
        if fuel_type in FUEL_TYPES:
            self.fuel_type = fuel_type
            logger.info(f"燃料类型已切换为: {FUEL_TYPES[fuel_type]['name']}")

    def _simulate_oil_consumption(self) -> float:
        base = self.base_oil_consumption * self.flame_intensity
        noise = random.gauss(0, 0.1)
        return max(0.1, base + noise)

    def _simulate_flue_temperature(self) -> float:
        fuel = FUEL_TYPES.get(self.fuel_type, FUEL_TYPES["animal_fat"])
        base_temp = self.base_flue_temp + (180.0 - self.base_flue_temp) * self.flame_intensity
        base_temp = base_temp * fuel["temp_factor"]
        cooling_effect = self.blockage_factor * 0.8
        base = base_temp * cooling_effect
        noise = random.gauss(0, 3.0)
        return max(self.base_flue_temp, base + noise)

    def _simulate_flue_velocity(self) -> float:
        base = self.base_flue_velocity * self.flame_intensity
        base = base / self.blockage_factor
        noise = random.gauss(0, 0.05)
        return max(0.01, base + noise)

    def _simulate_pm25(self, velocity: float) -> float:
        base = self.base_pm25
        smoke_emission = self.flame_intensity * 15.0
        settling_effect = velocity * 0.3
        pm25 = base + smoke_emission - settling_effect
        if self.blockage_degree > 0.3:
            pm25 += self.blockage_degree * 20.0
        noise = random.gauss(0, 3.0)
        daily_cycle = 5.0 * math.sin(datetime.now().hour * math.pi / 12)
        return max(5.0, pm25 + noise + daily_cycle)

    def _simulate_ambient(self) -> tuple:
        hour = datetime.now().hour
        temp_base = 22.0 + 4.0 * math.sin((hour - 6) * math.pi / 12)
        temp = temp_base + random.gauss(0, 0.5)
        humidity = 55.0 + 10.0 * random.gauss(0, 1)
        humidity = max(30.0, min(80.0, humidity))
        return temp, humidity

    def _random_anomaly(self):
        if getattr(self, '_inject_anomalies', True):
            r = random.random()
            if r < 0.02:
                self.blockage_degree = min(0.9, self.blockage_degree + 0.1)
                logger.warning(f"烟道堵塞程度增加: {self.blockage_degree:.2f}")
            elif r < 0.05 and self.blockage_degree > 0:
                self.blockage_degree = max(0, self.blockage_degree - 0.05)

            if random.random() < 0.03:
                self.flame_intensity = max(0.3, min(1.0, self.flame_intensity + random.gauss(0, 0.1)))

        self.blockage_factor = 1.0 + self.blockage_degree * 2.0

    def generate_sensor_data(self) -> dict:
        self._random_anomaly()

        fuel = FUEL_TYPES.get(self.fuel_type, FUEL_TYPES["animal_fat"])
        oil_consumption = self._simulate_oil_consumption()
        self.oil_level = max(0.0, self.oil_level - oil_consumption)
        if self.oil_level < 10.0:
            self.oil_level = 500.0
            logger.info("灯油已补充")

        flue_temp = self._simulate_flue_temperature()
        flue_velocity = self._simulate_flue_velocity()
        pm25 = self._simulate_pm25(flue_velocity)
        ambient_temp, ambient_humidity = self._simulate_ambient()

        timestamp = datetime.now().timestamp()

        return {
            "lamp_id": self.lamp_id,
            "oil_consumption": round(oil_consumption, 3),
            "flue_temperature": round(flue_temp, 2),
            "flue_velocity": round(flue_velocity, 3),
            "indoor_pm25": round(pm25, 2),
            "oil_level": round(self.oil_level, 2),
            "ambient_temperature": round(ambient_temp, 2),
            "ambient_humidity": round(ambient_humidity, 2),
            "blockage_degree": round(self.blockage_degree, 3),
            "fuel_type": self.fuel_type,
            "fuel_name": fuel["name"],
            "air_change_rate": round(self.air_change_rate, 2),
            "outdoor_pm25": round(self.outdoor_pm25, 2),
            "timestamp": int(timestamp),
            "time": datetime.now().isoformat()
        }

    async def start_modbus_server(self):
        if not self.enable_modbus:
            return
        try:
            self.modbus_server = ModbusServer(
                host=self.modbus_host,
                port=self.modbus_port,
                no_block=True
            )
            self.modbus_server.start()
            logger.info(f"Modbus TCP服务器已启动: {self.modbus_host}:{self.modbus_port}")
        except Exception as e:
            logger.error(f"启动Modbus服务器失败: {e}")
            self.enable_modbus = False

    async def send_to_api(self, data: dict):
        if not self.enable_http:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/api/sensor/data",
                    json=data
                )
                if response.status_code == 200:
                    logger.info(f"数据已上报API: PM2.5={data['indoor_pm25']}, 烟道温度={data['flue_temperature']}°C")
                else:
                    logger.warning(f"API上报失败: {response.status_code} - {response.text}")
        except Exception as e:
            logger.warning(f"API连接失败: {e}")

    async def read_via_modbus_client(self) -> dict:
        try:
            client = ModbusClient(host=self.modbus_host, port=self.modbus_port, auto_open=True)
            regs = client.read_holding_registers(0, 10)
            client.close()
            if regs:
                scale = 100.0
                return {
                    "oil_consumption": regs[0] / scale,
                    "flue_temperature": regs[1] / scale,
                    "flue_velocity": regs[2] / scale,
                    "indoor_pm25": regs[3] / scale,
                    "oil_level": regs[4] / scale,
                    "ambient_temperature": regs[5] / scale,
                    "ambient_humidity": regs[6] / scale,
                    "lamp_id": regs[7],
                }
        except Exception as e:
            logger.error(f"Modbus读取失败: {e}")
        return {}

    async def run(self):
        logger.info("=" * 60)
        logger.info("长信宫灯传感器模拟器启动")
        logger.info(f"灯ID: {self.lamp_id}")
        logger.info(f"Modbus TCP: {self.modbus_host}:{self.modbus_port}")
        logger.info(f"API地址: {self.api_url}")
        logger.info("=" * 60)

        await self.start_modbus_server()

        while True:
            try:
                data = self.generate_sensor_data()

                if self.enable_modbus and self.modbus_server:
                    self._update_modbus_registers(data)

                if self.enable_http:
                    await self.send_to_api(data)

                if self.enable_modbus:
                    read_data = await self.read_via_modbus_client()
                    if read_data:
                    logger.debug(f"Modbus读取验证: {json.dumps(read_data, ensure_ascii=False)}")

                await asyncio.sleep(getattr(self, '_report_interval', 60))

            except KeyboardInterrupt:
                logger.info("模拟器已停止")
                break
            except Exception as e:
                logger.error(f"运行错误: {e}")
                await asyncio.sleep(5)


def _str_to_bool(s: str) -> bool:
    """将字符串转换为布尔值"""
    return str(s).lower() in ("true", "1", "yes", "y", "on")


async def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="长信宫灯Modbus TCP传感器模拟器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置
  python gongdeng_simulator.py

  # 指定燃料类型和通风率
  python gongdeng_simulator.py --fuel-type beeswax --air-change-rate 2.5

  # 禁用异常注入，稳定输出
  python gongdeng_simulator.py --no-anomalies --fuel-type mineral_oil

  # 仅HTTP上报，不启用Modbus
  python gongdeng_simulator.py --no-modbus --report-interval 30

支持的燃料类型:
  animal_fat  (动物脂肪, 热值37.5 MJ/kg)
  sesame_oil  (麻油,     热值39.3 MJ/kg)
  beeswax     (蜜蜡,     热值40.6 MJ/kg)
  mineral_oil (矿物油,   热值44.0 MJ/kg)
  tallow      (牛油,     热值39.0 MJ/kg)
        """
    )

    # 基本配置
    parser.add_argument("--lamp-id", type=int,
                        default=int(os.getenv("LAMP_ID", "1")),
                        help="宫灯ID (默认: 1, 环境变量: LAMP_ID)")
    parser.add_argument("--modbus-host", type=str,
                        default=os.getenv("MODBUS_HOST", "0.0.0.0"),
                        help="Modbus服务地址 (环境变量: MODBUS_HOST)")
    parser.add_argument("--modbus-port", type=int,
                        default=int(os.getenv("MODBUS_PORT", "502")),
                        help="Modbus端口 (环境变量: MODBUS_PORT)")
    parser.add_argument("--api-url", type=str,
                        default=os.getenv("API_URL", "http://localhost:8000"),
                        help="后端API地址 (环境变量: API_URL)")
    parser.add_argument("--report-interval", type=int,
                        default=int(os.getenv("REPORT_INTERVAL", "60")),
                        help="数据上报间隔（秒）(环境变量: REPORT_INTERVAL)")

    # 功能开关
    parser.add_argument("--no-modbus", action="store_true",
                        default=not _str_to_bool(os.getenv("ENABLE_MODBUS", "true")),
                        help="禁用Modbus TCP服务")
    parser.add_argument("--no-http", action="store_true",
                        default=not _str_to_bool(os.getenv("ENABLE_HTTP", "true")),
                        help="禁用HTTP上报")
    parser.add_argument("--no-anomalies", action="store_true",
                        default=not _str_to_bool(os.getenv("INJECT_ANOMALIES", "true")),
                        help="禁用烟道堵塞等随机异常注入")

    # 实验参数（核心可配置项）
    parser.add_argument("--fuel-type", type=str,
                        default=os.getenv("FUEL_TYPE", "animal_fat"),
                        choices=["animal_fat", "sesame_oil", "beeswax", "mineral_oil", "tallow"],
                        help="灯油燃料类型 (环境变量: FUEL_TYPE)")
    parser.add_argument("--air-change-rate", type=float,
                        default=float(os.getenv("AIR_CHANGE_RATE", "1.0")),
                        help="室内通风换气率 ACH（次/小时）, 范围 0-20 (环境变量: AIR_CHANGE_RATE)")
    parser.add_argument("--outdoor-pm25", type=float,
                        default=float(os.getenv("OUTDOOR_PM25", "25.0")),
                        help="室外PM2.5基准浓度 μg/m³ (环境变量: OUTDOOR_PM25)")

    # 初始条件
    parser.add_argument("--flame-intensity", type=float,
                        default=0.8,
                        help="初始火焰强度 0-1 (默认: 0.8)")
    parser.add_argument("--initial-oil-level", type=float,
                        default=500.0,
                        help="初始油量 ml (默认: 500)")

    args = parser.parse_args()

    # 参数合法性校验
    args.air_change_rate = max(0.0, min(20.0, args.air_change_rate))
    args.outdoor_pm25 = max(0.0, min(500.0, args.outdoor_pm25))
    args.flame_intensity = max(0.1, min(1.0, args.flame_intensity))
    args.report_interval = max(1, args.report_interval)

    simulator = GongdengSensorSimulator(
        lamp_id=args.lamp_id,
        modbus_host=args.modbus_host,
        modbus_port=args.modbus_port,
        api_url=args.api_url,
        enable_modbus=not args.no_modbus,
        enable_http=not args.no_http,
        fuel_type=args.fuel_type,
        air_change_rate=args.air_change_rate,
        outdoor_pm25=args.outdoor_pm25
    )

    # 应用初始条件
    simulator.flame_intensity = args.flame_intensity
    simulator.oil_level = args.initial_oil_level
    simulator._inject_anomalies = not args.no_anomalies
    simulator._report_interval = args.report_interval

    # 启动时打印配置摘要
    logger.info("=" * 60)
    logger.info("模拟器配置摘要")
    logger.info("=" * 60)
    logger.info(f"宫灯ID:          {simulator.lamp_id}")
    logger.info(f"Modbus TCP:      {simulator.modbus_host}:{simulator.modbus_port} "
                f"({'启用' if simulator.enable_modbus else '禁用'})")
    logger.info(f"API地址:         {simulator.api_url} "
                f"({'启用' if simulator.enable_http else '禁用'})")
    logger.info(f"上报间隔:        {simulator._report_interval} 秒")
    logger.info(f"燃料类型:        {FUEL_TYPES[simulator.fuel_type]['name']} "
                f"({simulator.fuel_type})")
    logger.info(f"通风换气率:      {simulator.air_change_rate:.1f} ACH")
    logger.info(f"室外PM2.5:       {simulator.outdoor_pm25:.1f} μg/m³")
    logger.info(f"火焰强度:        {simulator.flame_intensity:.2f}")
    logger.info(f"异常注入:        {'启用' if simulator._inject_anomalies else '禁用'}")
    logger.info(f"初始油量:        {simulator.oil_level:.0f} ml")
    logger.info("=" * 60)

    await simulator.run()


if __name__ == "__main__":
    asyncio.run(main())
