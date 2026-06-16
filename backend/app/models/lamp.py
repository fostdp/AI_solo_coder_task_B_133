from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.sql import func
from ..database import Base


class Lamp(Base):
    __tablename__ = "lamps"

    lamp_id = Column(Integer, primary_key=True)
    lamp_name = Column(String(100), nullable=False)
    location = Column(String(200))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SensorData(Base):
    __tablename__ = "sensor_data"

    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    lamp_id = Column(Integer, ForeignKey("lamps.lamp_id"), primary_key=True)
    oil_consumption = Column(Float, nullable=False)
    flue_temperature = Column(Float, nullable=False)
    flue_velocity = Column(Float, nullable=False)
    indoor_pm25 = Column(Float, nullable=False)
    oil_level = Column(Float)
    ambient_temperature = Column(Float)
    ambient_humidity = Column(Float)


class FlueSimulation(Base):
    __tablename__ = "flue_simulation"

    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    lamp_id = Column(Integer, ForeignKey("lamps.lamp_id"), primary_key=True)
    reynolds_number = Column(Float)
    prandtl_number = Column(Float)
    nusselt_number = Column(Float)
    heat_transfer_coeff = Column(Float)
    pressure_drop = Column(Float)
    settling_efficiency = Column(Float)
    outlet_temperature = Column(Float)
    outlet_velocity = Column(Float)
    flow_regime = Column(String(20))


class AirQualityAnalysis(Base):
    __tablename__ = "air_quality_analysis"

    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    lamp_id = Column(Integer, ForeignKey("lamps.lamp_id"), primary_key=True)
    pm25_diffusion_coeff = Column(Float)
    pm25_gradient_x = Column(Float)
    pm25_gradient_y = Column(Float)
    pm25_gradient_z = Column(Float)
    purification_rate = Column(Float)
    air_change_efficiency = Column(Float)
    aqi_level = Column(String(20))
    health_risk = Column(String(50))


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    time = Column(DateTime(timezone=True), server_default=func.now())
    lamp_id = Column(Integer, ForeignKey("lamps.lamp_id"), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    threshold_value = Column(Float)
    actual_value = Column(Float)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True))


class PM25Grid(Base):
    __tablename__ = "pm25_grid"

    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    lamp_id = Column(Integer, ForeignKey("lamps.lamp_id"), primary_key=True)
    grid_x = Column(Integer, primary_key=True)
    grid_y = Column(Integer, primary_key=True)
    grid_z = Column(Integer, primary_key=True)
    concentration = Column(Float, nullable=False)
