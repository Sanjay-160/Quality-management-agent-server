from pathlib import Path
import pandas as pd
from .db import engine

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FILES = {
    "fact_quality_inspection": "fact_quality_inspection.csv",
    "fact_ncr_capa": "fact_ncr_capa.csv",
    "dim_defect_code": "dim_defect_code.csv",
    "fact_product_genealogy_event": "fact_product_genealogy_event.csv",
}

def load_datasets():
    eng = engine(); summary = {}
    for table, filename in FILES.items():
        path = DATA_DIR / filename
        if not path.exists(): raise FileNotFoundError(f"Missing bundled dataset: {filename}")
        df = pd.read_csv(path)
        # Keep original column names and values; let pandas infer compatible SQL types.
        df.to_sql(table, eng, if_exists="replace", index=False, chunksize=2000, method="multi")
        summary[table] = len(df)
    return summary
