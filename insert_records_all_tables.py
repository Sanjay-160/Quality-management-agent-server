import sys
import random
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.db import engine, execute_with_retry

def insert_all_tables():
    now = datetime.now(timezone.utc)
    ts_str = now.strftime("%Y-%m-%dT%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")

    print(f"--- Inserting records into EVERY table in Neon DB at {ts_str} ---")
    eng = engine()

    # 1. TABLE: dim_defect_code
    new_defects = [
        {"defect_code": "D013", "defect_name": "Wireless Charging Coil Disconnect", "defect_category": "FUNCTIONAL", "severity": "MAJOR", "disposition_default": "REWORK"},
        {"defect_code": "D014", "defect_name": "OLED Display Delamination", "defect_category": "DISPLAY", "severity": "CRITICAL", "disposition_default": "SCRAP"},
        {"defect_code": "D015", "defect_name": "Haptic Taptic Engine Rattle", "defect_category": "MECHANICAL", "severity": "MINOR", "disposition_default": "REWORK"},
        {"defect_code": "D016", "defect_name": "Under-Display Ultrasonic Sensor Drift", "defect_category": "BIOMETRIC", "severity": "MAJOR", "disposition_default": "REWORK"},
        {"defect_code": "D017", "defect_name": "Vapor Chamber Thermal Paste Void", "defect_category": "THERMAL", "severity": "CRITICAL", "disposition_default": "REWORK"},
        {"defect_code": "D018", "defect_name": "Acoustic Mesh Acoustic Clog", "defect_category": "AUDIO", "severity": "MINOR", "disposition_default": "REWORK"},
        {"defect_code": "D019", "defect_name": "5G mmWave Flex Ribbon Tear", "defect_category": "RF", "severity": "CRITICAL", "disposition_default": "SCRAP"},
        {"defect_code": "D020", "defect_name": "Battery Cell Pressure Micro-Leak", "defect_category": "BATTERY", "severity": "CRITICAL", "disposition_default": "SCRAP"}
    ]

    with eng.connect() as conn:
        # Ensure unique index exists on dim_defect_code(defect_code)
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_dim_defect_code_code ON dim_defect_code (defect_code)"))
        for d in new_defects:
            conn.execute(text("""
                INSERT INTO dim_defect_code (defect_code, defect_name, defect_category, severity, disposition_default)
                VALUES (:defect_code, :defect_name, :defect_category, :severity, :disposition_default)
                ON CONFLICT (defect_code) DO UPDATE
                SET defect_name = EXCLUDED.defect_name,
                    defect_category = EXCLUDED.defect_category,
                    severity = EXCLUDED.severity,
                    disposition_default = EXCLUDED.disposition_default
            """), d)
        conn.commit()
    print(f"1. dim_defect_code: Inserted/Updated {len(new_defects)} defect code records.")

    # 2. Get current max IDs from tables
    with eng.connect() as conn:
        max_qi = conn.execute(text("SELECT MAX(SUBSTRING(inspection_id FROM 4)::bigint) FROM fact_quality_inspection WHERE inspection_id LIKE 'QI-%'")).scalar() or 16000
        max_gen = conn.execute(text("SELECT MAX(SUBSTRING(genealogy_event_id FROM 5)::bigint) FROM fact_product_genealogy_event WHERE genealogy_event_id LIKE 'GEN-%'")).scalar() or 25000
        max_ncr = conn.execute(text("SELECT MAX(SUBSTRING(ncr_id FROM 5)::bigint) FROM fact_ncr_capa WHERE ncr_id LIKE 'NCR-%'")).scalar() or 400

    max_qi = int(max_qi)
    max_gen = int(max_gen)
    max_ncr = int(max_ncr)

    # 3. Generate batch of 20 realistic smartphones for fact_quality_inspection, fact_product_genealogy_event, and fact_ncr_capa
    plants = ["IN-KA-01", "IN-TN-01"]
    lines = ["FAL-L1", "FAL-L2", "SMT-L1", "SMT-L2"]
    stations = ["ST-SMT-010", "ST-SMT-020", "ST-SMT-030", "ST-SMT-060", "ST-TST-010", "ST-TST-020", "ST-TST-030", "ST-QA-010"]
    products = ["SPH-A15-128", "SPH-A15-256", "SPH-PRO-256"]
    materials = [
        ("MAT-PCB-004", "SUP-010"),
        ("MAT-DISP-001", "SUP-003"),
        ("MAT-BATT-002", "SUP-007"),
        ("MAT-CAM-003", "SUP-005"),
        ("MAT-COIL-013", "SUP-011"),
        ("MAT-VAPOR-017", "SUP-008")
    ]
    all_defects = [
        ("D001", "MAJOR", "REWORK"),
        ("D002", "CRITICAL", "REWORK"),
        ("D003", "MAJOR", "REWORK"),
        ("D004", "CRITICAL", "SCRAP"),
        ("D007", "MINOR", "HOLD"),
        ("D008", "MAJOR", "REWORK"),
        ("D012", "MINOR", "REWORK"),
        ("D013", "MAJOR", "REWORK"),
        ("D014", "CRITICAL", "SCRAP"),
        ("D017", "CRITICAL", "REWORK"),
        ("D019", "CRITICAL", "SCRAP"),
    ]
    root_causes = ["MACHINE", "MATERIAL", "METHOD", "MANPOWER", "ENVIRONMENT"]
    containments = ["100_PERCENT_SORT", "LINE_STOP", "QUARANTINE_LOT", "REWORK_INVENTORY"]

    inspections_to_insert = []
    genealogy_to_insert = []
    ncrs_to_insert = []

    count = 20
    for idx in range(count):
        max_qi += 1
        insp_id = f"QI-{max_qi:08d}"
        serial = f"SN{now.strftime('%y%m%d')}{random.randint(100000, 999999)}"
        plant = random.choice(plants)
        line = random.choice(lines)
        station = random.choice(stations)
        prod = random.choice(products)
        po_id = f"PO-{random.randint(100, 350):06d}"
        inspector = f"EMP-{random.randint(20, 190):04d}"

        # 3 out of 20 are failures to provide live intelligence
        is_fail = (idx % 6 == 0)

        if is_fail:
            def_code, severity, disp = random.choice(all_defects)
            result = "FAIL"
            meas = round(random.uniform(72.0, 93.0), 3)
        else:
            def_code = "NONE"
            severity = "NONE"
            disp = "RELEASE"
            result = "PASS"
            meas = round(random.uniform(96.0, 100.0), 3)

        inspections_to_insert.append({
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

        # Insert 2-3 genealogy events per smartphone (component mount, testing, assembly)
        for seq in range(1, 4):
            max_gen += 1
            mat_id, supp_id = random.choice(materials)
            mat_lot = f"LOT-{mat_id.split('-')[-1]}-{now.strftime('%y%m%d')}-{random.randint(1, 4)}"
            genealogy_to_insert.append({
                "genealogy_event_id": f"GEN-{max_gen:08d}",
                "event_ts": ts_str,
                "plant_id": plant,
                "serial_number": serial,
                "production_order_id": po_id,
                "product_id": prod,
                "material_id": mat_id,
                "material_lot_id": mat_lot,
                "supplier_id": supp_id,
                "station_id": station,
                "operation_sequence": seq * 5,
                "event_type": "COMPONENT_MOUNT" if seq == 1 else "FUNCTIONAL_TEST" if seq == 2 else ("INSPECTION" if not is_fail else "REWORK"),
                "quantity": 1,
                "parent_serial_number": None,
                "source_system": "MES",
                "event_lineage_id": f"LIN-{max_gen:08d}",
                "genealogy_complete": True
            })

        # Insert NCR record if failed
        if is_fail:
            max_ncr += 1
            ncr_id = f"NCR-{max_ncr:05d}"
            ncrs_to_insert.append({
                "ncr_id": ncr_id,
                "inspection_id": insp_id,
                "opened_ts": ts_str,
                "defect_code": def_code,
                "root_cause_category": random.choice(root_causes),
                "containment_action": random.choice(containments),
                "owner_id": inspector,
                "capa_due_date": date_str,
                "capa_status": "OPEN",
                "effectiveness_check": "PENDING"
            })

    # Execute batch inserts
    with eng.connect() as conn:
        conn.execute(text("""
            INSERT INTO fact_quality_inspection (
                inspection_id, inspection_ts, plant_id, line_id, station_id,
                product_id, serial_number, production_order_id, inspection_stage,
                defect_code, result, severity, measurement_value, spec_min, spec_max,
                inspector_id, disposition, spec_revision, source_system
            ) VALUES (
                :inspection_id, :inspection_ts, :plant_id, :line_id, :station_id,
                :product_id, :serial_number, :production_order_id, :inspection_stage,
                :defect_code, :result, :severity, :measurement_value, :spec_min, :spec_max,
                :inspector_id, :disposition, :spec_revision, :source_system
            )
        """), inspections_to_insert)

        conn.execute(text("""
            INSERT INTO fact_product_genealogy_event (
                genealogy_event_id, event_ts, plant_id, serial_number, production_order_id,
                product_id, material_id, material_lot_id, supplier_id, station_id,
                operation_sequence, event_type, quantity, parent_serial_number,
                source_system, event_lineage_id, genealogy_complete
            ) VALUES (
                :genealogy_event_id, :event_ts, :plant_id, :serial_number, :production_order_id,
                :product_id, :material_id, :material_lot_id, :supplier_id, :station_id,
                :operation_sequence, :event_type, :quantity, :parent_serial_number,
                :source_system, :event_lineage_id, :genealogy_complete
            )
        """), genealogy_to_insert)

        conn.execute(text("""
            INSERT INTO fact_ncr_capa (
                ncr_id, inspection_id, opened_ts, defect_code,
                root_cause_category, containment_action, owner_id,
                capa_due_date, capa_status, effectiveness_check
            ) VALUES (
                :ncr_id, :inspection_id, :opened_ts, :defect_code,
                :root_cause_category, :containment_action, :owner_id,
                :capa_due_date, :capa_status, :effectiveness_check
            )
        """), ncrs_to_insert)

        conn.commit()

    print(f"2. fact_quality_inspection: Inserted {len(inspections_to_insert)} inspection records.")
    print(f"3. fact_product_genealogy_event: Inserted {len(genealogy_to_insert)} genealogy event records.")
    print(f"4. fact_ncr_capa: Inserted {len(ncrs_to_insert)} non-conformance records.")

    # Verification: check row counts in EVERY table
    print("\n--- Current Row Counts in EVERY Neon Table ---")
    tables = ["dim_defect_code", "fact_quality_inspection", "fact_product_genealogy_event", "fact_ncr_capa"]
    with eng.connect() as conn:
        for t in tables:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t}: {cnt:,} records")

if __name__ == "__main__":
    insert_all_tables()
