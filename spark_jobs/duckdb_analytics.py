"""
NYC Mobility Analytics — DuckDB OLAP Query Engine
==================================================
Runs fast OLAP queries directly on Parquet files using DuckDB.
Produces analytics JSON outputs for the dashboard and PostgreSQL loader.

Usage:
    python spark_jobs/duckdb_analytics.py \
        --data_dir data/processed \
        --output   data/analytics
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("duckdb_analytics")

# ── Zone lookup (TLC official zone names) ────────────────────────────
ZONE_NAMES = {
    132: "JFK Airport",          138: "LaGuardia Airport",
    161: "Midtown East",         162: "Midtown North",
    163: "Midtown South",        186: "Penn Station/Madison Sq W",
    230: "Two Bridges/Seaport",  236: "Upper East Side N",
    237: "Upper East Side S",    142: "Lincoln Square E",
    239: "Upper West Side S",    238: "Upper West Side N",
    164: "Morningside Heights",  141: "Lenox Hill West",
    140: "Lenox Hill East",      48:  "Clinton East",
    113: "Greenwich Village N",  114: "Greenwich Village S",
    107: "Gramercy",             90:  "Flatiron",
    68:  "East Chelsea",         100: "Garment District",
    79:  "East Village",         249: "West Village",
    224: "Times Sq/Theatre Dist",87:  "Financial District N",
    88:  "Financial District S", 170: "Newark Airport",
    234: "Union Sq",             232: "Sutton Pl/Turtle Bay S",
}

PAYMENT_MAP = {1: "Credit Card", 2: "Cash", 3: "No Charge", 4: "Dispute"}


class DuckDBAnalytics:
    """Run OLAP queries on Parquet files using DuckDB."""

    def __init__(self, data_dir: str, output_dir: str):
        self.data_dir  = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect()
        self.benchmarks = []
        log.info(f"DuckDB version: {duckdb.__version__}")

    def _q(self, sql: str, name: str = "") -> pd.DataFrame:
        """Execute a query, log timing, return DataFrame."""
        t0 = time.perf_counter()
        df = self.con.execute(sql).df()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        if name:
            self.benchmarks.append({"query": name, "time_ms": ms, "rows": len(df)})
            log.info(f"  [{ms:6.1f}ms] {name} → {len(df):,} rows")
        return df

    def _save(self, df: pd.DataFrame, name: str):
        """Save DataFrame as Parquet and JSON."""
        pq_path   = self.output_dir / f"{name}.parquet"
        json_path = self.output_dir / f"{name}.json"
        df.to_parquet(pq_path, index=False)
        df.to_json(json_path, orient="records", indent=2)

    # ── Yellow Taxi ───────────────────────────────────────────────────
    def yellow_analytics(self):
        raw = list(self.data_dir.rglob("yellow_tripdata_2025-01.parquet"))
        if not raw:
            log.warning("Yellow Parquet not found, skipping")
            return {}

        p = str(raw[0])
        log.info(f"=== Yellow Taxi Analytics ({p}) ===")

        kpis = self._q(f"""
            SELECT
                COUNT(*)                                   AS total_trips,
                ROUND(AVG(fare_amount), 2)                 AS avg_fare,
                ROUND(AVG(trip_distance), 2)               AS avg_distance,
                ROUND(AVG(
                    DATEDIFF('minute', tpep_pickup_datetime, tpep_dropoff_datetime)
                ), 2)                                       AS avg_duration_min,
                ROUND(AVG(passenger_count), 2)             AS avg_passengers,
                ROUND(AVG(tip_amount), 2)                  AS avg_tip,
                ROUND(SUM(fare_amount), 0)                 AS total_base_fare,
                ROUND(SUM(tip_amount), 0)                  AS total_tips,
                ROUND(SUM(tolls_amount), 0)                AS total_tolls,
                ROUND(SUM(mta_tax), 0)                     AS total_mta_tax,
                ROUND(SUM(congestion_surcharge), 0)        AS total_congestion,
                ROUND(SUM(improvement_surcharge), 0)       AS total_improvement,
                ROUND(SUM(total_amount), 0)                AS total_revenue
            FROM read_parquet('{p}')
            WHERE fare_amount BETWEEN 0.01 AND 500
              AND trip_distance BETWEEN 0.01 AND 200
              AND passenger_count BETWEEN 1 AND 6
              AND YEAR(tpep_pickup_datetime) = 2025
              AND MONTH(tpep_pickup_datetime) = 1
              AND DATEDIFF('minute', tpep_pickup_datetime, tpep_dropoff_datetime) BETWEEN 1 AND 180
        """, "Yellow KPIs")

        hourly = self._q(f"""
            SELECT
                HOUR(tpep_pickup_datetime)             AS hour_of_day,
                COUNT(*)                               AS trips,
                ROUND(AVG(fare_amount), 2)             AS avg_fare,
                ROUND(AVG(tip_amount), 2)              AS avg_tip,
                ROUND(AVG(
                    DATEDIFF('minute', tpep_pickup_datetime, tpep_dropoff_datetime)
                ), 2)                                   AS avg_duration
            FROM read_parquet('{p}')
            WHERE fare_amount BETWEEN 0.01 AND 500
              AND YEAR(tpep_pickup_datetime) = 2025
              AND MONTH(tpep_pickup_datetime) = 1
            GROUP BY 1 ORDER BY 1
        """, "Yellow Hourly")

        daily = self._q(f"""
            SELECT
                DAY(tpep_pickup_datetime)  AS day_of_month,
                COUNT(*)                   AS trips,
                ROUND(AVG(fare_amount), 2) AS avg_fare
            FROM read_parquet('{p}')
            WHERE YEAR(tpep_pickup_datetime) = 2025
              AND MONTH(tpep_pickup_datetime) = 1
            GROUP BY 1 ORDER BY 1
        """, "Yellow Daily")

        dow = self._q(f"""
            SELECT
                DAYOFWEEK(tpep_pickup_datetime)  AS dow_num,
                DAYNAME(tpep_pickup_datetime)    AS day_name,
                COUNT(*)                         AS trips,
                ROUND(AVG(fare_amount), 2)       AS avg_fare,
                ROUND(AVG(tip_amount), 2)        AS avg_tip
            FROM read_parquet('{p}')
            WHERE YEAR(tpep_pickup_datetime) = 2025
              AND MONTH(tpep_pickup_datetime) = 1
            GROUP BY 1, 2 ORDER BY 1
        """, "Yellow DOW")

        zones = self._q(f"""
            SELECT
                PULocationID                          AS zone_id,
                COUNT(*)                              AS trips,
                ROUND(AVG(fare_amount), 2)            AS avg_fare,
                ROUND(AVG(trip_distance), 2)          AS avg_dist
            FROM read_parquet('{p}')
            WHERE fare_amount BETWEEN 0.01 AND 500
              AND YEAR(tpep_pickup_datetime) = 2025
              AND MONTH(tpep_pickup_datetime) = 1
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        """, "Yellow Top Zones")
        zones["zone_name"] = zones["zone_id"].map(ZONE_NAMES).fillna("Zone " + zones["zone_id"].astype(str))

        payment = self._q(f"""
            SELECT
                payment_type                AS payment_code,
                COUNT(*)                    AS trips
            FROM read_parquet('{p}')
            WHERE YEAR(tpep_pickup_datetime) = 2025
            GROUP BY 1 ORDER BY 2 DESC
        """, "Yellow Payment")
        payment["payment_label"] = payment["payment_code"].map(PAYMENT_MAP).fillna("Unknown")

        revenue = self._q(f"""
            SELECT
                ROUND(SUM(fare_amount), 0)          AS base_fare,
                ROUND(SUM(tip_amount), 0)           AS tips,
                ROUND(SUM(congestion_surcharge), 0) AS congestion_surcharge,
                ROUND(SUM(improvement_surcharge), 0)AS improvement_surcharge,
                ROUND(SUM(tolls_amount), 0)         AS tolls,
                ROUND(SUM(mta_tax), 0)              AS mta_tax,
                ROUND(SUM(total_amount), 0)         AS total_revenue
            FROM read_parquet('{p}')
            WHERE YEAR(tpep_pickup_datetime) = 2025
        """, "Yellow Revenue Breakdown")

        # Save all
        for name, df in {
            "yellow_kpis": kpis, "yellow_hourly": hourly,
            "yellow_daily": daily, "yellow_dow": dow,
            "yellow_top_zones": zones, "yellow_payment": payment,
            "yellow_revenue": revenue,
        }.items():
            self._save(df, name)

        return kpis.to_dict(orient="records")[0]

    # ── Green Taxi ────────────────────────────────────────────────────
    def green_analytics(self):
        raw = list(self.data_dir.rglob("green_tripdata_2025-01.parquet"))
        if not raw:
            log.warning("Green Parquet not found, skipping")
            return {}
        p = str(raw[0])
        log.info(f"=== Green Taxi Analytics ===")

        kpis = self._q(f"""
            SELECT COUNT(*)                  AS total_trips,
                   ROUND(AVG(fare_amount),2) AS avg_fare,
                   ROUND(AVG(trip_distance),2) AS avg_distance,
                   ROUND(SUM(total_amount),0)  AS total_revenue
            FROM read_parquet('{p}')
            WHERE fare_amount BETWEEN 0.01 AND 500
              AND trip_distance BETWEEN 0.01 AND 200
              AND YEAR(lpep_pickup_datetime) = 2025
        """, "Green KPIs")

        hourly = self._q(f"""
            SELECT HOUR(lpep_pickup_datetime) AS hour_of_day,
                   COUNT(*)                  AS trips,
                   ROUND(AVG(fare_amount),2) AS avg_fare
            FROM read_parquet('{p}')
            WHERE YEAR(lpep_pickup_datetime) = 2025
            GROUP BY 1 ORDER BY 1
        """, "Green Hourly")

        zones = self._q(f"""
            SELECT PULocationID AS zone_id,
                   COUNT(*)     AS trips,
                   ROUND(AVG(fare_amount),2) AS avg_fare
            FROM read_parquet('{p}')
            WHERE YEAR(lpep_pickup_datetime) = 2025
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        """, "Green Top Zones")
        zones["zone_name"] = zones["zone_id"].map(ZONE_NAMES).fillna("Zone " + zones["zone_id"].astype(str))

        for name, df in {"green_kpis": kpis, "green_hourly": hourly, "green_top_zones": zones}.items():
            self._save(df, name)

        return kpis.to_dict(orient="records")[0]

    # ── FHV ──────────────────────────────────────────────────────────
    def fhv_analytics(self):
        raw = list(self.data_dir.rglob("fhv_tripdata_2025-01.parquet"))
        if not raw:
            log.warning("FHV Parquet not found, skipping")
            return {}
        p = str(raw[0])
        log.info("=== FHV Analytics ===")

        kpis = self._q(f"""
            SELECT COUNT(*)                         AS total_trips,
                   ROUND(AVG(
                       DATEDIFF('minute', pickup_datetime, dropOff_datetime)
                   ), 2)                             AS avg_duration_min,
                   COUNT(DISTINCT dispatching_base_num) AS unique_bases
            FROM read_parquet('{p}')
            WHERE YEAR(pickup_datetime) = 2025
              AND MONTH(pickup_datetime) = 1
              AND DATEDIFF('minute', pickup_datetime, dropOff_datetime) BETWEEN 1 AND 300
        """, "FHV KPIs")

        hourly = self._q(f"""
            SELECT HOUR(pickup_datetime)            AS hour_of_day,
                   COUNT(*)                         AS trips,
                   ROUND(AVG(
                       DATEDIFF('minute', pickup_datetime, dropOff_datetime)
                   ), 2)                             AS avg_duration
            FROM read_parquet('{p}')
            WHERE YEAR(pickup_datetime) = 2025
              AND MONTH(pickup_datetime) = 1
            GROUP BY 1 ORDER BY 1
        """, "FHV Hourly")

        bases = self._q(f"""
            SELECT dispatching_base_num AS base,
                   COUNT(*)             AS trips
            FROM read_parquet('{p}')
            WHERE YEAR(pickup_datetime) = 2025
            GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """, "FHV Top Bases")

        for name, df in {"fhv_kpis": kpis, "fhv_hourly": hourly, "fhv_top_bases": bases}.items():
            self._save(df, name)

        return kpis.to_dict(orient="records")[0]

    # ── CitiBike ──────────────────────────────────────────────────────
    def citibike_analytics(self):
        paths = [
            str(self.data_dir / "202501-citibike-tripdata_1.csv"),
            str(self.data_dir / "202501-citibike-tripdata_2.csv"),
            str(self.data_dir / "202501-citibike-tripdata_3.csv"),
        ]
        existing = [p for p in paths if Path(p).exists()]
        if not existing:
            log.warning("CitiBike CSVs not found, skipping")
            return {}

        log.info("=== CitiBike Analytics ===")
        views = []
        for i, p in enumerate(existing):
            self.con.execute(f"CREATE OR REPLACE VIEW cb_{i} AS SELECT * FROM read_csv_auto('{p}')")
            views.append(f"SELECT * FROM cb_{i}")
        union_sql = " UNION ALL ".join(views)
        self.con.execute(f"CREATE OR REPLACE VIEW citibike AS {union_sql}")

        kpis = self._q("""
            SELECT COUNT(*)                              AS total_trips,
                   ROUND(AVG(
                       DATEDIFF('minute',
                           TRY_CAST(started_at AS TIMESTAMP),
                           TRY_CAST(ended_at AS TIMESTAMP))
                   ), 2)                                 AS avg_duration_min,
                   SUM(CASE WHEN member_casual='member' THEN 1 ELSE 0 END) AS member_trips,
                   SUM(CASE WHEN member_casual='casual' THEN 1 ELSE 0 END) AS casual_trips,
                   SUM(CASE WHEN rideable_type='electric_bike' THEN 1 ELSE 0 END) AS electric_trips,
                   SUM(CASE WHEN rideable_type='classic_bike'  THEN 1 ELSE 0 END) AS classic_trips
            FROM citibike
            WHERE DATEDIFF('minute',
                TRY_CAST(started_at AS TIMESTAMP),
                TRY_CAST(ended_at   AS TIMESTAMP)) BETWEEN 1 AND 180
        """, "CitiBike KPIs")

        hourly = self._q("""
            SELECT HOUR(TRY_CAST(started_at AS TIMESTAMP))   AS hour_of_day,
                   COUNT(*)                                   AS trips,
                   ROUND(AVG(
                       DATEDIFF('minute',
                           TRY_CAST(started_at AS TIMESTAMP),
                           TRY_CAST(ended_at   AS TIMESTAMP))
                   ), 2)                                       AS avg_duration
            FROM citibike
            WHERE DATEDIFF('minute',
                TRY_CAST(started_at AS TIMESTAMP),
                TRY_CAST(ended_at   AS TIMESTAMP)) BETWEEN 1 AND 180
            GROUP BY 1 ORDER BY 1
        """, "CitiBike Hourly")

        top_stations = self._q("""
            SELECT start_station_name                         AS station,
                   COUNT(*)                                   AS trips,
                   ROUND(AVG(
                       DATEDIFF('minute',
                           TRY_CAST(started_at AS TIMESTAMP),
                           TRY_CAST(ended_at   AS TIMESTAMP))
                   ), 2)                                       AS avg_duration
            FROM citibike
            WHERE start_station_name IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20
        """, "CitiBike Top Stations")

        user_type = self._q("""
            SELECT member_casual AS user_type,
                   COUNT(*)      AS trips,
                   ROUND(AVG(DATEDIFF('minute',
                       TRY_CAST(started_at AS TIMESTAMP),
                       TRY_CAST(ended_at   AS TIMESTAMP))), 2) AS avg_duration
            FROM citibike GROUP BY 1
        """, "CitiBike User Type")

        bike_type = self._q("""
            SELECT rideable_type                                 AS bike_type,
                   COUNT(*)                                      AS trips,
                   ROUND(AVG(DATEDIFF('minute',
                       TRY_CAST(started_at AS TIMESTAMP),
                       TRY_CAST(ended_at   AS TIMESTAMP))), 2)   AS avg_duration
            FROM citibike GROUP BY 1
        """, "CitiBike Bike Type")

        for name, df in {
            "citibike_kpis": kpis, "citibike_hourly": hourly,
            "citibike_top_stations": top_stations,
            "citibike_user_type": user_type, "citibike_bike_type": bike_type,
        }.items():
            self._save(df, name)

        return kpis.to_dict(orient="records")[0]

    # ── Cross-dataset comparison ──────────────────────────────────────
    def combined_summary(self, y_kpis, g_kpis, f_kpis, c_kpis):
        """Build a combined multi-modal summary."""
        summary = {
            "yellow_taxi": y_kpis,
            "green_taxi":  g_kpis,
            "fhv":         f_kpis,
            "citibike":    c_kpis,
            "total_all_trips": (
                int(y_kpis.get("total_trips", 0)) +
                int(g_kpis.get("total_trips", 0)) +
                int(f_kpis.get("total_trips", 0)) +
                int(c_kpis.get("total_trips", 0))
            ),
        }
        path = self.output_dir / "combined_summary.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        log.info(f"Combined summary saved → {path}")

    # ── Benchmarks ────────────────────────────────────────────────────
    def save_benchmarks(self):
        path = self.output_dir / "duckdb_benchmarks.json"
        with open(path, "w") as f:
            json.dump(self.benchmarks, f, indent=2)
        log.info(f"Benchmark results saved → {path}")
        log.info(f"Total queries: {len(self.benchmarks)}")
        log.info(f"Avg time: {sum(b['time_ms'] for b in self.benchmarks)/max(1,len(self.benchmarks)):.1f}ms")

    def close(self):
        """Close the DuckDB connection."""
        if self.con:
            self.con.close()
            log.info("DuckDB connection closed ✓")

    def run_all(self):
        """Run full analytics pipeline across all datasets."""
        log.info("=" * 60)
        log.info("Starting DuckDB Analytics Pipeline")
        log.info("=" * 60)
        try:
            y = self.yellow_analytics()
            g = self.green_analytics()
            f = self.fhv_analytics()
            c = self.citibike_analytics()
            self.combined_summary(y, g, f, c)
            self.save_benchmarks()
            log.info("=" * 60)
            log.info("DuckDB Analytics Pipeline completed ✓")
            log.info("=" * 60)
        except Exception as e:
            log.error(f"Pipeline failed: {e}")
            raise
        finally:
            self.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DuckDB Analytics Engine")
    parser.add_argument("--data_dir", default="data/raw",       help="Directory containing raw Parquet/CSV files")
    parser.add_argument("--output",   default="data/analytics", help="Output directory for analytics Parquet + JSON")
    args = parser.parse_args()
    analytics = DuckDBAnalytics(args.data_dir, args.output)
    analytics.run_all()
