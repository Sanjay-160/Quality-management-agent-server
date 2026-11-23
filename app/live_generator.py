import time
import random
import threading
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from .db import engine, execute_with_retry

logger = logging.getLogger("qcore.live")

PLANTS = ["IN-KA-01", "IN-TN-01"]
LINES = ["FAL-L1", "FAL-L2", "SMT-L1", "SMT-L2"]
STATIONS = [
    "ST-QA-010", "ST-SMT-010", "ST-SMT-020", "ST-SMT-030",
    "ST-SMT-040", "ST-SMT-050", "ST-SMT-060", "ST-SMT-070",
    "ST-SMT-080", "ST-TST-010", "ST-TST-020", "ST-TST-030",
    "ST-TST-040", "ST-TST-050"
]
PRODUCTS = ["SPH-A15-128", "SPH-A15-256", "SPH-PRO-256"]
DEFECTS = [
    ("D001", "Solder Bridge", "SMT", "MAJOR", "REWORK"),
    ("D002", "Missing Component", "SMT", "CRITICAL", "REWORK"),
    ("D003", "Tombstoning", "SMT", "MAJOR", "REWORK"),
    ("D004", "Display Dead Pixel", "DISPLAY", "CRITICAL", "SCRAP"),
    ("D005", "Camera Blur", "CAMERA", "MAJOR", "REWORK"),
    ("D006", "Battery Swell", "FUNCTIONAL", "CRITICAL", "SCRAP"),
    ("D007", "Cosmetic Scratch", "COSMETIC", "MINOR", "HOLD"),
    ("D008", "USB-C Charging Failure", "FUNCTIONAL", "MAJOR", "REWORK"),
    ("D009", "RF Sensitivity Failure", "RF", "CRITICAL", "REWORK"),
    ("D010", "Speaker Distortion", "AUDIO", "MINOR", "REWORK"),
    ("D011", "Button Stickiness", "MECHANICAL", "MINOR", "REWORK"),
    ("D012", "Back Cover Gap", "ASSEMBLY", "MINOR", "REWORK"),
    ("D013", "Wireless Charging Coil Disconnect", "FUNCTIONAL", "MAJOR", "REWORK"),
    ("D014", "OLED Display Delamination", "DISPLAY", "CRITICAL", "SCRAP"),
    ("D015", "Haptic Taptic Engine Rattle", "MECHANICAL", "MINOR", "REWORK"),
    ("D016", "Under-Display Ultrasonic Sensor Drift", "BIOMETRIC", "MAJOR", "REWORK"),
    ("D017", "Vapor Chamber Thermal Paste Void", "THERMAL", "CRITICAL", "REWORK"),
    ("D018", "Acoustic Mesh Acoustic Clog", "AUDIO", "MINOR", "REWORK"),
    ("D019", "5G mmWave Flex Ribbon Tear", "RF", "CRITICAL", "SCRAP"),
    ("D020", "Battery Cell Pressure Micro-Leak", "BATTERY", "CRITICAL", "SCRAP"),
]
MATERIALS = [
    ("MAT-PCB-004", "SUP-010"),
    ("MAT-DISP-001", "SUP-003"),
    ("MAT-BATT-002", "SUP-007"),
    ("MAT-CAM-003", "SUP-005"),
    ("MAT-ADH-018", "SUP-009"),
]
ROOT_CAUSES = ["MACHINE", "MATERIAL", "METHOD", "MANPOWER", "ENVIRONMENT"]
CONTAINMENTS = ["100_PERCENT_SORT", "LINE_STOP", "QUARANTINE_LOT", "REWORK_INVENTORY"]
INSPECTORS = [f"EMP-{i:04d}" for i in range(10, 200)]

class LiveDataStreamer:
    def __init__(self):
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.interval_seconds = 60
        self.tick_count = 0
        self.last_tick_time = None
        self.total_dim_defect_updates = 0
        self.total_inspections = 0
        self.total_genealogy = 0
        self.total_ncrs = 0
        self.recent_events = []
        self._max_recent = 25

    def start(self):
        with self.lock:
            if not self.running:
                self.running = True
                self.thread = threading.Thread(target=self._run_loop, daemon=True, name="neon-live-streamer")
                self.thread.start()
                logger.info("Real-time Live Data Streamer started (60s tick interval with dynamic auto-catchup).")

    def stop(self):
        with self.lock:
            self.running = False

    def get_status(self):
        with self.lock:
            return {
                "active": self.running,
                "interval_seconds": self.interval_seconds,
                "tick_count": self.tick_count,
                "last_tick_time": self.last_tick_time,
                "total_dim_defect_updates": self.total_dim_defect_updates,
                "total_inspections_streamed": self.total_inspections,
                "total_genealogy_streamed": self.total_genealogy,
                "total_ncrs_streamed": self.total_ncrs,
                "all_tables_updated_live": True,
                "tables": ["dim_defect_code", "fact_quality_inspection", "fact_product_genealogy_event", "fact_ncr_capa"],
                "recent_events": self.recent_events[:15],
            }

    def _run_loop(self):
        # Give backend 3 seconds to complete initial database pool handshake
        time.sleep(3)
        # Ensure telemetry is caught up to current date & time (today, tomorrow, or future)
        try:
            self.catchup_and_seed_to_now()
        except Exception as exc:
            logger.error(f"Live catchup error: {exc}")

        while self.running:
            try:
                self.execute_tick()
            except Exception as exc:
                logger.error(f"Live data generator tick error: {exc}")

            # Sleep for interval (1 minute)
            for _ in range(self.interval_seconds):
                if not self.running:
                    break
                time.sleep(1)

    def catchup_and_seed_to_now(self):
        """
        Dynamically synchronizes Neon DB so that telemetry always covers current date & time.
        If opened today, tomorrow, or in the future, it backfills missing hourly production
        so the dashboard instantly reflects active manufacturing activity up to the current minute.
        """
        now = datetime.now()
        eng = engine()
        with eng.connect() as conn:
            max_ts_str = conn.execute(text("SELECT MAX(inspection_ts) FROM fact_quality_inspection")).scalar()

        if not max_ts_str:
            return

        try:
            clean_ts = str(max_ts_str).replace('Z', '').split('+')[0]
            if 'T' in clean_ts:
                max_ts = datetime.fromisoformat(clean_ts)
            else:
                max_ts = datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            max_ts = now - timedelta(hours=2)

        # Check if the date has changed (e.g. tomorrow or gap > 20 mins)
        if max_ts.date() < now.date():
            # New production day! Start from 06:00 AM of today (Shift A kickoff)
            start_cursor = datetime(now.year, now.month, now.day, 6, 0, 0)
        elif now - max_ts > timedelta(minutes=20):
            # Same day but missed several minutes or hours
            start_cursor = max_ts + timedelta(minutes=5)
        else:
            return

        if start_cursor < now:
            logger.info(f"Auto-catchup initiated: Synchronizing production telemetry from {start_cursor} to {now}...")
            curr = start_cursor
            batches_created = 0
            while curr < now and batches_created < 50:
                self._insert_batch_at(curr, batch_size=random.randint(6, 12), force_fail=(batches_created % 4 == 0))
                curr += timedelta(minutes=random.randint(10, 20))
                batches_created += 1
            logger.info(f"Auto-catchup complete: Seeded {batches_created} baseline intervals up to {now}.")

    def _insert_batch_at(self, dt: datetime, batch_size: int = 6, force_fail: bool = False):
        """Generates and writes a batch of records at a specified timestamp."""
        ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
        date_str = dt.strftime("%Y-%m-%d")

        new_inspections = []
        new_genealogy = []
        new_ncrs = []

        eng = engine()
        with eng.connect() as conn:
            max_qi_res = conn.execute(text("SELECT MAX(SUBSTRING(inspection_id FROM 4)::bigint) FROM fact_quality_inspection WHERE inspection_id LIKE 'QI-%'")).scalar()
            max_qi = int(max_qi_res or 16000)

            max_gen_res = conn.execute(text("SELECT MAX(SUBSTRING(genealogy_event_id FROM 5)::bigint) FROM fact_product_genealogy_event WHERE genealogy_event_id LIKE 'GEN-%'")).scalar()
            max_gen = int(max_gen_res or 25000)

            max_ncr_res = conn.execute(text("SELECT MAX(SUBSTRING(ncr_id FROM 5)::bigint) FROM fact_ncr_capa WHERE ncr_id LIKE 'NCR-%'")).scalar()
            max_ncr = int(max_ncr_res or 400)

            for i in range(batch_size):
                max_qi += 1
                insp_id = f"QI-{max_qi:08d}"
                serial = f"SN{dt.strftime('%y%m%d')}{random.randint(100000, 999999)}"
                plant = random.choice(PLANTS)
                line = random.choice(LINES)
                station = random.choice(STATIONS)
                product = random.choice(PRODUCTS)
                po_id = f"PO-{random.randint(100, 350):06d}"
                stage = random.choice(["IQC", "SMT", "FAL", "OQC"])
                inspector = random.choice(INSPECTORS)

                is_fail = (force_fail and i == 0) or (random.random() < 0.08)
                if is_fail:
                    def_code, def_name, def_cat, severity, default_disp = random.choice(DEFECTS)
                    result = "FAIL"
                    disposition = default_disp
                    measurement = round(random.uniform(70.0, 93.0), 3)
                else:
                    def_code = "NONE"
                    severity = "NONE"
                    result = "PASS"
                    disposition = "RELEASE"
                    measurement = round(random.uniform(96.0, 100.0), 3)

                new_inspections.append({
                    "inspection_id": insp_id,
                    "inspection_ts": ts_str,
                    "plant_id": plant,
                    "line_id": line,
                    "station_id": station,
                    "product_id": product,
                    "serial_number": serial,
                    "production_order_id": po_id,
                    "inspection_stage": stage,
                    "defect_code": def_code,
                    "result": result,
                    "severity": severity,
                    "measurement_value": measurement,
                    "spec_min": 95.0,
                    "spec_max": 100.0,
                    "inspector_id": inspector,
                    "disposition": disposition,
                    "spec_revision": "QC-REV-08",
                    "source_system": "QMS",
                })

                mat_id, supp_id = random.choice(MATERIALS)
                mat_lot = f"LOT-{mat_id.split('-')[-1]}-{dt.strftime('%y%m%d')}-{random.randint(1, 4)}"
                max_gen += 1
                gen_event_type = "INSPECTION" if not is_fail else ("SCRAP" if disposition == "SCRAP" else ("HOLD" if disposition == "HOLD" else "REWORK"))
                new_genealogy.append({
                    "genealogy_event_id": f"GEN-{max_gen:08d}",
                    "event_ts": ts_str,
                    "plant_id": plant,
                    "serial_number": serial,
                    "production_order_id": po_id,
                    "product_id": product,
                    "material_id": mat_id,
                    "material_lot_id": mat_lot,
                    "supplier_id": supp_id,
                    "station_id": station,
                    "operation_sequence": random.randint(1, 18),
                    "event_type": gen_event_type,
                    "quantity": 1,
                    "parent_serial_number": None,
                    "source_system": "MES",
                    "event_lineage_id": f"LIN-{max_gen:08d}",
                    "genealogy_complete": True,
                })

                if is_fail:
                    max_ncr += 1
                    ncr_id = f"NCR-{max_ncr:05d}"
                    new_ncrs.append({
                        "ncr_id": ncr_id,
                        "inspection_id": insp_id,
                        "opened_ts": ts_str,
                        "defect_code": def_code,
                        "root_cause_category": random.choice(ROOT_CAUSES),
                        "containment_action": random.choice(CONTAINMENTS),
                        "owner_id": inspector,
                        "capa_due_date": date_str,
                        "capa_status": "OPEN",
                        "effectiveness_check": "PENDING",
                    })

            # Ensure at least 1 inspection in batch is a non-conformance so fact_ncr_capa gets record every tick
            if not new_ncrs and new_inspections and force_fail:
                insp_target = new_inspections[-1]
                def_code, def_name, def_cat, severity, default_disp = random.choice(DEFECTS)
                insp_target["result"] = "FAIL"
                insp_target["defect_code"] = def_code
                insp_target["severity"] = severity
                insp_target["disposition"] = default_disp
                insp_target["measurement_value"] = round(random.uniform(70.0, 93.0), 3)

                max_ncr += 1
                ncr_id = f"NCR-{max_ncr:05d}"
                new_ncrs.append({
                    "ncr_id": ncr_id,
                    "inspection_id": insp_target["inspection_id"],
                    "opened_ts": ts_str,
                    "defect_code": def_code,
                    "root_cause_category": random.choice(ROOT_CAUSES),
                    "containment_action": random.choice(CONTAINMENTS),
                    "owner_id": insp_target["inspector_id"],
                    "capa_due_date": date_str,
                    "capa_status": "OPEN",
                    "effectiveness_check": "PENDING",
                })

            # 1. dim_defect_code
            dim_defect = random.choice(DEFECTS)
            conn.execute(
                text("""
                INSERT INTO dim_defect_code (defect_code, defect_name, defect_category, severity, disposition_default)
                VALUES (:code, :name, :cat, :sev, :disp)
                ON CONFLICT (defect_code) DO UPDATE
                SET defect_name = EXCLUDED.defect_name,
                    defect_category = EXCLUDED.defect_category,
                    severity = EXCLUDED.severity,
                    disposition_default = EXCLUDED.disposition_default
                """),
                {
                    "code": dim_defect[0],
                    "name": dim_defect[1],
                    "cat": dim_defect[2],
                    "sev": dim_defect[3],
                    "disp": dim_defect[4]
                }
            )

            # 2. fact_quality_inspection
            if new_inspections:
                conn.execute(
                    text("""
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
                    """),
                    new_inspections
                )

            # 3. fact_product_genealogy_event
            if new_genealogy:
                conn.execute(
                    text("""
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
                    """),
                    new_genealogy
                )

            # 4. fact_ncr_capa
            if new_ncrs:
                conn.execute(
                    text("""
                    INSERT INTO fact_ncr_capa (
                        ncr_id, inspection_id, opened_ts, defect_code,
                        root_cause_category, containment_action, owner_id,
                        capa_due_date, capa_status, effectiveness_check
                    ) VALUES (
                        :ncr_id, :inspection_id, :opened_ts, :defect_code,
                        :root_cause_category, :containment_action, :owner_id,
                        :capa_due_date, :capa_status, :effectiveness_check
                    )
                    """),
                    new_ncrs
                )

            conn.commit()

        return new_inspections, new_genealogy, new_ncrs

    def execute_tick(self):
        """Generates and writes a live batch of smartphone manufacturing events into Neon DB for the current minute."""
        now = datetime.now()
        ts_str = now.strftime("%Y-%m-%dT%H:%M:%S")

        must_fail = (self.tick_count % 3 == 0)
        batch_size = random.randint(4, 8)
        new_inspections, new_genealogy, new_ncrs = self._insert_batch_at(now, batch_size=batch_size, force_fail=must_fail)

        with self.lock:
            self.tick_count += 1
            self.last_tick_time = ts_str
            self.total_dim_defect_updates += 1
            self.total_inspections += len(new_inspections)
            self.total_genealogy += len(new_genealogy)
            self.total_ncrs += len(new_ncrs)

            for insp in new_inspections:
                self.recent_events.insert(0, {
                    "time": ts_str.split("T")[1],
                    "serial": insp["serial_number"],
                    "line": insp["line_id"],
                    "station": insp["station_id"],
                    "product": insp["product_id"],
                    "result": insp["result"],
                    "defect": insp["defect_code"],
                })
            self.recent_events = self.recent_events[:self._max_recent]

        logger.info(f"Live tick #{self.tick_count}: Streamed {len(new_inspections)} inspections, {len(new_genealogy)} genealogy events, {len(new_ncrs)} NCRs at {ts_str} into Neon DB.")
        return {
            "tick": self.tick_count,
            "timestamp": ts_str,
            "inspections": len(new_inspections),
            "genealogy": len(new_genealogy),
            "ncrs": len(new_ncrs)
        }

# Global singleton
streamer = LiveDataStreamer()

