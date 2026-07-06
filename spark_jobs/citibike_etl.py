"""
NYC Mobility Analytics — CitiBike ETL Job
==========================================
PySpark job to:
  1. Read 3 CitiBike CSV files
  2. Merge and clean
  3. Feature-engineer (duration, hour, DOW, haversine distance)
  4. Convert to Parquet
  5. Compute analytics

Usage:
    spark-submit spark_jobs/citibike_etl.py \
        --input_dir data/raw \
        --output    data/processed \
        --analytics data/analytics
"""

import argparse
import json
import logging
import sys
import math
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, TimestampType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("citibike_etl")

DOW_MAP = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday",5:"Saturday",6:"Sunday"}


def build_spark(app_name="CitiBikeETL"):
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "4g")
        .getOrCreate()
    )


def haversine_udf():
    """Register a UDF to compute haversine distance in km between two lat/lon pairs."""
    def haversine(lat1, lon1, lat2, lon2):
        if None in (lat1, lon1, lat2, lon2):
            return None
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.asin(min(1, math.sqrt(a)))
    return F.udf(haversine, DoubleType())


def load_csvs(spark: SparkSession, input_dir: str):
    """Load all 3 CitiBike CSV files and union them."""
    log.info(f"Loading CitiBike CSVs from: {input_dir}")
    files = [
        f"{input_dir}/202501-citibike-tripdata_1.csv",
        f"{input_dir}/202501-citibike-tripdata_2.csv",
        f"{input_dir}/202501-citibike-tripdata_3.csv",
    ]
    dfs = []
    for path in files:
        if Path(path).exists():
            df = spark.read.option("header", "true").option("inferSchema", "true").csv(path)
            log.info(f"Loaded {path}: {df.count():,} rows")
            dfs.append(df)
    if not dfs:
        raise FileNotFoundError(f"No CitiBike CSV files found in {input_dir}")
    combined = dfs[0]
    for df in dfs[1:]:
        combined = combined.unionByName(df, allowMissingColumns=True)
    log.info(f"Combined CitiBike rows: {combined.count():,}")
    return combined


def clean(df):
    """Clean CitiBike trips."""
    log.info("Cleaning CitiBike data …")

    df = df.withColumn("started_at_ts", F.to_timestamp("started_at"))
    df = df.withColumn("ended_at_ts",   F.to_timestamp("ended_at"))

    df = df.withColumn(
        "duration_min",
        (F.unix_timestamp("ended_at_ts") - F.unix_timestamp("started_at_ts")) / 60.0
    )

    df = df.filter(
        (F.col("duration_min").between(1, 180)) &
        (F.year("started_at_ts") == 2025) &
        (F.month("started_at_ts") == 1) &
        F.col("start_station_name").isNotNull() &
        F.col("end_station_name").isNotNull() &
        F.col("start_lat").isNotNull() &
        F.col("start_lng").isNotNull() &
        F.col("end_lat").isNotNull() &
        F.col("end_lng").isNotNull()
    )

    log.info(f"After cleaning: {df.count():,} rows")
    return df


def feature_engineering(df, spark):
    """Compute derived features for CitiBike trips."""
    log.info("Feature engineering for CitiBike …")

    havfn = haversine_udf()

    df = (
        df
        .withColumn("hour_of_day",    F.hour("started_at_ts"))
        .withColumn("day_of_month",    F.dayofmonth("started_at_ts"))
        .withColumn("day_of_week_num", ((F.dayofweek("started_at_ts") + 5) % 7))  # 0=Mon, 6=Sun
        .withColumn("week_of_year",    F.weekofyear("started_at_ts"))
        .withColumn("is_weekend",      F.when(F.dayofweek("started_at_ts").isin([1, 7]), 1).otherwise(0))
        .withColumn("is_member",       F.when(F.col("member_casual") == "member", 1).otherwise(0))
        .withColumn("is_electric",     F.when(F.col("rideable_type") == "electric_bike", 1).otherwise(0))
        .withColumn("distance_km",     havfn(
            F.col("start_lat").cast(DoubleType()),
            F.col("start_lng").cast(DoubleType()),
            F.col("end_lat").cast(DoubleType()),
            F.col("end_lng").cast(DoubleType()),
        ))
        .withColumn("speed_kmh",       F.when(
            F.col("duration_min") > 0,
            (F.col("distance_km") / (F.col("duration_min") / 60.0))
        ).otherwise(None))
        .withColumn("dataset",         F.lit("citibike"))
        .withColumn("data_source",     F.lit("Citi Bike — January 2025"))
    )

    return df


def compute_kpis(df) -> dict:
    log.info("Computing CitiBike KPIs …")
    return df.agg(
        F.count("*").alias("total_trips"),
        F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        F.round(F.avg("distance_km"), 3).alias("avg_distance_km"),
        F.sum(F.col("is_member")).alias("member_trips"),
        F.sum(F.when(F.col("is_member") == 0, 1).otherwise(0)).alias("casual_trips"),
        F.sum(F.col("is_electric")).alias("electric_trips"),
        F.sum(F.when(F.col("is_electric") == 0, 1).otherwise(0)).alias("classic_trips"),
    ).collect()[0].asDict()


def run(input_dir: str, output_dir: str, analytics_dir: str):
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    raw_df  = load_csvs(spark, input_dir)
    clean_df = clean(raw_df)
    feat_df  = feature_engineering(clean_df, spark)
    feat_df.cache()

    # Save as Parquet
    out = f"{output_dir}/citibike_processed"
    feat_df.coalesce(8).write.mode("overwrite").parquet(out)
    log.info(f"Saved processed → {out}")

    # Analytics
    dow_map = F.create_map([F.lit(x) for kv in DOW_MAP.items() for x in kv])

    analytics = {
        "citibike_hourly": feat_df.groupBy("hour_of_day").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
            F.round(F.avg("distance_km"), 3).alias("avg_distance_km"),
        ).orderBy("hour_of_day"),

        "citibike_dow": feat_df.groupBy("day_of_week_num").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
        ).withColumn("day_name", dow_map[F.col("day_of_week_num")]).orderBy("day_of_week_num"),

        "citibike_daily": feat_df.groupBy("day_of_month").agg(
            F.count("*").alias("trips"),
        ).orderBy("day_of_month"),

        "citibike_top_start_stations": feat_df.groupBy("start_station_name").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
            F.round(F.avg("distance_km"), 3).alias("avg_distance_km"),
        ).orderBy(F.desc("trips")).limit(20),

        "citibike_top_end_stations": feat_df.groupBy("end_station_name").agg(
            F.count("*").alias("trips"),
        ).orderBy(F.desc("trips")).limit(20),

        "citibike_user_type": feat_df.groupBy("member_casual").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
            F.round(F.avg("distance_km"), 3).alias("avg_distance_km"),
        ).orderBy(F.desc("trips")),

        "citibike_bike_type": feat_df.groupBy("rideable_type").agg(
            F.count("*").alias("trips"),
            F.round(F.avg("duration_min"), 2).alias("avg_duration"),
            F.round(F.avg("distance_km"), 3).alias("avg_distance_km"),
        ).orderBy(F.desc("trips")),

        "citibike_duration_dist": feat_df.groupBy(
            F.floor(F.col("duration_min") / 5).cast("integer").alias("duration_bucket_5min")
        ).agg(F.count("*").alias("trips")).orderBy("duration_bucket_5min").limit(40),
    }

    for name, df in analytics.items():
        path = f"{analytics_dir}/{name}"
        df.coalesce(1).write.mode("overwrite").parquet(path)
        log.info(f"Saved → {path}")

    kpis = compute_kpis(feat_df)
    kpi_path = Path(analytics_dir) / "citibike_kpis.json"
    kpi_path.parent.mkdir(parents=True, exist_ok=True)
    with open(kpi_path, "w") as f:
        json.dump({k: float(v) if isinstance(v, (int, float)) else v for k, v in kpis.items()}, f, indent=2)

    feat_df.unpersist()
    spark.stop()
    log.info("CitiBike ETL completed ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CitiBike ETL — PySpark")
    parser.add_argument("--input_dir", default="data/raw")
    parser.add_argument("--output",    default="data/processed")
    parser.add_argument("--analytics", default="data/analytics")
    args = parser.parse_args()
    run(args.input_dir, args.output, args.analytics)
