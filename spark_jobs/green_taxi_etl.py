"""
NYC Mobility Analytics — Green Taxi ETL Job
============================================
PySpark job to clean, transform, and compute analytics
on the NYC TLC Green Taxi Parquet dataset.

Usage:
    spark-submit spark_jobs/green_taxi_etl.py \
        --input data/raw/green_tripdata_2025-01.parquet \
        --output data/processed \
        --analytics data/analytics
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("green_taxi_etl")

ZONE_NAMES = {
    132: "JFK Airport", 138: "LaGuardia Airport", 161: "Midtown East",
    162: "Midtown North", 163: "Midtown South", 186: "Penn Station/Madison Sq W",
    236: "Upper East Side N", 237: "Upper East Side S", 142: "Lincoln Square E",
    239: "Upper West Side S", 238: "Upper West Side N", 79: "East Village",
    249: "West Village", 224: "Times Sq/Theatre Dist", 87: "Financial District N",
    82: "Elmhurst", 74: "East Harlem N", 75: "East Harlem S", 119: "Highbridge Park",
    65: "East Concourse/Concourse Village", 41: "Central Park",
}
PAYMENT_MAP  = {1: "Credit Card", 2: "Cash", 3: "No Charge", 4: "Dispute"}
TRIP_TYPE_MAP = {1: "Street Hail", 2: "Dispatch"}
DOW_MAP = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday",5:"Saturday",6:"Sunday"}


def build_spark(app_name="GreenTaxiETL"):
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "4g")
        .getOrCreate()
    )


def clean(df):
    log.info("Cleaning Green Taxi data …")
    df = df.filter(
        (F.col("fare_amount").between(0.01, 500)) &
        (F.col("trip_distance").between(0.01, 200)) &
        (F.col("passenger_count").between(1, 6)) &
        (F.year("lpep_pickup_datetime") == 2025) &
        (F.month("lpep_pickup_datetime") == 1)
    )
    df = df.withColumn(
        "duration_min",
        (F.unix_timestamp("lpep_dropoff_datetime") - F.unix_timestamp("lpep_pickup_datetime")) / 60.0
    ).filter(F.col("duration_min").between(1, 180))

    log.info(f"After cleaning: {df.count():,} rows")
    return df


def feature_engineering(df):
    log.info("Feature engineering …")
    payment_expr  = F.create_map([F.lit(x) for kv in PAYMENT_MAP.items()  for x in kv])
    trip_type_expr = F.create_map([F.lit(x) for kv in TRIP_TYPE_MAP.items() for x in kv])

    return (
        df
        .withColumn("hour_of_day",    F.hour("lpep_pickup_datetime"))
        .withColumn("day_of_month",    F.dayofmonth("lpep_pickup_datetime"))
        .withColumn("day_of_week_num", ((F.dayofweek("lpep_pickup_datetime") + 5) % 7))  # 0=Mon, 6=Sun
        .withColumn("week_of_year",    F.weekofyear("lpep_pickup_datetime"))
        .withColumn("is_weekend",      F.when(F.dayofweek("lpep_pickup_datetime").isin([1, 7]), 1).otherwise(0))
        .withColumn("is_rush_hour",    F.when(
            (F.hour("lpep_pickup_datetime").between(7, 9)) |
            (F.hour("lpep_pickup_datetime").between(16, 19)), 1).otherwise(0))
        .withColumn("payment_label",   payment_expr[F.col("payment_type").cast(IntegerType())])
        .withColumn("trip_type_label", trip_type_expr[F.col("trip_type").cast(IntegerType())])
        .withColumn("tip_rate",        F.when(F.col("fare_amount") > 0, F.col("tip_amount") / F.col("fare_amount")).otherwise(None))
        .withColumn("dataset",         F.lit("green"))
        .withColumn("data_source",     F.lit("NYC TLC Green Taxi — January 2025"))
    )


def compute_kpis(df) -> dict:
    log.info("Computing Green KPIs …")
    return df.agg(
        F.count("*").alias("total_trips"),
        F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
        F.round(F.avg("trip_distance"), 2).alias("avg_distance"),
        F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        F.round(F.avg("passenger_count"), 2).alias("avg_passengers"),
        F.round(F.sum("total_amount"), 0).alias("total_revenue"),
        F.round(F.sum("fare_amount"), 0).alias("total_fare"),
        F.round(F.sum("tip_amount"), 0).alias("total_tips"),
    ).collect()[0].asDict()


def run(input_path: str, output_dir: str, analytics_dir: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    raw_df  = spark.read.parquet(input_path)
    log.info(f"Green raw rows: {raw_df.count():,}")

    clean_df = clean(raw_df)
    feat_df  = feature_engineering(clean_df)
    feat_df.cache()

    # Save processed
    out = f"{output_dir}/green_processed"
    feat_df.coalesce(2).write.mode("overwrite").parquet(out)
    log.info(f"Saved processed → {out}")

    # Analytics
    zone_map = F.create_map([F.lit(x) for kv in ZONE_NAMES.items() for x in kv])
    dow_map  = F.create_map([F.lit(x) for kv in DOW_MAP.items() for x in kv])

    analytics = {
        "green_hourly": feat_df.groupBy("hour_of_day").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
        ).orderBy("hour_of_day"),

        "green_dow": feat_df.groupBy("day_of_week_num").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
        ).withColumn("day_name", dow_map[F.col("day_of_week_num")]).orderBy("day_of_week_num"),

        "green_top_zones": (
            feat_df.groupBy("PULocationID").agg(
                F.count("*").alias("trips"),
                F.round(F.avg("fare_amount"), 2).alias("avg_fare"),
                F.round(F.avg("trip_distance"), 2).alias("avg_dist"),
            )
            .withColumn("zone_name", F.coalesce(zone_map[F.col("PULocationID")],
                F.concat(F.lit("Zone "), F.col("PULocationID").cast(StringType()))))
            .orderBy(F.desc("trips")).limit(15)
        ),

        "green_trip_type": feat_df.groupBy("trip_type_label").agg(
            F.count("*").alias("trips")
        ).orderBy(F.desc("trips")),

        "green_revenue": feat_df.agg(
            F.round(F.sum("fare_amount"), 0).alias("base_fare"),
            F.round(F.sum("tip_amount"), 0).alias("tips"),
            F.round(F.sum("total_amount"), 0).alias("total_revenue"),
        ),
    }

    for name, df in analytics.items():
        path = f"{analytics_dir}/{name}"
        df.coalesce(1).write.mode("overwrite").parquet(path)
        log.info(f"Saved analytics → {path}")

    # KPIs
    kpis = compute_kpis(feat_df)
    kpi_path = Path(analytics_dir) / "green_kpis.json"
    kpi_path.parent.mkdir(parents=True, exist_ok=True)
    with open(kpi_path, "w") as f:
        json.dump({k: float(v) if isinstance(v, (int, float)) else v for k, v in kpis.items()}, f, indent=2)
    log.info(f"KPIs saved → {kpi_path}")

    feat_df.unpersist()
    spark.stop()
    log.info("Green Taxi ETL completed ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Green Taxi ETL — PySpark")
    parser.add_argument("--input",     default="data/raw/green_tripdata_2025-01.parquet")
    parser.add_argument("--output",    default="data/processed")
    parser.add_argument("--analytics", default="data/analytics")
    args = parser.parse_args()
    run(args.input, args.output, args.analytics)
