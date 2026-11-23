import sys
from pathlib import Path
from sqlalchemy import text
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.db import engine

with engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT inspection_ts::date AS dt, COUNT(*) as cnt, COUNT(*) FILTER (WHERE UPPER(result)='FAIL') as fail_cnt
        FROM fact_quality_inspection
        WHERE inspection_ts >= '2026-10-20'
        GROUP BY inspection_ts::date
        ORDER BY dt ASC
    """)).fetchall()
    print("Inspection dates found:")
    for r in rows:
        print(f"  {r[0]}: {r[1]} inspections ({r[2]} failed)")

    min_max = conn.execute(text("""
        SELECT MIN(inspection_ts), MAX(inspection_ts), COUNT(*) FROM fact_quality_inspection
    """)).fetchone()
    print(f"Total range: {min_max[0]} to {min_max[1]} (Total: {min_max[2]})")
