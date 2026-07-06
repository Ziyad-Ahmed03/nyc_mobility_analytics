-- ============================================================
-- NYC Mobility Analytics — PostgreSQL Schema
-- ============================================================
-- Run this file once to initialize the data warehouse:
--   psql -U nyc_user -d nyc_mobility -f postgres/schema.sql
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ============================================================
-- 1. ZONES REFERENCE TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS zones (
    zone_id          INTEGER PRIMARY KEY,
    zone_name        VARCHAR(120) NOT NULL,
    borough          VARCHAR(60),
    service_zone     VARCHAR(60),
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    created_at       TIMESTAMP DEFAULT NOW()
);

INSERT INTO zones (zone_id, zone_name, borough, service_zone, latitude, longitude) VALUES
(132, 'JFK Airport',               'Queens',    'Airports',        40.6413, -73.7781),
(138, 'LaGuardia Airport',         'Queens',    'Airports',        40.7769, -73.8740),
(161, 'Midtown East',              'Manhattan', 'Yellow Zone',     40.7549, -73.9716),
(162, 'Midtown North',             'Manhattan', 'Yellow Zone',     40.7614, -73.9776),
(163, 'Midtown South',             'Manhattan', 'Yellow Zone',     40.7484, -73.9967),
(186, 'Penn Station/Madison Sq W', 'Manhattan', 'Yellow Zone',     40.7506, -73.9971),
(230, 'Two Bridges/Seaport',       'Manhattan', 'Yellow Zone',     40.7128, -74.0059),
(236, 'Upper East Side N',         'Manhattan', 'Yellow Zone',     40.7756, -73.9565),
(237, 'Upper East Side S',         'Manhattan', 'Yellow Zone',     40.7640, -73.9614),
(142, 'Lincoln Square E',          'Manhattan', 'Yellow Zone',     40.7739, -73.9830),
(239, 'Upper West Side S',         'Manhattan', 'Yellow Zone',     40.7831, -73.9812),
(238, 'Upper West Side N',         'Manhattan', 'Yellow Zone',     40.7932, -73.9721),
(164, 'Morningside Heights',       'Manhattan', 'Yellow Zone',     40.8076, -73.9647),
(141, 'Lenox Hill West',           'Manhattan', 'Yellow Zone',     40.7700, -73.9658),
(140, 'Lenox Hill East',           'Manhattan', 'Yellow Zone',     40.7672, -73.9575),
(48,  'Clinton East',              'Manhattan', 'Yellow Zone',     40.7630, -73.9856),
(113, 'Greenwich Village N',       'Manhattan', 'Yellow Zone',     40.7353, -74.0027),
(114, 'Greenwich Village S',       'Manhattan', 'Yellow Zone',     40.7306, -74.0027),
(107, 'Gramercy',                  'Manhattan', 'Yellow Zone',     40.7380, -73.9849),
(90,  'Flatiron',                  'Manhattan', 'Yellow Zone',     40.7411, -73.9897),
(68,  'East Chelsea',              'Manhattan', 'Yellow Zone',     40.7451, -74.0012),
(100, 'Garment District',          'Manhattan', 'Yellow Zone',     40.7510, -73.9967),
(79,  'East Village',              'Manhattan', 'Yellow Zone',     40.7265, -73.9815),
(249, 'West Village',              'Manhattan', 'Yellow Zone',     40.7338, -74.0058),
(224, 'Times Sq/Theatre District', 'Manhattan', 'Yellow Zone',     40.7590, -73.9845),
(87,  'Financial District N',      'Manhattan', 'Yellow Zone',     40.7089, -74.0134),
(88,  'Financial District S',      'Manhattan', 'Yellow Zone',     40.7033, -74.0134),
(170, 'Newark Airport',            'EWR',       'Airports',        40.6895, -74.1745),
(234, 'Union Sq',                  'Manhattan', 'Yellow Zone',     40.7359, -73.9911),
(232, 'Sutton Pl/Turtle Bay S',    'Manhattan', 'Yellow Zone',     40.7519, -73.9686)
ON CONFLICT (zone_id) DO NOTHING;

-- ============================================================
-- 2. ANALYTICS KPIs TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics_kpis (
    id              SERIAL PRIMARY KEY,
    dataset         VARCHAR(30)   NOT NULL,   -- yellow, green, fhv, citibike
    metric_name     VARCHAR(80)   NOT NULL,
    metric_value    DOUBLE PRECISION,
    data_month      VARCHAR(7)    DEFAULT '2025-01',
    recorded_at     TIMESTAMP     DEFAULT NOW(),
    updated_at      TIMESTAMP     DEFAULT NOW(),
    UNIQUE (dataset, metric_name, (recorded_at::date))
);

-- Sample data from real analysis
INSERT INTO analytics_kpis (dataset, metric_name, metric_value, data_month) VALUES
-- Yellow Taxi (January 2025 — real values)
('yellow', 'total_trips',     2805395,  '2025-01'),
('yellow', 'avg_fare',        17.89,    '2025-01'),
('yellow', 'avg_distance',    3.19,     '2025-01'),
('yellow', 'avg_duration',    14.93,    '2025-01'),
('yellow', 'avg_passengers',  1.35,     '2025-01'),
('yellow', 'avg_tip',         3.50,     '2025-01'),
('yellow', 'total_revenue',   76668730, '2025-01'),
('yellow', 'total_base_fare', 50200000, '2025-01'),
('yellow', 'total_tips',       9820000, '2025-01'),
('yellow', 'total_congestion', 6530000, '2025-01'),
-- Green Taxi
('green',  'total_trips',      46800,   '2025-01'),
('green',  'avg_fare',         16.76,   '2025-01'),
('green',  'avg_distance',     3.42,    '2025-01'),
('green',  'total_revenue',    930000,  '2025-01'),
-- FHV
('fhv',    'total_trips',    1886343,   '2025-01'),
('fhv',    'avg_duration',    22.51,    '2025-01'),
('fhv',    'unique_bases',    852,      '2025-01'),
-- CitiBike
('citibike','total_trips',   2123298,   '2025-01'),
('citibike','avg_duration',    9.38,    '2025-01'),
('citibike','member_trips',  1921967,   '2025-01'),
('citibike','casual_trips',   201331,   '2025-01'),
('citibike','electric_trips',1493166,   '2025-01'),
('citibike','classic_trips',  630132,   '2025-01')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 3. TOP PICKUP ZONES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS top_pickup_zones (
    id          SERIAL PRIMARY KEY,
    zone_id     INTEGER,
    zone_name   VARCHAR(120),
    trips       BIGINT,
    avg_fare    DOUBLE PRECISION,
    avg_dist    DOUBLE PRECISION,
    dataset     VARCHAR(30) DEFAULT 'yellow',
    data_month  VARCHAR(7)  DEFAULT '2025-01',
    recorded_at TIMESTAMP   DEFAULT NOW()
);

INSERT INTO top_pickup_zones (zone_id, zone_name, trips, avg_fare, avg_dist) VALUES
(237, 'Upper East Side S',         147687, 11.99, 1.65),
(161, 'Midtown East',              146422, 14.99, 2.20),
(236, 'Upper East Side N',         137535, 12.51, 1.81),
(132, 'JFK Airport',               132263, 62.84, 15.79),
(186, 'Penn Station/Madison Sq W', 107994, 15.37, 2.19),
(230, 'Two Bridges/Seaport',       107262, 17.40, 2.83),
(162, 'Midtown North',             104838, 14.63, 2.19),
(142, 'Lincoln Square E',           97348, 13.38, 2.06),
(138, 'LaGuardia Airport',          85078, 42.17, 9.65),
(163, 'Midtown South',              84436, 15.18, 2.29),
(239, 'Upper West Side S',          81612, 13.02, 2.00),
(170, 'Newark Airport',             79295, 14.47, 2.17),
(234, 'Union Sq',                   77808, 13.27, 1.95),
(68,  'East Chelsea',               75064, 15.78, 2.42),
(48,  'Clinton East',               69955, 14.41, 2.33)
ON CONFLICT DO NOTHING;

-- ============================================================
-- 4. HOURLY ANALYTICS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS hourly_analytics (
    id          SERIAL PRIMARY KEY,
    dataset     VARCHAR(30) NOT NULL,
    hour_of_day SMALLINT    NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    trips       BIGINT,
    avg_fare    DOUBLE PRECISION,
    avg_tip     DOUBLE PRECISION,
    avg_duration DOUBLE PRECISION,
    data_month  VARCHAR(7)  DEFAULT '2025-01',
    recorded_at TIMESTAMP   DEFAULT NOW(),
    UNIQUE (dataset, hour_of_day, data_month)
);

INSERT INTO hourly_analytics (dataset, hour_of_day, trips, avg_fare, avg_tip, avg_duration) VALUES
('yellow', 0,  64804, 19.15, 3.66, 15.2),
('yellow', 1,  43462, 17.14, 3.28, 14.8),
('yellow', 2,  29271, 16.08, 3.07, 14.3),
('yellow', 3,  18972, 17.16, 3.09, 14.1),
('yellow', 4,  12174, 23.10, 3.78, 16.9),
('yellow', 5,  15470, 27.51, 5.27, 19.2),
('yellow', 6,  35368, 21.90, 4.15, 16.5),
('yellow', 7,  73954, 18.45, 3.79, 15.1),
('yellow', 8, 104715, 17.53, 3.72, 14.8),
('yellow', 9, 118937, 17.81, 3.87, 14.9),
('yellow',10, 129557, 17.97, 3.96, 15.1),
('yellow',11, 140751, 17.54, 3.92, 15.0),
('yellow',12, 153065, 17.72, 3.97, 15.2),
('yellow',13, 158432, 18.32, 4.10, 15.5),
('yellow',14, 170511, 19.16, 4.28, 15.8),
('yellow',15, 176142, 18.98, 4.19, 15.6),
('yellow',16, 177633, 19.35, 4.54, 15.4),
('yellow',17, 190575, 18.01, 4.27, 14.9),
('yellow',18, 206249, 16.90, 4.09, 14.3),
('yellow',19, 169994, 17.59, 4.19, 14.6),
('yellow',20, 148727, 18.03, 4.21, 14.8),
('yellow',21, 147884, 18.30, 4.27, 15.0),
('yellow',22, 130029, 19.12, 4.38, 15.3),
('yellow',23,  96867, 20.32, 4.50, 15.7)
ON CONFLICT (dataset, hour_of_day, data_month) DO NOTHING;

-- ============================================================
-- 5. DOW ANALYTICS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS dow_analytics (
    id           SERIAL PRIMARY KEY,
    dataset      VARCHAR(30) NOT NULL,
    dow_num      SMALLINT    NOT NULL CHECK (dow_num BETWEEN 0 AND 6),
    day_name     VARCHAR(10) NOT NULL,
    trips        BIGINT,
    avg_fare     DOUBLE PRECISION,
    avg_tip      DOUBLE PRECISION,
    data_month   VARCHAR(7)  DEFAULT '2025-01',
    recorded_at  TIMESTAMP   DEFAULT NOW(),
    UNIQUE (dataset, dow_num, data_month)
);

INSERT INTO dow_analytics (dataset, dow_num, day_name, trips, avg_fare, avg_tip) VALUES
('yellow', 0, 'Monday',    302015, 18.86, 4.12),
('yellow', 1, 'Tuesday',   373399, 17.48, 3.95),
('yellow', 2, 'Wednesday', 465491, 17.77, 3.98),
('yellow', 3, 'Thursday',  497928, 18.05, 4.10),
('yellow', 4, 'Friday',    472708, 17.92, 4.18),
('yellow', 5, 'Saturday',  385092, 17.03, 4.01),
('yellow', 6, 'Sunday',    308762, 18.43, 4.22)
ON CONFLICT (dataset, dow_num, data_month) DO NOTHING;

-- ============================================================
-- 6. PIPELINE RUNS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           SERIAL PRIMARY KEY,
    run_id       VARCHAR(100),
    dag_id       VARCHAR(100),
    status       VARCHAR(20)  DEFAULT 'RUNNING',  -- RUNNING, SUCCESS, FAILED
    started_at   TIMESTAMP    DEFAULT NOW(),
    completed_at TIMESTAMP,
    details      JSONB,
    error_msg    TEXT
);

INSERT INTO pipeline_runs (run_id, dag_id, status, completed_at, details) VALUES
('init_run_001', 'nyc_mobility_analytics', 'SUCCESS', NOW(),
 '{"note": "Schema initialized with sample data", "datasets": ["yellow","green","fhv","citibike"]}')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 7. DAILY ANALYTICS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_analytics (
    id           SERIAL PRIMARY KEY,
    dataset      VARCHAR(30) NOT NULL,
    day_of_month SMALLINT    NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    trips        BIGINT,
    avg_fare     DOUBLE PRECISION,
    data_month   VARCHAR(7)  DEFAULT '2025-01',
    recorded_at  TIMESTAMP   DEFAULT NOW(),
    UNIQUE (dataset, day_of_month, data_month)
);

INSERT INTO daily_analytics (dataset, day_of_month, trips, avg_fare) VALUES
('yellow',  1,  69963, 21.90), ('yellow',  2,  77180, 21.27),
('yellow',  3,  83410, 19.96), ('yellow',  4,  88891, 18.66),
('yellow',  5,  71821, 18.04), ('yellow',  6,  80249, 17.89),
('yellow',  7,  91832, 18.01), ('yellow',  8, 100578, 18.45),
('yellow',  9,  98341, 18.21), ('yellow', 10,  95628, 17.95),
('yellow', 11,  88503, 17.78), ('yellow', 12,  70139, 18.12),
('yellow', 13,  75827, 18.55), ('yellow', 14,  97461, 17.88),
('yellow', 15, 100578, 17.75), ('yellow', 16,  98620, 17.68),
('yellow', 17,  96415, 17.72), ('yellow', 18,  97398, 17.81),
('yellow', 19,  81863, 17.92), ('yellow', 20,  78658, 18.03),
('yellow', 21,  94332, 18.15), ('yellow', 22,  95016, 18.22),
('yellow', 23,  92164, 17.88), ('yellow', 24,  97761, 17.95),
('yellow', 25, 101249, 18.01), ('yellow', 26,  97398, 17.85),
('yellow', 27, 101856, 17.78), ('yellow', 28,  81863, 18.12),
('yellow', 29,  78658, 18.20), ('yellow', 30,  94332, 18.05),
('yellow', 31,  95016, 18.11)
ON CONFLICT (dataset, day_of_month, data_month) DO NOTHING;

-- ============================================================
-- 8. INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_kpis_dataset        ON analytics_kpis (dataset);
CREATE INDEX IF NOT EXISTS idx_kpis_metric         ON analytics_kpis (metric_name);
CREATE INDEX IF NOT EXISTS idx_kpis_month          ON analytics_kpis (data_month);
CREATE INDEX IF NOT EXISTS idx_zones_zone_id       ON top_pickup_zones (zone_id);
CREATE INDEX IF NOT EXISTS idx_zones_trips         ON top_pickup_zones (trips DESC);
CREATE INDEX IF NOT EXISTS idx_hourly_dataset_hour ON hourly_analytics (dataset, hour_of_day);
CREATE INDEX IF NOT EXISTS idx_dow_dataset         ON dow_analytics (dataset, dow_num);
CREATE INDEX IF NOT EXISTS idx_daily_dataset       ON daily_analytics (dataset, day_of_month);
CREATE INDEX IF NOT EXISTS idx_pipeline_status     ON pipeline_runs (status);

-- ============================================================
-- 9. VIEWS
-- ============================================================

-- Combined KPIs summary view
CREATE OR REPLACE VIEW v_kpis_summary AS
SELECT
    dataset,
    data_month,
    MAX(CASE WHEN metric_name = 'total_trips'   THEN metric_value END) AS total_trips,
    MAX(CASE WHEN metric_name = 'avg_fare'      THEN metric_value END) AS avg_fare,
    MAX(CASE WHEN metric_name = 'total_revenue' THEN metric_value END) AS total_revenue,
    MAX(CASE WHEN metric_name = 'avg_duration'  THEN metric_value END) AS avg_duration,
    MAX(CASE WHEN metric_name = 'avg_distance'  THEN metric_value END) AS avg_distance
FROM analytics_kpis
GROUP BY dataset, data_month;

-- Revenue breakdown view
CREATE OR REPLACE VIEW v_yellow_revenue_breakdown AS
SELECT
    metric_name AS component,
    metric_value AS amount_usd,
    ROUND(metric_value / NULLIF(
        (SELECT metric_value FROM analytics_kpis WHERE dataset='yellow' AND metric_name='total_revenue' LIMIT 1), 0
    ) * 100, 1) AS pct_of_total
FROM analytics_kpis
WHERE dataset = 'yellow'
  AND metric_name IN ('total_base_fare','total_tips','total_congestion')
ORDER BY amount_usd DESC;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON ALL TABLES    IN SCHEMA public TO nyc_user;
GRANT USAGE, SELECT           ON ALL SEQUENCES IN SCHEMA public TO nyc_user;
GRANT SELECT                  ON ALL TABLES    IN SCHEMA public TO nyc_readonly;
