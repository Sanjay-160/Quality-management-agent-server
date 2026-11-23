import sys
import random
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.db import engine

def run():
    print("Connecting to database...", flush=True)
    eng = engine()

    with eng.connect() as conn:
        max_qi = conn.execute(text("SELECT MAX(SUBSTRING(inspection_id FROM 4)::bigint) FROM fact_quality_inspection WHERE inspection_id LIKE 'QI-%'")).scalar() or 20000
        max_gen = conn.execute(text("SELECT MAX(SUBSTRING(genealogy_event_id FROM 5)::bigint) FROM fact_product_genealogy_event WHERE genealogy_event_id LIKE 'GEN-%'")).scalar() or 30000
        max_ncr = conn.execute(text("SELECT MAX(SUBSTRING(ncr_id FROM 5)::bigint) FROM fact_ncr_capa WHERE ncr_id LIKE 'NCR-%'")).scalar() or 1000

    max_qi = int(max_qi)
    max_gen = int(max_gen)
    max_ncr = int(max_ncr)
    print(f"Current Max IDs: max_qi={max_qi}, max_gen={max_gen}, max_ncr={max_ncr}", flush=True)

    plants = ["IN-KA-01", "IN-TN-01"]
    lines = ["FAL-L1", "FAL-L2", "SMT-L1", "SMT-L2"]
    stations = [
        "ST-SMT-010", "ST-SMT-020", "ST-SMT-030", "ST-SMT-060",
        "ST-TST-010", "ST-TST-020", "ST-TST-030", "ST-QA-010"
    ]
    products = ["SPH-A15-128", "SPH-A15-256", "SPH-PRO-256"]
    materials = [
        ("MAT-PCB-004", "SUP-010"),
        ("MAT-DISP-001", "SUP-003"),
        ("MAT-BATT-002", "SUP-007"),
        ("MAT-CAM-003", "SUP-005"),
        ("MAT-COIL-013", "SUP-011"),
        ("MAT-VAPOR-017", "SUP-008")
    ]
    defects = [
        ("D001", "MAJOR", "REWORK"),
        ("D002", "CRITICAL", "REWORK"),
        ("D003", "MAJOR", "REWORK"),
        ("D004", "CRITICAL", "SCRAP"),
        ("D005", "MAJOR", "REWORK"),
        ("D006", "CRITICAL", "SCRAP"),
        ("D007", "MINOR", "HOLD"),
        ("D008", "MAJOR", "REWORK"),
        ("D009", "CRITICAL", "REWORK"),
        ("D010", "MINOR", "REWORK"),
        ("D011", "MINOR", "REWORK"),
        ("D012", "MINOR", "REWORK"),
        ("D013", "MAJOR", "REWORK"),
        ("D014", "CRITICAL", "SCRAP"),
        ("D015", "MINOR", "REWORK"),
        ("D016", "MAJOR", "REWORK"),
        ("D017", "CRITICAL", "REWORK"),
        ("D018", "MINOR", "REWORK"),
        ("D019", "CRITICAL", "SCRAP"),
        ("D020", "CRITICAL", "SCRAP")
    ]
    root_causes = ["MACHINE", "MATERIAL", "METHOD", "MANPOWER", "ENVIRONMENT"]
    containments = ["100_PERCENT_SORT", "LINE_STOP", "QUARANTINE_LOT", "REWORK_INVENTORY"]

    all_inspections = []
    all_genealogy = []
    all_ncrs = []

    # 11 days: 2026-11-01 through 2026-11-11
    # Generate ~85 inspections per day (approx 935 inspections total for high speed and density)
    for day in range(1, 12):
        dt_base = datetime(2026, 11, day)
        date_str = dt_base.strftime("%Y-%m-%d")
        daily_count = 85

        for i in range(daily_count):
            max_qi += 1
            insp_id = f"QI-{max_qi:08d}"
            minute_offset = int((i / daily_count) * 1400) + random.randint(0, 10)
            insp_dt = dt_base + timedelta(minutes=minute_offset)
            ts_str = insp_dt.strftime("%Y-%m-%dT%H:%M:%S")

            serial = f"SN2611{day:02d}{random.randint(100000, 999999)}"
            plant = random.choice(plants)
            line = random.choice(lines)
            station = random.choice(stations)
            prod = random.choice(products)
            po_id = f"PO-{random.randint(160, 310):06d}"
            inspector = f"EMP-{random.randint(20, 190):04d}"

            # ~5.5% failure rate (about 4-6 failures per day)
            is_fail = (random.random() < 0.055)

            if is_fail:
                def_code, severity, disp = random.choice(defects)
                result = "FAIL"
                meas = round(random.uniform(70.0, 93.5), 3)
            else:
                def_code = "NONE"
                severity = "NONE"
                disp = "RELEASE"
                result = "PASS"
                meas = round(random.uniform(96.0, 100.0), 3)

            all_inspections.append({
                "inspection_id": insp_id,
                "inspection_ts": ts_str,
                "plant_id": plant,
                "line_id": line,
                "station_id": station,
                "product_id": prod,
                "serial_number": serial,
                "production_order_id": po_id,
                "inspection_stage": random.choice(["IQC", "SMT", "FAL", "OQC"]),
                "defect_code": def_code,
                "result": result,
                "severity": severity,
                "measurement_value": meas,
                "spec_min": 95.0,
                "spec_max": 100.0,
                "inspector_id": inspector,
                "disposition": disp,
                "spec_revision": "QC-REV-08",
                "source_system": "QMS"
            })

            # 2 genealogy events per unit
            for seq in range(1, 3):
                max_gen += 1
                mat_id, supp_id = random.choice(materials)
                mat_lot = f"LOT-{mat_id.split('-')[-1]}-2611{day:02d}-{random.randint(1, 5)}"
                gen_dt = insp_dt - timedelta(minutes=(3 - seq) * 10)
                all_genealogy.append({
                    "genealogy_event_id": f"GEN-{max_gen:08d}",
                    "event_ts": gen_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "plant_id": plant,
                    "serial_number": serial,
                    "production_order_id": po_id,
                    "product_id": prod,
                    "material_id": mat_id,
                    "material_lot_id": mat_lot,
                    "supplier_id": supp_id,
                    "station_id": station,
                    "operation_sequence": seq * 5,
                    "event_type": "COMPONENT_MOUNT" if seq == 1 else ("INSPECTION" if not is_fail else "REWORK"),
                    "quantity": 1,
                    "parent_serial_number": None,
                    "source_system": "MES",
                    "event_lineage_id": f"LIN-{max_gen:08d}",
                    "genealogy_complete": True
                })

            # NCR record if failure
            if is_fail:
                max_ncr += 1
                ncr_id = f"NCR-{max_ncr:05d}"
                due_dt = insp_dt + timedelta(days=random.randint(7, 14))
                is_closed = (day <= 7)
                all_ncrs.append({
                    "ncr_id": ncr_id,
                    "inspection_id": insp_id,
                    "opened_ts": ts_str,
                    "defect_code": def_code,
                    "root_cause_category": random.choice(root_causes),
                    "containment_action": random.choice(containments),
                    "owner_id": inspector,
                    "capa_due_date": due_dt.strftime("%Y-%m-%d"),
                    "capa_status": "CLOSED" if is_closed else ("IN_PROGRESS" if day <= 9 else "OPEN"),
                    "effectiveness_check": "EFFECTIVE" if is_closed else "PENDING"
                })

    print(f"Generated {len(all_inspections)} inspections, {len(all_genealogy)} genealogy events, {len(all_ncrs)} NCRs.", flush=True)

    df_insp = pd.DataFrame(all_inspections)
    df_gen = pd.DataFrame(all_genealogy)
    df_ncr = pd.DataFrame(all_ncrs)

    print("Inserting fact_quality_inspection via multi-value batch...", flush=True)
    df_insp.to_sql("fact_quality_inspection", eng, if_exists="append", index=False, chunksize=500, method="multi")
    print("  fact_quality_inspection inserted successfully!", flush=True)

    print("Inserting fact_product_genealogy_event via multi-value batch...", flush=True)
    df_gen.to_sql("fact_product_genealogy_event", eng, if_exists="append", index=False, chunksize=500, method="multi")
    print("  fact_product_genealogy_event inserted successfully!", flush=True)

    if not df_ncr.empty:
        print("Inserting fact_ncr_capa via multi-value batch...", flush=True)
        df_ncr.to_sql("fact_ncr_capa", eng, if_exists="append", index=False, chunksize=500, method="multi")
        print("  fact_ncr_capa inserted successfully!", flush=True)

    # Append to CSVs
    data_dir = Path(__file__).resolve().parent / "data"
    insp_csv = data_dir / "fact_quality_inspection.csv"
    if insp_csv.exists():
        df_insp.to_csv(insp_csv, mode='a', header=False, index=False)
        print(f"  Appended {len(df_insp)} rows to {insp_csv.name}", flush=True)

    gen_csv = data_dir / "fact_product_genealogy_event.csv"
    if gen_csv.exists():
        df_gen.to_csv(gen_csv, mode='a', header=False, index=False)
        print(f"  Appended {len(df_gen)} rows to {gen_csv.name}", flush=True)

    ncr_csv = data_dir / "fact_ncr_capa.csv"
    if ncr_csv.exists() and not df_ncr.empty:
        df_ncr.to_csv(ncr_csv, mode='a', header=False, index=False)
        print(f"  Appended {len(df_ncr)} rows to {ncr_csv.name}", flush=True)

    print("ALL TABLES UPDATED WITH 1 NOV - 11 NOV DATA!", flush=True)

if __name__ == "__main__":
    run()
