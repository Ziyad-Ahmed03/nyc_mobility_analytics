"""
NYC Mobility Analytics — Yellow Taxi ETL Job
=============================================
PySpark job to clean, transform, and compute analytics
on the NYC TLC Yellow Taxi Parquet dataset.

Usage:
    spark-submit spark_jobs/yellow_taxi_etl.py \
        --input data/raw/yellow_tripdata_2025-01.parquet \
        --output data/processed/yellow \
        --analytics data/analytics
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("yellow_taxi_etl")

# ── TLC Zone Lookup (embedded) ────────────────────────────────────────
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

PAYMENT_MAP = {1: "Credit Card", 2: "Cash", 3: "No Charge", 4: "Dispute", 5: "Unknown", 6: "Voided"}
VENDOR_MAP  = {1: "Creative Mobile Tech", 2: "VeriFone Inc"}
DOW_MAP     = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}


def build_spark_session(app_name: str = "YellowTaxiETL") -> SparkSession:
    """Create and return a configured SparkSession."""
    return (
        SparkSession.builder
        .appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.parquet.enableVectorizedReader", "true")
        .config("spark.driver.memory", "4g")
        .config("spark.executor.memory", "4g")
        .getOrCreate()
    )


def load_raw(spark: SparkSession, input_path: str):
    """Load raw Parquet file into Spark DataFrame."""
    log.info(f"Loading raw data from: {input_path}")
    df = spark.read.parquet(input_path)
    log.info(f"Raw rows: {df.count():,} | Columns: {len(df.columns)}")
    return df


def clean(df):
    """
    Apply data quality filters:
    - Valid fare range ($0.01 – $500)
    - Valid distance (0.01 – 200 miles)
    - Valid passenger count (1 – 6)
    - Valid pickup timestamps (January 2025)
    - Valid trip duration (1 – 180 minutes)
    """
    log.info("Applying data cleaning filters …")

    df = df.filter(
        (F.col("fare_amount").between(0.01, 500)) &
        (F.col("trip_distance").between(0.01, 200)) &
        (F.col("passenger_count").between(1, 6)) &
        (F.year("tpep_pickup_datetime") == 2025) &
        (F.month("tpep_pickup_datetime") == 1)
    )

    # Compute duration
    df = df.withColumn(
        "duration_min",
        (F.unix_timestamp("tpep_dropoff_datetime") - F.unix_timestamp("tpep_pickup_datetime")) / 60.0
    )
    df = df.filter(F.col("duration_min").between(1, 180))

    log.info(f"After cleaning: {df.count():,} rows")
    return df


def feature_engineering(df):
    """
    Derive time-based and categorical features:
    - hour_of_day, day_of_week, day_of_month, is_weekend
    - payment_label, vendor_label, zone names
    """
    log.info("Running feature engineering …")

    # Time features
    df = (
        df
        .withColumn("hour_of_day",   F.hour("tpep_pickup_datetime"))
        .withColumn("day_of_month",   F.dayofmonth("tpep_pickup_datetime"))
        .withColumn("day_of_week_num",((F.dayofweek("tpep_pickup_datetime") + 5) % 7))  # 0=Mon, 6=Sun
        .withColumn("week_of_year",   F.weekofyear("tpep_pickup_datetime"))
        .withColumn("is_weekend",     F.when(F.dayofweek("tpep_pickup_datetime").isin([1, 7]), 1).otherwise(0))
        .withColumn("is_rush_hour",   F.when(
            (F.hour("tpep_pickup_datetime").between(7, 9)) |
            (F.hour("tpep_pickup_datetime").between(16, 19)), 1).otherwise(0))
    )

    # Categorical labels
    payment_expr = F.create_map([F.lit(k) for kv in PAYMENT_MAP.items() for k in kv])
    vendor_expr  = F.create_map([F.lit(k) for kv in VENDOR_MAP.items()  for k in kv])

    df = (
        df
        .withColumn("payment_label", payment_expr[F.col("payment_type").cast(IntegerType())])
        .withColumn("vendor_label",  vendor_expr[F.col("VendorID").cast(IntegerType())])
        .withColumn("revenue_per_mile", F.when(F.col("trip_distance") > 0,
            F.col("fare_amount") / F.col("trip_distance")).otherwise(None))
        .withColumn("tip_rate", F.when(F.col("fare_amount") > 0,
            F.col("tip_amount") / F.col("fare_amount")).otherwise(None))
        .withColumn("dataset", F.lit("yellow"))
        .withColumn("data_source", F.lit("NYC TLC Yellow Taxi — January 2025"))
    )

    return df


def compute_kpis(df) -> dict:
    """Compute top-level KPI metrics and return as dict."""
    log.info("Computing KPIs …")

    agg = df.agg(
        F.count("*").alias("total_trips"),
        F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
        F.round(F.avg("trip_distance"), 2).alias("avg_distance"),
        F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        F.round(F.avg("passenger_count"), 2).alias("avg_passengers"),
        F.round(F.avg("tip_amount"), 2).alias("avg_tip"),
        F.round(F.sum("fare_amount"), 0).alias("total_fare"),
        F.round(F.sum("tip_amount"), 0).alias("total_tips"),
        F.round(F.sum("tolls_amount"), 0).alias("total_tolls"),
        F.round(F.sum("mta_tax"), 0).alias("total_mta_tax"),
        F.round(F.sum("congestion_surcharge"), 0).alias("total_congestion"),
        F.round(F.sum("improvement_surcharge"), 0).alias("total_improvement"),
        F.round(F.sum("total_amount"), 0).alias("total_revenue"),
    ).collect()[0].asDict()

    log.info(f"KPIs — Trips: {agg['total_trips']:,} | Revenue: ${agg['total_revenue']/1e6:.2f}M")
    return agg


def compute_hourly(df):
    """Trips and avg fare grouped by hour of day."""
    return (
        df.groupBy("hour_of_day")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
            F.round(F.avg("tip_amount"), 2).alias("avg_tip"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        )
        .orderBy("hour_of_day")
    )


def compute_daily(df):
    """Trips grouped by day of month."""
    return (
        df.groupBy("day_of_month")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
        )
        .orderBy("day_of_month")
    )


def compute_dow(df):
    """Trips and fares grouped by day of week."""
    dow_map_expr = F.create_map([F.lit(x) for kv in DOW_MAP.items() for x in kv])
    return (
        df.groupBy("day_of_week_num")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
            F.round(F.avg("tip_amount"), 2).alias("avg_tip"),
        )
        .withColumn("day_name", dow_map_expr[F.col("day_of_week_num")])
        .orderBy("day_of_week_num")
    )


def compute_top_zones(df, top_n: int = 15):
    """Top pickup zones by trip volume with avg fare and distance."""
    zone_map_expr = F.create_map([F.lit(x) for kv in ZONE_NAMES.items() for x in kv])
    return (
        df.groupBy("PULocationID")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
            F.round(F.avg("trip_distance"), 2).alias("avg_dist"),
        )
        .withColumn("zone_name",
            F.coalesce(zone_map_expr[F.col("PULocationID")],
                       F.concat(F.lit("Zone "), F.col("PULocationID").cast(StringType()))))
        .orderBy(F.desc("trips"))
        .limit(top_n)
    )


def compute_payment_dist(df):
    """Payment method distribution."""
    return (
        df.groupBy("payment_label")
        .agg(F.count("*").alias("trips"))
        .orderBy(F.desc("trips"))
    )


def compute_revenue_components(df):
    """Revenue broken down by component."""
    return df.agg(
        F.round(F.sum("fare_amount"), 0).alias("base_fare"),
        F.round(F.sum("tip_amount"), 0).alias("tips"),
        F.round(F.sum("tolls_amount"), 0).alias("tolls"),
        F.round(F.sum("mta_tax"), 0).alias("mta_tax"),
        F.round(F.sum("congestion_surcharge"), 0).alias("congestion_surcharge"),
        F.round(F.sum("improvement_surcharge"), 0).alias("improvement_surcharge"),
        F.round(F.sum("total_amount"), 0).alias("total_revenue"),
    )


def compute_vendor_dist(df):
    """Vendor market share."""
    return (
        df.groupBy("vendor_label")
        .agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
        )
        .orderBy(F.desc("trips"))
    )


def save_parquet(df, output_path: str, mode: str = "overwrite"):
    """Write DataFrame to Parquet with logging."""
    log.info(f"Saving → {output_path}")
    df.coalesce(4).write.mode(mode).parquet(output_path)
    log.info(f"Saved: {output_path}")


def run(input_path: str, output_dir: str, analytics_dir: str):
    """Main ETL pipeline entry point."""
    spark = build_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    # ── Load & Clean ──────────────────────────────────────────────────
    raw_df   = load_raw(spark, input_path)
    clean_df = clean(raw_df)
    feat_df  = feature_engineering(clean_df)
    feat_df.cache()

    # ── Save processed Parquet ────────────────────────────────────────
    save_parquet(feat_df, f"{output_dir}/yellow_processed")

    # ── Compute & Save Analytics ──────────────────────────────────────
    analytics_tables = {
        "yellow_hourly":    compute_hourly(feat_df),
        "yellow_daily":     compute_daily(feat_df),
        "yellow_dow":       compute_dow(feat_df),
        "yellow_top_zones": compute_top_zones(feat_df),
        "yellow_payment":   compute_payment_dist(feat_df),
        "yellow_revenue":   compute_revenue_components(feat_df),
        "yellow_vendor":    compute_vendor_dist(feat_df),
    }

    for name, df in analytics_tables.items():
        save_parquet(df, f"{analytics_dir}/{name}")

    # ── KPIs as JSON ──────────────────────────────────────────────────
    kpis = compute_kpis(feat_df)
    kpi_path = Path(analytics_dir) / "yellow_kpis.json"
    kpi_path.parent.mkdir(parents=True, exist_ok=True)
    with open(kpi_path, "w") as f:
        json.dump({k: float(v) if isinstance(v, (int, float)) else v for k, v in kpis.items()}, f, indent=2)
    log.info(f"KPIs saved → {kpi_path}")

    feat_df.unpersist()
    spark.stop()
    log.info("Yellow Taxi ETL completed successfully ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yellow Taxi ETL — PySpark")
    parser.add_argument("--input",     default="data/raw/yellow_tripdata_2025-01.parquet")
    parser.add_argument("--output",    default="data/processed")
    parser.add_argument("--analytics", default="data/analytics")
    args = parser.parse_args()
    run(args.input, args.output, args.analytics)
