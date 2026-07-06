"""
NYC Mobility Analytics — Fixed Airflow DAG
==========================================
Fixed to use spark-submit correctly inside the custom Airflow image.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.dates import days_ago

DATA_DIR      = os.getenv("NYC_DATA_DIR",  "/opt/airflow/data")
SPARK_JOBS    = "/opt/airflow/spark_jobs"
ANALYTICS_DIR = f"{DATA_DIR}/analytics"
RAW_DIR       = f"{DATA_DIR}/raw"
PROCESSED_DIR = f"{DATA_DIR}/processed"
POSTGRES_CONN = "nyc_postgres"
SPARK_HOME    = os.getenv("SPARK_HOME", "/opt/spark")
SPARK_SUBMIT  = f"{SPARK_HOME}/bin/spark-submit"

log = logging.getLogger(__name__)

default_args = {
    "owner":            "nyc_mobility",
    "depends_on_past":  False,
    "email_on_failure": False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "execution_timeout":timedelta(hours=2),
}


def validate_files(**context):
    required = [
        f"{RAW_DIR}/yellow_tripdata_2025-01.parquet",
        f"{RAW_DIR}/green_tripdata_2025-01.parquet",
        f"{RAW_DIR}/fhv_tripdata_2025-01.parquet",
        f"{RAW_DIR}/202501-citibike-tripdata_1.csv",
        f"{RAW_DIR}/202501-citibike-tripdata_2.csv",
        f"{RAW_DIR}/202501-citibike-tripdata_3.csv",
    ]
    missing = [f for f in required if not Path(f).exists()]
    if missing:
        raise FileNotFoundError(f"Missing: {missing}")
    log.info(f"All {len(required)} files validated ✓")


def run_duckdb(**context):
    import sys
    sys.path.insert(0, SPARK_JOBS)
    from duckdb_analytics import DuckDBAnalytics
    Path(ANALYTICS_DIR).mkdir(parents=True, exist_ok=True)
    engine = DuckDBAnalytics(data_dir=RAW_DIR, output_dir=ANALYTICS_DIR)
    engine.run_all()
    log.info("DuckDB analytics completed ✓")


def load_kpis(**context):
    import json
    from pathlib import Path
    try:
        from airflow.providers.postgres.hooks.postgres import PostgresHook
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN)
    except Exception as e:
        log.warning(f"PostgreSQL not available: {e}")
        return

    for dataset in ["yellow", "green", "fhv", "citibike"]:
        kpi_file = Path(ANALYTICS_DIR) / f"{dataset}_kpis.json"
        if not kpi_file.exists():
            continue
        with open(kpi_file) as f:
            kpis = json.load(f)
        for k, v in kpis.items():
            if isinstance(v, (int, float)):
                try:
                    hook.run("""
                        INSERT INTO analytics_kpis (dataset, metric_name, metric_value, recorded_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (dataset, metric_name, (recorded_at::date))
                        DO UPDATE SET metric_value = EXCLUDED.metric_value
                    """, parameters=(dataset, k, float(v)), autocommit=True)
                except Exception as e:
                    log.warning(f"KPI insert failed: {e}")
    log.info("KPIs loaded ✓")


# ── SPARK SUBMIT COMMAND ─────────────────────────────────────────────
def spark_cmd(script, extra_args=""):
    return (
        f"{SPARK_SUBMIT} "
        f"--master local[*] "
        f"--driver-memory 4g "
        f"--executor-memory 4g "
        f"{SPARK_JOBS}/{script} "
        f"{extra_args}"
    )


with DAG(
    dag_id="nyc_mobility_analytics",
    description="NYC Mobility Analytics — Full ETL Pipeline",
    default_args=default_args,
    schedule_interval="0 6 1 * *",
    start_date=days_ago(1),
    catchup=False,
    tags=["nyc", "etl", "spark", "duckdb"],
) as dag:

    start = EmptyOperator(task_id="start")

    validate = PythonOperator(
        task_id="validate_input_files",
        python_callable=validate_files,
    )

    spark_yellow = BashOperator(
        task_id="spark_yellow_taxi_etl",
        bash_command=spark_cmd(
            "yellow_taxi_etl.py",
            f"--input {RAW_DIR}/yellow_tripdata_2025-01.parquet "
            f"--output {PROCESSED_DIR} --analytics {ANALYTICS_DIR}"
        ),
    )

    spark_green = BashOperator(
        task_id="spark_green_taxi_etl",
        bash_command=spark_cmd(
            "green_taxi_etl.py",
            f"--input {RAW_DIR}/green_tripdata_2025-01.parquet "
            f"--output {PROCESSED_DIR} --analytics {ANALYTICS_DIR}"
        ),
    )

    spark_fhv = BashOperator(
        task_id="spark_fhv_etl",
        bash_command=spark_cmd(
            "fhv_etl.py",
            f"--input {RAW_DIR}/fhv_tripdata_2025-01.parquet "
            f"--output {PROCESSED_DIR} --analytics {ANALYTICS_DIR}"
        ),
    )

    spark_citibike = BashOperator(
        task_id="spark_citibike_etl",
        bash_command=spark_cmd(
            "citibike_etl.py",
            f"--input_dir {RAW_DIR} "
            f"--output {PROCESSED_DIR} --analytics {ANALYTICS_DIR}"
        ),
    )

    duckdb_task = PythonOperator(
        task_id="run_duckdb_analytics",
        python_callable=run_duckdb,
    )

    load_task = PythonOperator(
        task_id="load_kpis_to_postgres",
        python_callable=load_kpis,
    )

    end = EmptyOperator(task_id="pipeline_complete")

    (
        start
        >> validate
        >> [spark_yellow, spark_green, spark_fhv, spark_citibike]
        >> duckdb_task
        >> load_task
        >> end
    )
