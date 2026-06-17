from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class SensorDataCreate(BaseModel):
    lamp_id: int = Field(..., description="宫灯ID")
    oil_consumption: float = Field(..., ge=0, description="灯油消耗速率 ml/min")
    flue_temperature: float = Field(..., description="烟道温度 °C")
    flue_velocity: float = Field(..., ge=0, description="烟气流速 m/s")
    indoor_pm25: float = Field(..., ge=0, description="室内PM2.5浓度 μg/m³")
    oil_level: Optional[float] = Field(None, description="剩余油量 ml")
    ambient_temperature: Optional[float] = Field(None, description="环境温度 °C")
    ambient_humidity: Optional[float] = Field(None, description="环境湿度 %")
    blockage_degree: Optional[float] = Field(None, description="烟道堵塞程度")
    fuel_type: Optional[str] = Field(None, description="燃料类型: animal_fat, sesame_oil, beeswax, mineral_oil, tallow")
    lamp_type: Optional[str] = Field(None, description="灯具类型: changxin_gongdeng, yanyu_deng, niu_deng")
    air_change_rate: Optional[float] = Field(None, ge=0, description="室内换气率 次/小时")
    outdoor_pm25: Optional[float] = Field(None, ge=0, description="室外PM2.5浓度 μg/m³")
    timestamp: Optional[int] = Field(None, description="Unix时间戳")
    time: Optional[str] = Field(None, description="ISO时间字符串")


class SensorDataResponse(BaseModel):
    time: datetime
    lamp_id: int
    oil_consumption: float
    flue_temperature: float
    flue_velocity: float
    indoor_pm25: float
    oil_level: Optional[float]
    ambient_temperature: Optional[float]
    ambient_humidity: Optional[float]

    class Config:
        from_attributes = True


class FlueSimulationResponse(BaseModel):
    time: datetime
    lamp_id: int
    fuel_type: Optional[str] = None
    fuel_name: Optional[str] = None
    heating_value: Optional[float] = None
    reynolds_number: float
    prandtl_number: float
    nusselt_number: float
    heat_transfer_coeff: float
    pressure_drop: float
    settling_efficiency: float
    outlet_temperature: float
    outlet_velocity: float
    flow_regime: str

    class Config:
        from_attributes = True


class AirQualityResponse(BaseModel):
    time: datetime
    lamp_id: int
    pm25_diffusion_coeff: float
    pm25_gradient_x: float
    pm25_gradient_y: float
    pm25_gradient_z: float
    purification_rate: float
    air_change_efficiency: float
    aqi_level: str
    health_risk: str
    air_change_rate: Optional[float] = None
    outdoor_pm25: Optional[float] = None
    ventilation_decay: Optional[float] = None

    class Config:
        from_attributes = True


class PM25GridPoint(BaseModel):
    grid_x: int
    grid_y: int
    grid_z: int
    concentration: float


class PM25GridResponse(BaseModel):
    time: datetime
    lamp_id: int
    grid_data: List[PM25GridPoint]


class AlertResponse(BaseModel):
    alert_id: int
    time: datetime
    lamp_id: int
    alert_type: str
    severity: str
    message: str
    threshold_value: Optional[float]
    actual_value: Optional[float]
    resolved: bool
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class LampResponse(BaseModel):
    lamp_id: int
    lamp_name: str
    location: Optional[str]
    description: Optional[str]
    created_at: datetime
    lamp_type: Optional[str] = None
    dynasty: Optional[str] = None
    flue_length_m: Optional[float] = None
    flue_diameter_m: Optional[float] = None
    bend_count: Optional[int] = None
    height_m: Optional[float] = None
    weight_kg: Optional[float] = None
    material: Optional[str] = None
    base_purification_efficiency: Optional[float] = None

    class Config:
        from_attributes = True


class CombinedDataResponse(BaseModel):
    sensor: SensorDataResponse
    flue_simulation: Optional[FlueSimulationResponse]
    air_quality: Optional[AirQualityResponse]
    alerts: List[AlertResponse]


class StatisticsResponse(BaseModel):
    lamp_id: int
    start_time: datetime
    end_time: datetime
    avg_oil_consumption: float
    avg_flue_temperature: float
    avg_flue_velocity: float
    avg_pm25: float
    max_pm25: float
    min_pm25: float
    data_points: int
