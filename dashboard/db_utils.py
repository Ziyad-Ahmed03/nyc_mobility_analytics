"""
NYC Mobility Analytics — PostgreSQL Connection Utility
======================================================
Shared helper for connecting to PostgreSQL from any script.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
import pandas as pd
from sqlalchemy import create_engine, text

log = logging.getLogger(__name__)


def get_pg_conn_str() -> str:
    """Build PostgreSQL connection string from environment variables."""
    host = os.getenv("NYC_PG_HOST",     "localhost")
    port = os.getenv("NYC_PG_PORT",     "5432")
    db   = os.getenv("NYC_PG_DB",       "nyc_mobility")
    user = os.getenv("NYC_PG_USER",     "nyc_user")
    pwd  = os.getenv("NYC_PG_PASS",     "nyc_pass_2025")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def get_engine():
    """Return a SQLAlchemy engine connected to the NYC Mobility database."""
    conn_str = get_pg_conn_str()
    engine = create_engine(conn_str, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return engine


@contextmanager
def get_psycopg2_conn():
    """Context manager yielding a psycopg2 connection."""
    conn = psycopg2.connect(
        host=os.getenv("NYC_PG_HOST",  "localhost"),
        port=int(os.getenv("NYC_PG_PORT", "5432")),
        dbname=os.getenv("NYC_PG_DB",  "nyc_mobility"),
        user=os.getenv("NYC_PG_USER",  "nyc_user"),
        password=os.getenv("NYC_PG_PASS","nyc_pass_2025"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


def query_df(sql: str, params=None) -> pd.DataFrame:
    """Execute a SQL query and return a Pandas DataFrame."""
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def upsert_kpis(dataset: str, kpis: dict, data_month: str = "2025-01"):
    """Upsert KPI metrics into the analytics_kpis table."""
    with get_psycopg2_conn() as conn:
        with conn.cursor() as cur:
            for metric_name, metric_value in kpis.items():
                if not isinstance(metric_value, (int, float)):
                    continue
                cur.execute("""
                    INSERT INTO analytics_kpis
                        (dataset, metric_name, metric_value, data_month, recorded_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (dataset, metric_name, (recorded_at::date))
                    DO UPDATE SET metric_value = EXCLUDED.metric_value,
                                  updated_at   = NOW()
                """, (dataset, metric_name, float(metric_value), data_month))
        conn.commit()
    log.info(f"Upserted {len(kpis)} KPIs for [{dataset}] ✓")


def load_kpis_from_pg(dataset: Optional[str] = None) -> pd.DataFrame:
    """Load KPIs from PostgreSQL, optionally filtered by dataset."""
    if not test_connection():
        csv_path = os.path.join(os.path.dirname(__file__), "static_data", "analytics_kpis.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            if dataset:
                df = df[df["dataset"] == dataset]
            return df
        return pd.DataFrame()
        
    if dataset:
        return query_df(
            "SELECT * FROM analytics_kpis WHERE dataset = :dataset ORDER BY metric_name",
            params={"dataset": dataset}
        )
    return query_df("SELECT * FROM analytics_kpis ORDER BY dataset, metric_name")


def load_top_zones_from_pg() -> pd.DataFrame:
    """Load top pickup zones from PostgreSQL."""
    if not test_connection():
        csv_path = os.path.join(os.path.dirname(__file__), "static_data", "top_pickup_zones.csv")
        if os.path.exists(csv_path):
            return pd.read_csv(csv_path)
        return pd.DataFrame()
        
    return query_df("SELECT * FROM top_pickup_zones ORDER BY trips DESC")


def load_hourly_from_pg(dataset: str = "yellow") -> pd.DataFrame:
    """Load hourly analytics from PostgreSQL."""
    if not test_connection():
        csv_path = os.path.join(os.path.dirname(__file__), "static_data", "hourly_analytics.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            return df[df["dataset"] == dataset]
        return pd.DataFrame()
        
    return query_df(
        "SELECT * FROM hourly_analytics WHERE dataset = :dataset ORDER BY hour_of_day",
        params={"dataset": dataset}
    )


def test_connection() -> bool:
    """Test PostgreSQL connectivity, return True if successful."""
    try:
        with get_psycopg2_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        log.info("PostgreSQL connection: OK ✓")
        return True
    except Exception as e:
        log.error(f"PostgreSQL connection failed: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if test_connection():
        kpis_df = load_kpis_from_pg("yellow")
        print(kpis_df.to_string())
