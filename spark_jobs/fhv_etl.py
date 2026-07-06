"""
NYC Mobility Analytics — FHV (For-Hire Vehicle) ETL Job
========================================================
PySpark job to clean, transform, and compute analytics
on the NYC TLC FHV Parquet dataset.

Usage:
    spark-submit spark_jobs/fhv_etl.py \
        --input data/raw/fhv_tripdata_2025-01.parquet \
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
from pyspark.sql.types import StringType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fhv_etl")

ZONE_NAMES = {
    132: "JFK Airport", 138: "LaGuardia Airport", 161: "Midtown East",
    162: "Midtown North", 163: "Midtown South", 186: "Penn Station/Madison Sq W",
    236: "Upper East Side N", 237: "Upper East Side S", 142: "Lincoln Square E",
    239: "Upper West Side S", 238: "Upper West Side N", 79: "East Village",
    249: "West Village", 224: "Times Sq/Theatre Dist", 87: "Financial District N",
    170: "Newark Airport", 56: "Crown Heights N", 61: "Dyker Heights", 76: "East New York",
}

# Known dispatching base companies (partial lookup)
BASE_COMPANIES = {
    "B03614": "Uber", "B02617": "Uber", "B02598": "Uber",
    "B03524": "Lyft", "B02512": "Lyft",
    "B02550": "Juno", "B01536": "Via",
    "B00856": "Dial 7", "B01626": "Carmel",
}

DOW_MAP = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday",5:"Saturday",6:"Sunday"}


def build_spark(app_name="FHV_ETL"):
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "4g")
        .getOrCreate()
    )


def clean(df):
    log.info("Cleaning FHV data …")

    # Filter valid timestamps in Jan 2025
    df = df.filter(
        (F.year("pickup_datetime") == 2025) &
        (F.month("pickup_datetime") == 1) &
        F.col("PUlocationID").isNotNull() &
        F.col("DOlocationID").isNotNull()
    )

    # Compute duration
    df = df.withColumn(
        "duration_min",
        (F.unix_timestamp("dropOff_datetime") - F.unix_timestamp("pickup_datetime")) / 60.0
    ).filter(F.col("duration_min").between(1, 300))

    log.info(f"After cleaning: {df.count():,} rows")
    return df


def feature_engineering(df):
    log.info("Feature engineering for FHV …")

    # Embedded base → company mapping
    base_map_expr = F.create_map([F.lit(x) for kv in BASE_COMPANIES.items() for x in kv])
    zone_map_expr = F.create_map([F.lit(x) for kv in ZONE_NAMES.items() for x in kv])

    return (
        df
        .withColumn("hour_of_day",    F.hour("pickup_datetime"))
        .withColumn("day_of_month",    F.dayofmonth("pickup_datetime"))
        .withColumn("day_of_week_num", ((F.dayofweek("pickup_datetime") + 5) % 7))  # 0=Mon, 6=Sun
        .withColumn("week_of_year",    F.weekofyear("pickup_datetime"))
        .withColumn("is_weekend",      F.when(F.dayofweek("pickup_datetime").isin([1, 7]), 1).otherwise(0))
        .withColumn("is_rush_hour",    F.when(
            (F.hour("pickup_datetime").between(7, 9)) |
            (F.hour("pickup_datetime").between(16, 19)), 1).otherwise(0))
        .withColumn("company",         F.coalesce(
            base_map_expr[F.col("dispatching_base_num")], F.lit("Other TNC")))
        .withColumn("pickup_zone",     F.coalesce(
            zone_map_expr[F.col("PUlocationID").cast("integer")],
            F.concat(F.lit("Zone "), F.col("PUlocationID").cast(StringType()))))
        .withColumn("dropoff_zone",    F.coalesce(
            zone_map_expr[F.col("DOlocationID").cast("integer")],
            F.concat(F.lit("Zone "), F.col("DOlocationID").cast(StringType()))))
        .withColumn("shared_ride",     F.when(F.col("SR_Flag") == 1, "Shared").otherwise("Solo"))
        .withColumn("dataset",         F.lit("fhv"))
        .withColumn("data_source",     F.lit("NYC TLC FHV — January 2025"))
    )


def compute_kpis(df) -> dict:
    log.info("Computing FHV KPIs …")
    return df.agg(
        F.count("*").alias("total_trips"),
        F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        F.countDistinct("dispatching_base_num").alias("unique_bases"),
    ).collect()[0].asDict()


def run(input_path: str, output_dir: str, analytics_dir: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    raw_df   = spark.read.parquet(input_path)
    log.info(f"FHV raw rows: {raw_df.count():,}")

    clean_df = clean(raw_df)
    feat_df  = feature_engineering(clean_df)
    feat_df.cache()

    # Save processed
    out = f"{output_dir}/fhv_processed"
    feat_df.coalesce(4).write.mode("overwrite").parquet(out)

    # Analytics
    dow_map = F.create_map([F.lit(x) for kv in DOW_MAP.items() for x in kv])

    analytics = {
        "fhv_hourly": feat_df.groupBy("hour_of_day").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        ).orderBy("hour_of_day"),

        "fhv_dow": feat_df.groupBy("day_of_week_num").agg(
            F.count("*").alias("trips"),
        ).withColumn("day_name", dow_map[F.col("day_of_week_num")]).orderBy("day_of_week_num"),

        "fhv_top_zones": feat_df.groupBy("pickup_zone").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        ).orderBy(F.desc("trips")).limit(15),

        "fhv_companies": feat_df.groupBy("company").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        ).orderBy(F.desc("trips")),

        "fhv_shared": feat_df.groupBy("shared_ride").agg(
            F.count("*").alias("trips"),
        ).orderBy(F.desc("trips")),
    }

    for name, df in analytics.items():
        path = f"{analytics_dir}/{name}"
        df.coalesce(1).write.mode("overwrite").parquet(path)
        log.info(f"Saved → {path}")

    kpis = compute_kpis(feat_df)
    kpi_path = Path(analytics_dir) / "fhv_kpis.json"
    kpi_path.parent.mkdir(parents=True, exist_ok=True)
    with open(kpi_path, "w") as f:
        json.dump({k: float(v) if isinstance(v, (int, float)) else v for k, v in kpis.items()}, f, indent=2)

    feat_df.unpersist()
    spark.stop()
    log.info("FHV ETL completed ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FHV ETL — PySpark")
    parser.add_argument("--input",     default="data/raw/fhv_tripdata_2025-01.parquet")
    parser.add_argument("--output",    default="data/processed")
    parser.add_argument("--analytics", default="data/analytics")
    args = parser.parse_args()
    run(args.input, args.output, args.analytics)
