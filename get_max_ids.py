from app.db import engine
from sqlalchemy import text

with engine().connect() as conn:
    max_qi = conn.execute(text("SELECT MAX(SUBSTRING(inspection_id FROM 4)::bigint) FROM fact_quality_inspection WHERE inspection_id LIKE 'QI-%'")).scalar() or 0
    max_gen = conn.execute(text("SELECT MAX(SUBSTRING(genealogy_event_id FROM 5)::bigint) FROM fact_product_genealogy_event WHERE genealogy_event_id LIKE 'GEN-%'")).scalar() or 0
    max_ncr = conn.execute(text("SELECT MAX(SUBSTRING(ncr_id FROM 5)::bigint) FROM fact_ncr_capa WHERE ncr_id LIKE 'NCR-%'")).scalar() or 0
    print(f"max_qi={max_qi}, max_gen={max_gen}, max_ncr={max_ncr}")
