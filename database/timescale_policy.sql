-- ============================================
-- 长信宫灯 TimescaleDB 策略配置
-- 降采样（连续聚合） + 数据保留策略
-- ============================================

-- ============================================
-- 1. 传感器数据 - 连续聚合视图
-- ============================================

-- 1分钟聚合（实时）
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_data_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    lamp_id,
    AVG(oil_consumption) AS avg_oil_consumption,
    AVG(flue_temperature) AS avg_flue_temperature,
    MAX(flue_temperature) AS max_flue_temperature,
    MIN(flue_temperature) AS min_flue_temperature,
    AVG(flue_velocity) AS avg_flue_velocity,
    MIN(flue_velocity) AS min_flue_velocity,
    AVG(indoor_pm25) AS avg_pm25,
    MAX(indoor_pm25) AS max_pm25,
    MIN(indoor_pm25) AS min_pm25,
    AVG(oil_level) AS avg_oil_level,
    AVG(ambient_temperature) AS avg_ambient_temperature,
    AVG(ambient_humidity) AS avg_ambient_humidity,
    COUNT(*) AS sample_count
FROM sensor_data
GROUP BY bucket, lamp_id
WITH NO DATA;

-- 1小时聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_data_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    lamp_id,
    AVG(avg_oil_consumption) AS avg_oil_consumption,
    AVG(avg_flue_temperature) AS avg_flue_temperature,
    MAX(max_flue_temperature) AS max_flue_temperature,
    MIN(min_flue_temperature) AS min_flue_temperature,
    AVG(avg_flue_velocity) AS avg_flue_velocity,
    MIN(min_flue_velocity) AS min_flue_velocity,
    AVG(avg_pm25) AS avg_pm25,
    MAX(max_pm25) AS max_pm25,
    MIN(min_pm25) AS min_pm25,
    SUM(sample_count) AS sample_count
FROM sensor_data_1min
GROUP BY bucket, lamp_id
WITH NO DATA;

-- 1天聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS sensor_data_1day
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    lamp_id,
    AVG(avg_oil_consumption) AS avg_oil_consumption,
    AVG(avg_flue_temperature) AS avg_flue_temperature,
    MAX(max_flue_temperature) AS max_flue_temperature,
    MIN(min_flue_temperature) AS min_flue_temperature,
    AVG(avg_flue_velocity) AS avg_flue_velocity,
    MIN(min_flue_velocity) AS min_flue_velocity,
    AVG(avg_pm25) AS avg_pm25,
    MAX(max_pm25) AS max_pm25,
    MIN(min_pm25) AS min_pm25,
    SUM(sample_count) AS sample_count
FROM sensor_data_1hour
GROUP BY bucket, lamp_id
WITH NO DATA;

-- ============================================
-- 2. 烟道仿真数据 - 连续聚合视图
-- ============================================

CREATE MATERIALIZED VIEW IF NOT EXISTS flue_simulation_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    lamp_id,
    AVG(reynolds_number) AS avg_reynolds_number,
    AVG(prandtl_number) AS avg_prandtl_number,
    AVG(nusselt_number) AS avg_nusselt_number,
    AVG(heat_transfer_coeff) AS avg_heat_transfer_coeff,
    AVG(pressure_drop) AS avg_pressure_drop,
    AVG(settling_efficiency) AS avg_settling_efficiency,
    MAX(settling_efficiency) AS max_settling_efficiency,
    AVG(outlet_temperature) AS avg_outlet_temperature,
    AVG(outlet_velocity) AS avg_outlet_velocity
FROM flue_simulation
GROUP BY bucket, lamp_id
WITH NO DATA;

-- ============================================
-- 3. 空气质量分析 - 连续聚合视图
-- ============================================

CREATE MATERIALIZED VIEW IF NOT EXISTS air_quality_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    lamp_id,
    AVG(pm25_diffusion_coeff) AS avg_diffusion_coeff,
    AVG(purification_rate) AS avg_purification_rate,
    AVG(air_change_efficiency) AS avg_air_change_efficiency,
    MAX(aqi_level) AS max_aqi_level
FROM air_quality_analysis
GROUP BY bucket, lamp_id
WITH NO DATA;

-- ============================================
-- 4. 数据保留策略 (Retention Policy)
-- ============================================

-- 原始传感器数据：保留 30 天
SELECT add_retention_policy(
    'sensor_data',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- PM2.5 网格数据：保留 7 天（数据量大）
SELECT add_retention_policy(
    'pm25_grid',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- 1分钟聚合：保留 90 天
SELECT add_retention_policy(
    'sensor_data_1min',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- 1小时聚合：保留 1 年
SELECT add_retention_policy(
    'sensor_data_1hour',
    INTERVAL '1 year',
    if_not_exists => TRUE
);

-- 1天聚合：永久保留（不设置保留策略）

-- 烟道仿真原始数据：保留 30 天
SELECT add_retention_policy(
    'flue_simulation',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- 空气质量分析原始数据：保留 30 天
SELECT add_retention_policy(
    'air_quality_analysis',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- 告警记录：保留 1 年
SELECT add_retention_policy(
    'alerts',
    INTERVAL '1 year',
    if_not_exists => TRUE
);

-- ============================================
-- 5. 连续聚合刷新策略 (Continuous Aggregate Refresh Policy)
-- ============================================

-- 1分钟聚合：每 1 分钟刷新，刷新最近 15 分钟数据
SELECT add_continuous_aggregate_policy(
    'sensor_data_1min',
    start_offset => INTERVAL '15 minutes',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- 1小时聚合：每 15 分钟刷新，刷新最近 3 小时数据
SELECT add_continuous_aggregate_policy(
    'sensor_data_1hour',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

-- 1天聚合：每 1 小时刷新，刷新最近 2 天数据
SELECT add_continuous_aggregate_policy(
    'sensor_data_1day',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- 烟道仿真1小时聚合：每 30 分钟刷新
SELECT add_continuous_aggregate_policy(
    'flue_simulation_1hour',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '30 minutes',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);

-- 空气质量1小时聚合：每 30 分钟刷新
SELECT add_continuous_aggregate_policy(
    'air_quality_1hour',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '30 minutes',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);

-- ============================================
-- 6. 压缩策略 (Compression Policy)
-- ============================================

-- 启用超表压缩（节省存储空间）
ALTER TABLE sensor_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'lamp_id',
    timescaledb.compress_orderby = 'time DESC'
);

ALTER TABLE flue_simulation SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'lamp_id',
    timescaledb.compress_orderby = 'time DESC'
);

ALTER TABLE air_quality_analysis SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'lamp_id',
    timescaledb.compress_orderby = 'time DESC'
);

ALTER TABLE pm25_grid SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'lamp_id',
    timescaledb.compress_orderby = 'time DESC'
);

-- 添加压缩策略：超过 7 天的数据自动压缩
SELECT add_compression_policy(
    'sensor_data',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

SELECT add_compression_policy(
    'flue_simulation',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

SELECT add_compression_policy(
    'air_quality_analysis',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

SELECT add_compression_policy(
    'pm25_grid',
    INTERVAL '3 days',
    if_not_exists => TRUE
);

-- ============================================
-- 7. 重新排序策略 (Reorder Policy)
-- ============================================

-- 按 lamp_id + time 排序，提高查询性能
SELECT add_reorder_policy(
    'sensor_data',
    'idx_sensor_data_lamp_id',
    if_not_exists => TRUE
);

SELECT add_reorder_policy(
    'flue_simulation',
    'idx_flue_sim_lamp_id',
    if_not_exists => TRUE
);

SELECT add_reorder_policy(
    'air_quality_analysis',
    'idx_aq_lamp_id',
    if_not_exists => TRUE
);

-- ============================================
-- 8. 信息视图
-- ============================================

-- 查看所有策略
CREATE OR REPLACE VIEW gongdeng_policies AS
SELECT
    'retention' AS policy_type,
    hypertable_name,
    schedule_interval,
    config ->> 'drop_after' AS retention_period
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_retention'

UNION ALL

SELECT
    'continuous_aggregate' AS policy_type,
    hypertable_name,
    schedule_interval,
    config ->> 'refresh_interval' AS refresh_interval
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_continuous_aggregate'

UNION ALL

SELECT
    'compression' AS policy_type,
    hypertable_name,
    schedule_interval,
    config ->> 'compress_after' AS compress_after
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_compression'

UNION ALL

SELECT
    'reorder' AS policy_type,
    hypertable_name,
    schedule_interval,
    NULL AS extra_info
FROM timescaledb_information.jobs
WHERE proc_name = 'policy_reorder';

-- 授予权限
GRANT SELECT ON gongdeng_policies TO current_user;
