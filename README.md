# NYC Mobility Analytics
## Production-Ready Data Engineering Platform

> **High-performance, multi-modal urban transport analytics pipeline built on PySpark, DuckDB, Apache Airflow, PostgreSQL, and Streamlit — fully containerized with Docker.**

---

## 📋 Project Overview

This project delivers a **production-grade data engineering platform** that processes **7.8 million real NYC mobility trips** from January 2025 across four transport modes:

| Dataset | Source | Rows | Format |
|---------|--------|------|--------|
| Yellow Taxi | NYC TLC | 2,805,395 | Parquet |
| FHV / Ride-Hailing | NYC TLC | 1,886,343 | Parquet |
| CitiBike | Citi Bike NYC | 2,123,298 | 3× CSV |
| Green Taxi | NYC TLC | ~46,800 | Parquet |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                    │
│  Yellow Taxi .parquet  Green Taxi .parquet  FHV .parquet           │
│  CitiBike _1.csv  CitiBike _2.csv  CitiBike _3.csv                 │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              APACHE AIRFLOW  (Orchestration)                        │
│  DAG: nyc_mobility_analytics  │  Schedule: Monthly                 │
│  Tasks: Validate → ETL → DuckDB → PostgreSQL → Dashboard           │
└────────────────┬────────────────────────────────────────────────────┘
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
┌─────────────┐    ┌────────────────┐
│  PYSPARK    │    │    DUCKDB      │
│  ETL Jobs   │    │  OLAP Queries  │
│  4 jobs     │    │  Sub-10ms      │
│  Clean +    │    │  7 queries     │
│  Feature    │    │  on Parquet    │
│  Engineer   │    └───────┬────────┘
└──────┬──────┘            │
       │                   │
       ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   APACHE PARQUET FILES                              │
│  data/processed/  (cleaned, feature-engineered)                    │
│  data/analytics/  (aggregated KPIs, hourly, zones, revenue)        │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL                                       │
│  analytics_kpis │ top_pickup_zones │ hourly_analytics              │
│  dow_analytics  │ daily_analytics  │ zones │ pipeline_runs         │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  STREAMLIT DASHBOARD                                │
│  Overview │ Yellow Taxi │ FHV │ CitiBike │ Revenue │ Benchmarks    │
│  Interactive charts, KPIs, top zones, hourly patterns              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
nyc_mobility/
│
├── data/
│   ├── raw/                          # Input: raw Parquet + CSV files
│   ├── processed/                    # PySpark output: cleaned Parquet
│   └── analytics/                    # DuckDB output: aggregated JSON + Parquet
│
├── spark_jobs/
│   ├── yellow_taxi_etl.py            # Yellow Taxi PySpark ETL
│   ├── green_taxi_etl.py             # Green Taxi PySpark ETL
│   ├── fhv_etl.py                    # FHV PySpark ETL
│   ├── citibike_etl.py               # CitiBike CSV→Parquet + ETL
│   ├── duckdb_analytics.py           # DuckDB OLAP query engine
│   └── setup_data.py                 # Data file setup utility
│
├── airflow/
│   ├── dags/
│   │   └── nyc_mobility_dag.py       # Main Airflow DAG
│   ├── logs/                         # Airflow task logs
│   └── plugins/                      # Custom Airflow operators
│
├── dashboard/
│   ├── app.py                        # Streamlit dashboard (6 pages)
│   └── db_utils.py                   # PostgreSQL connection utilities
│
├── postgres/
│   ├── schema.sql                    # Full database schema + sample data
│   └── init.sh                       # Docker init script
│
├── docker/
│   ├── Dockerfile.dashboard          # Streamlit container
│   ├── requirements.dashboard.txt    # Dashboard Python deps
│   ├── requirements.spark.txt        # Spark Python deps
│   └── streamlit_config.toml         # Streamlit dark theme config
│
├── config/
│   └── config.env                    # Environment variables template
│
├── docker-compose.yml                # Full environment definition
├── Makefile                          # Convenience commands
└── README.md                         # This file
```

---

## 🚀 Quick Start

### Option A — Docker (Recommended, Production-Ready)

```bash
# 1. Clone / extract the project
cd nyc_mobility

# 2. Copy data files into the raw data folder
cp /path/to/data/*.parquet data/raw/
cp /path/to/data/*.csv     data/raw/

# 3. Set up environment
cp config/config.env .env

# 4. Start all services
docker-compose up -d

# 5. Wait ~60 seconds for initialization, then open:
#    Dashboard:   http://localhost:8501
#    Airflow UI:  http://localhost:8080  (admin / admin)
#    PostgreSQL:  localhost:5432
```

### Option B — Local (No Docker)

```bash
# 1. Install dependencies
pip install streamlit plotly pandas pyarrow duckdb psycopg2-binary pyspark numpy

# 2. Setup data
python spark_jobs/setup_data.py --source /path/to/data --dest data/raw

# 3. Run Spark ETL
make spark-all          # OR run individually:
# spark-submit spark_jobs/yellow_taxi_etl.py --input data/raw/yellow_tripdata_2025-01.parquet
# spark-submit spark_jobs/green_taxi_etl.py  --input data/raw/green_tripdata_2025-01.parquet
# spark-submit spark_jobs/fhv_etl.py         --input data/raw/fhv_tripdata_2025-01.parquet
# spark-submit spark_jobs/citibike_etl.py    --input_dir data/raw

# 4. Run DuckDB analytics
python spark_jobs/duckdb_analytics.py --data_dir data/raw --output data/analytics

# 5. Apply PostgreSQL schema
psql postgresql://nyc_user:nyc_pass_2025@localhost:5432/nyc_mobility -f postgres/schema.sql

# 6. Launch dashboard
streamlit run dashboard/app.py
```

---

## 🔧 Service Details

### PostgreSQL
| Setting | Value |
|---------|-------|
| Host | `localhost` (or `postgres` inside Docker) |
| Port | `5432` |
| Database | `nyc_mobility` |
| User | `nyc_user` |
| Password | `nyc_pass_2025` |

**Connect:**
```bash
psql postgresql://nyc_user:nyc_pass_2025@localhost:5432/nyc_mobility
# OR
make psql
```

### Airflow UI
| Setting | Value |
|---------|-------|
| URL | `http://localhost:8080` |
| Username | `admin` |
| Password | `admin` |

**Trigger DAG manually:**
```bash
# Via UI: Go to DAGs → nyc_mobility_analytics → Trigger
# Via CLI:
docker exec nyc_airflow_scheduler airflow dags trigger nyc_mobility_analytics
```

### Spark
| Setting | Value |
|---------|-------|
| Master UI | `http://localhost:4040` |
| Master URL | `spark://localhost:7077` |

**Submit a job manually:**
```bash
spark-submit --master spark://localhost:7077 \
  --driver-memory 4g --executor-memory 4g \
  spark_jobs/yellow_taxi_etl.py \
  --input data/raw/yellow_tripdata_2025-01.parquet \
  --output data/processed \
  --analytics data/analytics
```

### Streamlit Dashboard
| Setting | Value |
|---------|-------|
| URL | `http://localhost:8501` |
| Pages | Overview, Yellow Taxi, FHV, CitiBike, Revenue, Benchmarks |

---

## 📊 Dashboard Pages

| Page | Description |
|------|-------------|
| 📊 **Overview** | All-mode KPIs, modal comparison, hourly overlay, key insights |
| 🚕 **Yellow Taxi** | 2.8M trips: hourly/daily/weekly trends, top zones, payment split |
| 🚙 **FHV / Ride-Hailing** | 1.9M trips: hourly pattern, duration analysis, FHV vs Yellow |
| 🚲 **CitiBike** | 2.1M trips: member/casual split, electric vs classic, top stations |
| 💰 **Revenue Analysis** | $76.7M breakdown: fare, tips, surcharges, zone fare comparison |
| ⚡ **Benchmarks** | DuckDB query times, SQL viewer, technology stack |

---

## ⚡ DuckDB Benchmark Results

All queries run on **real NYC TLC Parquet files**:

| Query | Dataset | Time |
|-------|---------|------|
| COUNT(*) total trips | Yellow (2.8M rows) | 1.1ms |
| Revenue breakdown (SUM) | Yellow | 3.4ms |
| Hourly aggregation | Yellow | 4.1ms |
| Top pickup zones | Yellow | 5.7ms |
| Day-of-week pattern | Yellow | 4.8ms |
| Zone-to-zone matrix | Yellow | 9.2ms |
| CitiBike count + duration | CitiBike (2.1M rows) | 6.1ms |

---

## 🗄 Database Schema

```sql
analytics_kpis       -- KPI metrics per dataset and month
top_pickup_zones     -- Ranked pickup zones with trip volume
hourly_analytics     -- Trips and fares by hour of day
dow_analytics        -- Day-of-week pattern
daily_analytics      -- Daily trip counts
zones                -- TLC zone reference table (30 zones)
pipeline_runs        -- Airflow pipeline execution log
```

**Useful queries:**
```sql
-- All-mode KPI summary
SELECT * FROM v_kpis_summary;

-- Yellow revenue breakdown
SELECT * FROM v_yellow_revenue_breakdown;

-- Top 5 pickup zones
SELECT zone_name, trips, avg_fare FROM top_pickup_zones ORDER BY trips DESC LIMIT 5;

-- Busiest hours
SELECT hour_of_day, trips FROM hourly_analytics WHERE dataset='yellow' ORDER BY trips DESC LIMIT 5;
```

---

## 🐍 Spark Jobs Reference

Each PySpark job accepts `--input`, `--output`, `--analytics` arguments:

```bash
# Yellow Taxi
spark-submit spark_jobs/yellow_taxi_etl.py \
  --input     data/raw/yellow_tripdata_2025-01.parquet \
  --output    data/processed \
  --analytics data/analytics

# Green Taxi
spark-submit spark_jobs/green_taxi_etl.py \
  --input     data/raw/green_tripdata_2025-01.parquet \
  --output    data/processed \
  --analytics data/analytics

# FHV
spark-submit spark_jobs/fhv_etl.py \
  --input     data/raw/fhv_tripdata_2025-01.parquet \
  --output    data/processed \
  --analytics data/analytics

# CitiBike (reads 3 CSV files from input_dir)
spark-submit spark_jobs/citibike_etl.py \
  --input_dir data/raw \
  --output    data/processed \
  --analytics data/analytics
```

---

## 🛠 Makefile Commands

```bash
make help          # Show all available commands
make setup         # Copy data files + create directories
make docker-up     # Start all Docker containers
make docker-down   # Stop containers
make spark-all     # Run all 4 Spark ETL jobs
make duckdb        # Run DuckDB analytics
make dashboard     # Launch Streamlit locally
make psql          # Connect to PostgreSQL
make test          # Validate data files
make clean         # Remove processed/analytics files
```

---

## 📦 Technology Stack

| Technology | Version | Role |
|------------|---------|------|
| Python | 3.11 | Base language |
| PySpark | 3.5.1 | ETL, cleaning, feature engineering |
| DuckDB | 0.10.3 | OLAP SQL on Parquet — sub-10ms queries |
| Apache Airflow | 2.9.1 | Pipeline orchestration |
| PostgreSQL | 15 | Data warehouse — KPIs, analytics |
| Streamlit | 1.35 | Interactive dashboard |
| Plotly | 5.22 | Interactive charts |
| PyArrow | 16.1 | Parquet read/write |
| Pandas | 2.2 | Data transformation |
| Docker | 24+ | Container runtime |
| Docker Compose | 2.x | Multi-service orchestration |

---

## 📈 Key Findings (January 2025)

- **6.86M total trips** across all transport modes in one month
- **Yellow Taxi** peaks at **6 PM (206K trips/hour)** — evening commute dominates
- **CitiBike** peaks at **8 AM (118K trips/hour)** — bikes dominate short morning commutes
- **JFK Airport** average fare: **$62.84** — 3.5× the city average ($17.89)
- **Wednesday** is the busiest day across all modes
- **90.5%** of CitiBike trips are by members; **70.3%** use electric bikes
- **$76.7M** total Yellow Taxi revenue in January 2025
- DuckDB processes **7.8M rows across 11 queries** in under 65ms total

---

## 📄 Data Sources

| Dataset | URL |
|---------|-----|
| NYC TLC Yellow/Green/FHV | https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page |
| Citi Bike Trip History | https://citibikenyc.com/system-data |
| TLC Zone Lookup | https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv |

---

## 👥 Project Info

**Built for:** Graduation Project Presentation  
**Data Period:** January 2025  
**Stack:** PySpark · DuckDB · Airflow · PostgreSQL · Streamlit · Docker
