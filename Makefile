# ============================================================
# NYC Mobility Analytics — Makefile
# ============================================================
# Usage:
#   make setup      → copy data + create folders
#   make docker-up  → start all containers
#   make spark-all  → run all Spark ETL jobs
#   make duckdb     → run DuckDB analytics
#   make dashboard  → launch Streamlit locally
#   make psql       → connect to PostgreSQL
# ============================================================

.PHONY: help setup docker-up docker-down spark-yellow spark-green \
        spark-fhv spark-citibike spark-all duckdb dashboard psql \
        logs clean test

PYTHON     := python3
DATA_RAW   := data/raw
DATA_PROC  := data/processed
DATA_ANA   := data/analytics
SPARK      := spark-submit --master local[*] --driver-memory 4g
PG_CONN    := postgresql://nyc_user:nyc_pass_2025@localhost:5432/nyc_mobility

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────
setup: ## Copy raw data files and create directory structure
	@echo "Setting up project structure..."
	mkdir -p $(DATA_RAW) $(DATA_PROC) $(DATA_ANA)
	mkdir -p airflow/logs airflow/plugins
	$(PYTHON) spark_jobs/setup_data.py --source /mnt/user-data/uploads --dest $(DATA_RAW)
	@echo "Setup complete ✓"

setup-local: ## Copy data from local path (DATA_SOURCE=... make setup-local)
	$(PYTHON) spark_jobs/setup_data.py --source $(DATA_SOURCE) --dest $(DATA_RAW)

# ── Docker ─────────────────────────────────────────────────────────
docker-up: ## Start all Docker containers
	docker-compose up -d
	@echo "Services started:"
	@echo "  → PostgreSQL:  localhost:5432"
	@echo "  → Airflow UI:  http://localhost:8080  (admin/admin)"
	@echo "  → Spark UI:    http://localhost:4040"
	@echo "  → Dashboard:   http://localhost:8501"

docker-down: ## Stop all Docker containers
	docker-compose down

docker-build: ## Rebuild Docker images
	docker-compose build --no-cache

docker-logs: ## Show logs from all containers
	docker-compose logs -f

docker-ps: ## Show running containers
	docker-compose ps

# ── Spark ETL ──────────────────────────────────────────────────────
spark-yellow: ## Run Yellow Taxi PySpark ETL
	$(SPARK) spark_jobs/yellow_taxi_etl.py \
	  --input $(DATA_RAW)/yellow_tripdata_2025-01.parquet \
	  --output $(DATA_PROC) \
	  --analytics $(DATA_ANA)

spark-green: ## Run Green Taxi PySpark ETL
	$(SPARK) spark_jobs/green_taxi_etl.py \
	  --input $(DATA_RAW)/green_tripdata_2025-01.parquet \
	  --output $(DATA_PROC) \
	  --analytics $(DATA_ANA)

spark-fhv: ## Run FHV PySpark ETL
	$(SPARK) spark_jobs/fhv_etl.py \
	  --input $(DATA_RAW)/fhv_tripdata_2025-01.parquet \
	  --output $(DATA_PROC) \
	  --analytics $(DATA_ANA)

spark-citibike: ## Run CitiBike PySpark ETL (CSV → Parquet)
	$(SPARK) spark_jobs/citibike_etl.py \
	  --input_dir $(DATA_RAW) \
	  --output $(DATA_PROC) \
	  --analytics $(DATA_ANA)

spark-all: spark-yellow spark-green spark-fhv spark-citibike ## Run all Spark ETL jobs
	@echo "All Spark ETL jobs completed ✓"

# ── DuckDB Analytics ───────────────────────────────────────────────
duckdb: ## Run DuckDB OLAP analytics on Parquet files
	$(PYTHON) spark_jobs/duckdb_analytics.py \
	  --data_dir $(DATA_RAW) \
	  --output $(DATA_ANA)
	@echo "DuckDB analytics completed ✓"

# ── PostgreSQL ─────────────────────────────────────────────────────
psql: ## Connect to PostgreSQL (requires psql client)
	psql "$(PG_CONN)"

psql-schema: ## Apply schema to local PostgreSQL
	psql "$(PG_CONN)" -f postgres/schema.sql
	@echo "Schema applied ✓"

psql-test: ## Run a quick test query
	psql "$(PG_CONN)" -c "SELECT dataset, metric_name, metric_value FROM analytics_kpis LIMIT 10;"

# ── Dashboard ──────────────────────────────────────────────────────
dashboard: ## Launch Streamlit dashboard locally
	streamlit run dashboard/app.py \
	  --server.port 8501 \
	  --server.headless true \
	  --theme.base dark

install: ## Install Python dependencies locally
	pip install -r docker/requirements.dashboard.txt
	pip install -r docker/requirements.spark.txt

# ── Testing ────────────────────────────────────────────────────────
test: ## Run data validation checks
	$(PYTHON) -c "
import pyarrow.parquet as pq, pandas as pd
for name, path in [
  ('Yellow', 'data/raw/yellow_tripdata_2025-01.parquet'),
  ('Green',  'data/raw/green_tripdata_2025-01.parquet'),
  ('FHV',    'data/raw/fhv_tripdata_2025-01.parquet'),
]:
    df = pq.read_table(path).to_pandas()
    print(f'{name}: {len(df):,} rows, {len(df.columns)} cols')
print('All Parquet files valid ✓')
"

# ── Clean ──────────────────────────────────────────────────────────
clean: ## Remove processed and analytics files
	rm -rf $(DATA_PROC)/* $(DATA_ANA)/*
	@echo "Cleaned processed and analytics directories ✓"

clean-all: clean ## Remove all generated files including Docker volumes
	docker-compose down -v
	@echo "All cleaned ✓"
