import os
import sys

# Ensure we can import db_utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db_utils import get_engine
import pandas as pd

def export_data():
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static_data")
    os.makedirs(output_dir, exist_ok=True)
    
    queries = {
        "analytics_kpis.csv": "SELECT * FROM analytics_kpis ORDER BY dataset, metric_name",
        "top_pickup_zones.csv": "SELECT * FROM top_pickup_zones ORDER BY trips DESC",
        "hourly_analytics.csv": "SELECT * FROM hourly_analytics ORDER BY dataset, hour_of_day"
    }

    try:
        engine = get_engine()
        print("Connected to database successfully.")
        with engine.connect() as conn:
            for filename, sql in queries.items():
                print(f"Exporting {filename}...")
                df = pd.read_sql(sql, conn)
                output_path = os.path.join(output_dir, filename)
                df.to_csv(output_path, index=False)
                print(f"Saved {len(df)} rows to {output_path}")
        print("Data export complete!")
    except Exception as e:
        print(f"Error during export: {e}")

if __name__ == "__main__":
    export_data()
