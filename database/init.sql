-- ============================================
-- 长信宫灯烟道流体仿真与室内空气质量分析系统
-- TimescaleDB 初始化脚本
-- ============================================

-- 创建数据库
-- CREATE DATABASE changxin_gongdeng;
-- \c changxin_gongdeng;

-- 启用 TimescaleDB 扩展
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================
-- 宫灯信息表
-- ============================================
CREATE TABLE IF NOT EXISTS lamps (
    lamp_id SERIAL PRIMARY KEY,
    lamp_name VARCHAR(100) NOT NULL,
    location VARCHAR(200),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 插入默认宫灯数据
INSERT INTO lamps (lamp_id, lamp_name, location, description) VALUES
(1, '长信宫灯-1号', '展厅A区-汉代展区', '复原的汉代长信宫灯，配备烟道模拟系统')
ON CONFLICT (lamp_id) DO NOTHING;

-- ============================================
-- 传感器数据表（超表 - 时序数据）
-- ============================================
CREATE TABLE IF NOT EXISTS sensor_data (
    time TIMESTAMPTZ NOT NULL,
    lamp_id INTEGER NOT NULL REFERENCES lamps(lamp_id),
    oil_consumption DOUBLE PRECISION NOT NULL,  -- 灯油消耗速率 (ml/min)
    flue_temperature DOUBLE PRECISION NOT NULL,  -- 烟道温度 (°C)
    flue_velocity DOUBLE PRECISION NOT NULL,     -- 烟气流速 (m/s)
    indoor_pm25 DOUBLE PRECISION NOT NULL,       -- 室内PM2.5浓度 (μg/m³)
    oil_level DOUBLE PRECISION,                  -- 剩余油量 (ml)
    ambient_temperature DOUBLE PRECISION,        -- 环境温度 (°C)
    ambient_humidity DOUBLE PRECISION            -- 环境湿度 (%)
);

-- 创建超表（按时间分区）
SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_sensor_data_lamp_id ON sensor_data(lamp_id, time DESC);

-- ============================================
-- 烟道流体仿真结果表（超表）
-- ============================================
CREATE TABLE IF NOT EXISTS flue_simulation (
    time TIMESTAMPTZ NOT NULL,
    lamp_id INTEGER NOT NULL REFERENCES lamps(lamp_id),
    reynolds_number DOUBLE PRECISION,            -- 雷诺数
    prandtl_number DOUBLE PRECISION,             -- 普朗特数
    nusselt_number DOUBLE PRECISION,             -- 努塞尔数
    heat_transfer_coeff DOUBLE PRECISION,        -- 对流换热系数 (W/m²·K)
    pressure_drop DOUBLE PRECISION,              -- 烟道压降 (Pa)
    settling_efficiency DOUBLE PRECISION,        -- 烟尘沉降效率 (%)
    outlet_temperature DOUBLE PRECISION,         -- 烟道出口温度 (°C)
    outlet_velocity DOUBLE PRECISION,            -- 烟道出口流速 (m/s)
    flow_regime VARCHAR(20)                      -- 流型 (laminar/transitional/turbulent)
);

SELECT create_hypertable('flue_simulation', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_flue_sim_lamp_id ON flue_simulation(lamp_id, time DESC);

-- ============================================
-- 空气质量分析结果表（超表）
-- ============================================
CREATE TABLE IF NOT EXISTS air_quality_analysis (
    time TIMESTAMPTZ NOT NULL,
    lamp_id INTEGER NOT NULL REFERENCES lamps(lamp_id),
    pm25_diffusion_coeff DOUBLE PRECISION,       -- PM2.5扩散系数 (m²/s)
    pm25_gradient_x DOUBLE PRECISION,            -- X方向浓度梯度
    pm25_gradient_y DOUBLE PRECISION,            -- Y方向浓度梯度
    pm25_gradient_z DOUBLE PRECISION,            -- Z方向浓度梯度
    purification_rate DOUBLE PRECISION,          -- 净化速率 (μg/m³·min)
    air_change_efficiency DOUBLE PRECISION,      -- 空气交换效率 (%)
    aqi_level VARCHAR(20),                        -- 空气质量等级
    health_risk VARCHAR(50)                       -- 健康风险评估
);

SELECT create_hypertable('air_quality_analysis', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_aq_lamp_id ON air_quality_analysis(lamp_id, time DESC);

-- ============================================
-- 告警事件表
-- ============================================
CREATE TABLE IF NOT EXISTS alerts (
    alert_id SERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    lamp_id INTEGER NOT NULL REFERENCES lamps(lamp_id),
    alert_type VARCHAR(50) NOT NULL,             -- FLUE_BLOCKAGE / PM25_EXCEEDED / TEMPERATURE_HIGH
    severity VARCHAR(20) NOT NULL,               -- WARNING / CRITICAL
    message TEXT NOT NULL,
    threshold_value DOUBLE PRECISION,
    actual_value DOUBLE PRECISION,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_lamp_id ON alerts(lamp_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved);

-- ============================================
-- 室内PM2.5分布网格数据（超表）
-- ============================================
CREATE TABLE IF NOT EXISTS pm25_grid (
    time TIMESTAMPTZ NOT NULL,
    lamp_id INTEGER NOT NULL REFERENCES lamps(lamp_id),
    grid_x INTEGER NOT NULL,
    grid_y INTEGER NOT NULL,
    grid_z INTEGER NOT NULL,
    concentration DOUBLE PRECISION NOT NULL      -- PM2.5浓度 (μg/m³)
);

SELECT create_hypertable('pm25_grid', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_pm25_grid_lamp_time ON pm25_grid(lamp_id, time DESC);

-- ============================================
-- 连续聚合视图 - 每分钟汇总
-- ============================================
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_data_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    lamp_id,
    AVG(oil_consumption) AS avg_oil_consumption,
    AVG(flue_temperature) AS avg_flue_temperature,
    AVG(flue_velocity) AS avg_flue_velocity,
    AVG(indoor_pm25) AS avg_pm25,
    MAX(indoor_pm25) AS max_pm25,
    MIN(indoor_pm25) AS min_pm25
FROM sensor_data
GROUP BY bucket, lamp_id
WITH NO DATA;

-- ============================================
-- 授予权限
-- ============================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO current_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO current_user;
