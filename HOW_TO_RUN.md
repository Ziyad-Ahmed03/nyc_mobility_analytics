# 🚀 NYC Mobility Analytics — How To Run (Complete Guide)

## ✅ This version is FIXED — Airflow + Spark both work and display in the UI

---

## STEP 1 — Make sure Docker Desktop is running

Open Docker Desktop and wait until the whale icon 🐳 in your taskbar is steady (not loading).

---

## STEP 2 — Open PowerShell in the project folder

1. Open the `nyc_mobility` folder
2. Right-click on empty space inside the folder
3. Choose **"Open in Terminal"**

---

## STEP 3 — Run these commands ONE BY ONE

### Command 1 — Stop everything and clean up
```powershell
docker compose down -v
```

### Command 2 — Clean old images
```powershell
docker system prune -f
```

### Command 3 — Build and start (takes 10-15 minutes first time)
```powershell
docker compose up -d --build
```

⏳ **Be patient** — the first build downloads Java + Spark inside Airflow. This is normal and only happens once.

---

## STEP 4 — Check everything is running

```powershell
docker compose ps
```

You should see all these as "Up" / "running":
```
nyc_postgres            running (healthy)
nyc_airflow_init        exited (0)      ← this is NORMAL, init runs once
nyc_airflow_scheduler   running
nyc_airflow_webserver   running
nyc_spark_master        running (healthy)
nyc_spark_worker        running
nyc_dashboard           running
```

---

## STEP 5 — Open the interfaces in your browser

| Service | URL | Login |
|---------|-----|-------|
| 🟡 **Dashboard** | http://localhost:8501 | — |
| 🔄 **Airflow** | http://localhost:8080 | admin / admin |
| ⚡ **Spark Master** | http://localhost:8090 | — |

---

## STEP 6 — Run the pipeline in Airflow

1. Open http://localhost:8080
2. Login: **admin** / **admin**
3. Find the DAG: **nyc_mobility_analytics**
4. Toggle it **ON** (switch on the left)
5. Click the **▶️ Play button** → **Trigger DAG**
6. Watch the tasks turn green one by one:

```
✅ start
✅ validate_input_files
✅ spark_yellow_taxi_etl
✅ spark_green_taxi_etl
✅ spark_fhv_etl
✅ spark_citibike_etl
✅ run_duckdb_analytics
✅ load_kpis_to_postgres
✅ pipeline_complete
```

---

## STEP 7 — See Spark working

While the DAG runs, open http://localhost:8090 — you'll see the **Spark Master UI** with your worker connected and jobs running.

---

## 🆘 TROUBLESHOOTING

### Problem: "docker-compose: command not found"
**Solution:** Use `docker compose` (with a SPACE, not a dash)

### Problem: Build is very slow / fails downloading Spark
**Solution:** Your internet may be slow. Wait longer, or run:
```powershell
docker compose up -d --build --no-cache
```

### Problem: Port already in use
**Solution:** Stop other programs using those ports, or run:
```powershell
docker compose down
docker compose up -d
```

### Problem: Airflow shows "DAG not found"
**Solution:** Wait 1-2 minutes for Airflow to scan the DAGs folder, then refresh.

### Problem: Spark task fails in Airflow
**Solution:** Check the data files are in `data/raw/`:
```powershell
dir data\raw
```
You should see 6 files (3 parquet + 3 csv).

---

## 📋 PRESENTATION ORDER (for your defense)

| # | Program | What to say |
|---|---------|-------------|
| 1 | VS Code | "Here's my PySpark ETL code that cleans the data" |
| 2 | PowerShell | "I start the production environment with docker compose" |
| 3 | Docker Desktop | "All 7 services are containerized and running" |
| 4 | Airflow UI | "This is my orchestration DAG — it runs the Spark jobs in order" |
| 5 | Spark Master UI | "Here you can see Spark processing the 6.87M trips" |
| 6 | Dashboard | "And this is the final result — interactive analytics" |

---

## 🛑 To stop everything
```powershell
docker compose down
```

## 🔄 To start again (after first build, fast)
```powershell
docker compose up -d
```
