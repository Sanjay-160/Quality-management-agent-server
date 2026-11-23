from app.db import engine
from sqlalchemy import text

with engine().connect() as conn:
    for tbl, ts_col in [
        ('fact_quality_inspection', 'inspection_ts'),
        ('fact_product_genealogy_event', 'event_ts'),
        ('fact_ncr_capa', 'opened_ts')
    ]:
        row = conn.execute(text(f"""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE {ts_col}::date >= '2026-11-01' AND {ts_col}::date <= '2026-11-11') AS nov_gap
            FROM {tbl}
        """)).fetchone()
        print(f"{tbl}: total={row[0]}, nov_1_to_11={row[1]}")
