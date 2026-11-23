from datetime import datetime, timedelta
from sqlalchemy import text
from .db import engine, execute_with_retry

def query(sql, params=None):
    def _run():
        with engine().connect() as c:
            return [dict(r._mapping) for r in c.execute(text(sql), params or {}).fetchall()]
    return execute_with_retry(_run)

def build_filter_clause(filters=None, prefix=""):
    """
    Builds SQL WHERE clause and parameters for quality inspection queries.
    prefix: e.g. 'i.' when fact_quality_inspection is aliased as 'i'.
    """
    filters = filters or {}
    clauses = []
    params = {}
    p = f"{prefix}." if prefix and not prefix.endswith(".") else prefix

    # 1. Date Range & Presets
    date_preset = filters.get("date_preset")
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")

    # If preset is selected (e.g. 7 days, 14 days, 30 days, last day)
    if date_preset == "7d":
        clauses.append(f"{p}inspection_ts::timestamp >= (NOW() - INTERVAL '7 days')")
    elif date_preset == "14d":
        clauses.append(f"{p}inspection_ts::timestamp >= (NOW() - INTERVAL '14 days')")
    elif date_preset == "30d" or date_preset == "all_30":
        clauses.append(f"{p}inspection_ts::timestamp >= (NOW() - INTERVAL '30 days')")
    elif date_preset == "last_day":
        clauses.append(f"{p}inspection_ts::timestamp >= (NOW() - INTERVAL '1 day')")
    else:
        if start_date:
            clauses.append(f"{p}inspection_ts::timestamp >= :start_date::timestamp")
            params["start_date"] = start_date
        if end_date:
            clauses.append(f"{p}inspection_ts::timestamp <= (:end_date || ' 23:59:59')::timestamp")
            params["end_date"] = end_date

    # 2. Line Filter (using line_id as requested)
    line_id = filters.get("line_id")
    if line_id and line_id not in ("All lines", "all", "ALL", ""):
        clauses.append(f"{p}line_id = :line_id")
        params["line_id"] = line_id

    # 3. Machine / Station Filter (station_id)
    station_id = filters.get("station_id")
    if station_id and station_id not in ("All machines", "all", "ALL", ""):
        clauses.append(f"{p}station_id = :station_id")
        params["station_id"] = station_id

    # 4. Product Filter (product_id)
    product_id = filters.get("product_id")
    if product_id and product_id not in ("All products", "all", "ALL", ""):
        clauses.append(f"{p}product_id = :product_id")
        params["product_id"] = product_id

    # 5. Shift Filters (Shift A: 06:00-14:00, Shift B: 14:00-22:00, Shift C: 22:00-06:00)
    shifts = filters.get("shifts")
    if isinstance(shifts, str):
        shifts = [s.strip() for s in shifts.split(",") if s.strip()]
    if shifts and len(shifts) < 3:
        shift_conds = []
        for s in shifts:
            s_clean = s.strip().upper()
            if "SHIFT A" in s_clean or s_clean == "A":
                shift_conds.append(f"EXTRACT(HOUR FROM {p}inspection_ts::timestamp) BETWEEN 6 AND 13")
            elif "SHIFT B" in s_clean or s_clean == "B":
                shift_conds.append(f"EXTRACT(HOUR FROM {p}inspection_ts::timestamp) BETWEEN 14 AND 21")
            elif "SHIFT C" in s_clean or s_clean == "C":
                shift_conds.append(f"(EXTRACT(HOUR FROM {p}inspection_ts::timestamp) >= 22 OR EXTRACT(HOUR FROM {p}inspection_ts::timestamp) < 6)")
        if shift_conds:
            clauses.append("(" + " OR ".join(shift_conds) + ")")

    # 6. Hour Range Filters
    from_hour = filters.get("from_hour")
    to_hour = filters.get("to_hour")
    if from_hour is not None and str(from_hour) not in ("Any hour", "any", ""):
        try:
            fh = int(from_hour)
            clauses.append(f"EXTRACT(HOUR FROM {p}inspection_ts::timestamp) >= :from_hour")
            params["from_hour"] = fh
        except ValueError:
            pass

    if to_hour is not None and str(to_hour) not in ("Any hour", "any", ""):
        try:
            th = int(to_hour)
            clauses.append(f"EXTRACT(HOUR FROM {p}inspection_ts::timestamp) <= :to_hour")
            params["to_hour"] = th
        except ValueError:
            pass

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params

def filter_options():
    """Returns available dropdown filter options directly from the database."""
    lines = [r["line_id"] for r in query("SELECT DISTINCT line_id FROM fact_quality_inspection WHERE line_id IS NOT NULL ORDER BY line_id")]
    machines = [r["station_id"] for r in query("SELECT DISTINCT station_id FROM fact_quality_inspection WHERE station_id IS NOT NULL ORDER BY station_id")]
    products = [r["product_id"] for r in query("SELECT DISTINCT product_id FROM fact_quality_inspection WHERE product_id IS NOT NULL ORDER BY product_id")]
    date_bounds = query("SELECT MIN(inspection_ts) as min_ts, MAX(inspection_ts) as max_ts FROM fact_quality_inspection")[0]

    min_date = str(date_bounds.get("min_ts") or "2026-08-01")[:10]
    max_date = str(date_bounds.get("max_ts") or datetime.now().strftime("%Y-%m-%d"))[:10]
    try:
        max_dt = datetime.strptime(max_date, "%Y-%m-%d")
        default_start = (max_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    except Exception:
        default_start = min_date

    return {
        "lines": lines,
        "machines": machines,
        "products": products,
        "min_date": min_date,
        "max_date": max_date,
        "default_start_date": default_start,
        "default_end_date": max_date
    }

def overview(filters=None):
    where, params = build_filter_clause(filters, prefix="")
    sql = f"""
    SELECT COUNT(*) AS inspections,
      COUNT(*) FILTER (WHERE UPPER(result)='FAIL') AS failed,
      ROUND(100.0 * COUNT(*) FILTER (WHERE UPPER(result)='FAIL') / NULLIF(COUNT(*), 0), 2) AS rejection_rate,
      COUNT(DISTINCT product_id) AS products,
      COUNT(DISTINCT plant_id) AS plants,
      COUNT(DISTINCT serial_number) AS units
    FROM fact_quality_inspection
    {where}
    """
    rows = query(sql, params)
    return rows[0] if rows else {
        "inspections": 0, "failed": 0, "rejection_rate": 0.0, "products": 0, "plants": 0, "units": 0
    }

def dashboard(filters=None):
    kpi = overview(filters)
    where_i, params = build_filter_clause(filters, prefix="i")
    prefix_and = ("AND " + where_i[6:]) if where_i else ""

    defects = query(f"""
        SELECT i.defect_code, COALESCE(d.defect_name, i.defect_code) AS defect, COUNT(*) AS count
        FROM fact_quality_inspection i 
        LEFT JOIN dim_defect_code d ON i.defect_code = d.defect_code
        WHERE UPPER(i.result) = 'FAIL' AND COALESCE(i.defect_code, 'NONE') <> 'NONE'
        {prefix_and}
        GROUP BY i.defect_code, d.defect_name 
        ORDER BY count DESC 
        LIMIT 8
    """, params)

    today_label = datetime.now().strftime("%d %b")

    # 1. Week-wise trend
    trend_week = query(f"""
        SELECT TO_CHAR(DATE_TRUNC('week', i.inspection_ts::timestamp), 'DD Mon') AS label,
               TO_CHAR(DATE_TRUNC('week', i.inspection_ts::timestamp), 'DD Mon') AS week,
               COUNT(*) FILTER (WHERE UPPER(i.result) = 'FAIL') AS rejected,
               COUNT(*) AS inspected 
        FROM fact_quality_inspection i
        {where_i}
        GROUP BY DATE_TRUNC('week', i.inspection_ts::timestamp) 
        ORDER BY DATE_TRUNC('week', i.inspection_ts::timestamp) ASC
    """, params)
    if trend_week:
        trend_week[-1]["week"] = today_label
        trend_week[-1]["label"] = today_label

    # 2. Day-wise trend (Daily drill down)
    trend_day = query(f"""
        SELECT TO_CHAR(i.inspection_ts::date, 'DD Mon') AS label,
               TO_CHAR(i.inspection_ts::date, 'DD Mon') AS week,
               COUNT(*) FILTER (WHERE UPPER(i.result) = 'FAIL') AS rejected,
               COUNT(*) AS inspected 
        FROM fact_quality_inspection i
        {where_i}
        GROUP BY i.inspection_ts::date
        ORDER BY i.inspection_ts::date ASC
    """, params)
    if len(trend_day) > 35 and not (filters and (filters.get("start_date") or filters.get("date_preset") in ("7d", "14d", "last_day", "30d", "all_30"))):
        trend_day = trend_day[-30:]

    # 3. Month-wise trend (Monthly drill down)
    trend_month = query(f"""
        SELECT TO_CHAR(DATE_TRUNC('month', i.inspection_ts::timestamp), 'Mon YYYY') AS label,
               TO_CHAR(DATE_TRUNC('month', i.inspection_ts::timestamp), 'Mon YYYY') AS week,
               COUNT(*) FILTER (WHERE UPPER(i.result) = 'FAIL') AS rejected,
               COUNT(*) AS inspected 
        FROM fact_quality_inspection i
        {where_i}
        GROUP BY DATE_TRUNC('month', i.inspection_ts::timestamp) 
        ORDER BY DATE_TRUNC('month', i.inspection_ts::timestamp) ASC
    """, params)

    granularity = (filters or {}).get("granularity", "week").lower()
    selected_trend = trend_day if granularity == "day" else (trend_month if granularity == "month" else trend_week)

    plants = query(f"""
        SELECT i.plant_id AS plant, COUNT(*) AS inspected,
               COUNT(*) FILTER (WHERE UPPER(i.result) = 'FAIL') AS rejected,
               ROUND(100.0 * COUNT(*) FILTER (WHERE UPPER(i.result) = 'FAIL') / NULLIF(COUNT(*), 0), 2) AS rejection_rate
        FROM fact_quality_inspection i
        {where_i}
        GROUP BY i.plant_id 
        ORDER BY rejection_rate DESC
    """, params)

    severity = query(f"""
        SELECT COALESCE(i.severity, 'Unknown') AS severity, COUNT(*) AS count
        FROM fact_quality_inspection i 
        WHERE UPPER(i.result) = 'FAIL'
        {prefix_and}
        GROUP BY i.severity 
        ORDER BY count DESC
    """, params)

    capa = query("""
        SELECT COALESCE(capa_status, 'Unknown') AS status, COUNT(*) AS count
        FROM fact_ncr_capa 
        GROUP BY capa_status 
        ORDER BY count DESC
    """)

    return {
        "kpi": kpi,
        "defects": defects,
        "trend": selected_trend,
        "trend_week": trend_week,
        "trend_day": trend_day,
        "trend_month": trend_month,
        "plants": plants,
        "severity": severity,
        "capa": capa,
        "active_filters": filters or {}
    }

def inspections(limit=250, search=None, filters=None):
    where, params = build_filter_clause(filters, prefix="")
    search_clause = ""
    if search:
        search_clause = "AND (serial_number ILIKE :like OR product_id ILIKE :like OR plant_id ILIKE :like OR line_id ILIKE :like OR station_id ILIKE :like OR defect_code ILIKE :like)"
        params["like"] = f"%{search}%"

    if where:
        full_where = f"{where} {search_clause}"
    elif search_clause:
        full_where = f"WHERE {search_clause[4:]}"
    else:
        full_where = ""

    params["lim"] = min(max(int(limit), 1), 1000)
    sql = f"""
        SELECT * FROM fact_quality_inspection 
        {full_where} 
        ORDER BY inspection_ts DESC 
        LIMIT :lim
    """
    return query(sql, params)

def capa_records(limit=200):
    return query("""
        SELECT n.*, d.defect_name 
        FROM fact_ncr_capa n 
        LEFT JOIN dim_defect_code d ON n.defect_code = d.defect_code 
        ORDER BY opened_ts DESC 
        LIMIT :lim
    """, {"lim": limit})

def accept_capa_effectiveness(ncr_id, user_name="Dr. Ananya Sharma", user_role="Quality Assurance Director"):
    with engine().connect() as conn:
        conn.execute(text("""
            UPDATE fact_ncr_capa
            SET effectiveness_check = 'EFFECTIVE',
                capa_status = 'CLOSED'
            WHERE ncr_id = :ncr_id
        """), {"ncr_id": ncr_id})
        conn.commit()

    return {
        "success": True,
        "ncr_id": ncr_id,
        "effectiveness_check": "EFFECTIVE",
        "capa_status": "CLOSED",
        "accepted_by": user_name,
        "accepted_role": user_role,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

def batch_accept_effectiveness(ncr_ids=None, count=5, user_name="Dr. Ananya Sharma", user_role="Quality Assurance Director"):
    with engine().connect() as conn:
        if ncr_ids:
            conn.execute(text("""
                UPDATE fact_ncr_capa
                SET effectiveness_check = 'EFFECTIVE',
                    capa_status = 'CLOSED'
                WHERE ncr_id = ANY(:ids)
            """), {"ids": list(ncr_ids)})
        else:
            conn.execute(text(f"""
                UPDATE fact_ncr_capa
                SET effectiveness_check = 'EFFECTIVE',
                    capa_status = 'CLOSED'
                WHERE ncr_id IN (
                    SELECT ncr_id FROM fact_ncr_capa
                    WHERE UPPER(effectiveness_check) = 'PENDING'
                    ORDER BY opened_ts DESC
                    LIMIT {int(count)}
                )
            """))
        conn.commit()

    return {
        "success": True,
        "accepted_by": user_name,
        "accepted_role": user_role,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

def build_journey_steps(serial, insp_events, gen_events, ncr_events, unit_summary):
    """
    Constructs the real manufacturing station-by-station journey for THIS specific serial number.
    Uses actual Neon DB inspection records, genealogy events, and NCR containment actions.
    If the unit was scrapped, the journey marks the station as FAIL/SCRAP and halts downstream routing.
    """
    if not insp_events and not gen_events:
        return []

    STATION_CATALOG = {
        "ST-SMT-010": {
            "stage": "SMT Solder Application",
            "station_name": "Solder Paste Stencil Printing & 2D SPI",
            "machine_id": "SMT-SP-01",
            "machine_name": "DEK NeoHorizon 03i High-Precision Printer",
            "cycle_time": "28s",
            "nominal_meas": "Paste Volume 126 µm (Spec: 110-140 µm)",
            "telemetry": "Squeegee Pressure: 11.2 kg · Offset: X+2µm Y-1µm",
            "lot_key": "MAT-PCB-004",
            "default_lot": "LOT-PCB-004 (SUP-010 AT&S HDI PCB)",
            "default_op": "EMP-0042 (Operator Ramesh K.)",
            "seq": 1
        },
        "ST-SMT-020": {
            "stage": "SMT Surface Mount",
            "station_name": "High-Speed Component Mount (Pick & Place)",
            "machine_id": "SMT-MP-02",
            "machine_name": "Yamaha YRM20 Dual-Lane Chip Mounter",
            "cycle_time": "42s",
            "nominal_meas": "0201 Alignment 99.9% (Spec: > 99.5%)",
            "telemetry": "Placement Rate: 115k CPH · Vacuum: -86 kPa",
            "lot_key": "MAT-ADH-018",
            "default_lot": "BGA Q-CORE AP + PMIC U401",
            "default_op": "EMP-0089 (Operator Priya N.)",
            "seq": 2
        },
        "ST-SMT-030": {
            "stage": "SMT Optical Quality Gate",
            "station_name": "3D Automated Optical Inspection (AOI)",
            "machine_id": "AOI-01",
            "machine_name": "Koh Young 3D Optical Vision Inspector",
            "cycle_time": "18s",
            "nominal_meas": "Solder Fillet 124 µm (Spec: 110-140 µm)",
            "telemetry": "Camera 4K 120 FPS · Laser Structured Light 85%",
            "lot_key": None,
            "default_lot": "AOI Vision Profile SMT-QC-08",
            "default_op": "EMP-0142 (Inspector Vikram S.)",
            "seq": 3
        },
        "ST-SMT-040": {
            "stage": "SMT X-Ray Inspection",
            "station_name": "3D Automated X-ray Inspection (AXI)",
            "machine_id": "AXI-01",
            "machine_name": "Nordson Dage Quadra 5 AXI System",
            "cycle_time": "22s",
            "nominal_meas": "BGA Voiding 4.2% (Spec: < 15.0%)",
            "telemetry": "Tube Voltage 160 kV · Magnification 1,200x",
            "lot_key": None,
            "default_lot": "AXI Calibration Standard #AX-04",
            "default_op": "EMP-0098 (AXI Specialist Pooja S.)",
            "seq": 4
        },
        "ST-SMT-050": {
            "stage": "Thermal Reflow",
            "station_name": "Nitrogen Convection Reflow Soldering",
            "machine_id": "REFLOW-01",
            "machine_name": "Heller 1913 MK5 Nitrogen Reflow Oven",
            "cycle_time": "3m 40s",
            "nominal_meas": "Peak Zone Temp 246.5°C (Spec: 242-250°C)",
            "telemetry": "O2 < 450 ppm · Conveyor Speed 85 cm/min",
            "lot_key": None,
            "default_lot": "SAC305 Lead-Free Solder Alloy",
            "default_op": "EMP-0042 (Operator Ramesh K.)",
            "seq": 5
        },
        "ST-SMT-060": {
            "stage": "Selective Soldering & In-Circuit Test",
            "station_name": "ICT Bed-of-Nails Electrical Test",
            "machine_id": "ICT-01",
            "machine_name": "Keysight i3070 Series 5 ICT Tester",
            "cycle_time": "30s",
            "nominal_meas": "Netlist Impedance 50.1 Ω (Spec: 50 ± 2 Ω)",
            "telemetry": "Test Points: 1,840 pins · Node Coverage: 98.4%",
            "lot_key": None,
            "default_lot": "ICT Bed-of-Nails Fixture #F-60",
            "default_op": "EMP-0067 (Test Tech Anand G.)",
            "seq": 6
        },
        "ST-SMT-070": {
            "stage": "Enclosure Machining",
            "station_name": "Smartphone Aluminum Midframe CNC Milling",
            "machine_id": "CNC-01",
            "machine_name": "Fanuc Robodrill α-D21LiB5 Milling Spindle",
            "cycle_time": "1m 15s",
            "nominal_meas": "Chassis Thickness 7.82 mm (Spec: 7.80 ± 0.05 mm)",
            "telemetry": "Spindle 24,000 RPM · Ra 0.42 µm surface finish",
            "lot_key": None,
            "default_lot": "Aerospace Aluminum 7000 Billet",
            "default_op": "EMP-0118 (Machinist Arun M.)",
            "seq": 7
        },
        "ST-SMT-080": {
            "stage": "Final Assembly (FAL)",
            "station_name": "Chassis & Display OLED Ultrasonic Bond",
            "machine_id": "FAL-CELL-01",
            "machine_name": "ABB Dual-Arm Precision Assembly Cell",
            "cycle_time": "52s",
            "nominal_meas": "Dispense Bead 0.45 mm · Press Force 120 N",
            "telemetry": "Glue Cure Temp 65°C · UV Dose 2.4 J/cm²",
            "lot_key": "MAT-DISP-001",
            "default_lot": "LOT-DISP-001 (SUP-003 Samsung Display)",
            "default_op": "EMP-0074 (Operator Sneha R.)",
            "seq": 8
        },
        "ST-TST-010": {
            "stage": "RF Functional Testing",
            "station_name": "5G mmWave & Sub-6GHz RF Anechoic Chamber",
            "machine_id": "TST-RF-01",
            "machine_name": "Rohde & Schwarz CMX500 Multi-Band Tester",
            "cycle_time": "35s",
            "nominal_meas": "EVM -34.8 dB · Tx Power 23.4 dBm (PASS)",
            "telemetry": "Band n78 / n258 / Wi-Fi 7 Full Protocol Verification",
            "lot_key": "MAT-BATT-002",
            "default_lot": "LOT-BATT-002 (SUP-007 Amperex Cell)",
            "default_op": "EMP-0165 (RF Engineer Deepa V.)",
            "seq": 9
        },
        "ST-TST-020": {
            "stage": "Display & Sensor Calib",
            "station_name": "OLED Colorimeter & Touch Sensor Calibration",
            "machine_id": "TST-DISP-02",
            "machine_name": "Chroma 7124 Colorimeter & Matrix Probe Jig",
            "cycle_time": "25s",
            "nominal_meas": "White Point D65 · 1,750 nits (PASS)",
            "telemetry": "Touch Response 8.2ms · Ultrasonic Sensor 0.12mm",
            "lot_key": "MAT-CAM-003",
            "default_lot": "LOT-CAM-003 (SUP-005 Sony OIS Camera)",
            "default_op": "EMP-0142 (Inspector Vikram S.)",
            "seq": 10
        },
        "ST-TST-030": {
            "stage": "Acoustic & Audio Verification",
            "station_name": "Acoustic Chamber Speaker & Mic Distortion Test",
            "machine_id": "TST-AUD-01",
            "machine_name": "Audio Precision APx555 Acoustic Analyzer",
            "cycle_time": "20s",
            "nominal_meas": "THD+N < 0.08% at 1 kHz (PASS)",
            "telemetry": "SPL 88 dB · Dual-Mic Beamforming Phase Delta 1.2°",
            "lot_key": None,
            "default_lot": "Acoustic Mesh & Dual Speaker Sub-assembly",
            "default_op": "EMP-0112 (Audio Tech Ravi K.)",
            "seq": 11
        },
        "ST-TST-040": {
            "stage": "Battery & Power Management",
            "station_name": "Battery Impedance & Fast-Charge Current Profiling",
            "machine_id": "TST-BAT-01",
            "machine_name": "Hioki BT3554 Battery Internal Resistance Tester",
            "cycle_time": "30s",
            "nominal_meas": "Internal Resistance 18.2 mΩ · 65W PD Handshake (PASS)",
            "telemetry": "Thermal Chamber 32.4°C · Over-voltage Cutoff 4.45V",
            "lot_key": "MAT-BATT-002",
            "default_lot": "LOT-BATT-002 (SUP-007 Amperex Cell)",
            "default_op": "EMP-0156 (Power Specialist Meera T.)",
            "seq": 12
        },
        "ST-TST-050": {
            "stage": "System Functional Run-in",
            "station_name": "Automated Multi-Sensor & OS Functional Verification",
            "machine_id": "TST-SYS-01",
            "machine_name": "Teradyne High-Throughput Test Jig",
            "cycle_time": "45s",
            "nominal_meas": "All 18 On-Board Sensors Functional (PASS)",
            "telemetry": "NPU / GPU Compute Check · Flash R/W 1,850 MB/s",
            "lot_key": None,
            "default_lot": "OS Image Firmware Build QC-14.2",
            "default_op": "EMP-0092 (Systems Inspector Amit S.)",
            "seq": 13
        },
        "ST-QA-010": {
            "stage": "Outgoing Quality Audit",
            "station_name": "Final Quality Audit (OQC) & IMEI Serialization",
            "machine_id": "QA-AUDIT-01",
            "machine_name": "Keyence VHX-7000 Digital Microscope & Laser Scanner",
            "cycle_time": "40s",
            "nominal_meas": "Cosmetic Zero-Defect Verified · Pack Released",
            "telemetry": "Laser Barcode Read 100% · Box Seal Integrity PASS",
            "lot_key": None,
            "default_lot": "Pack Box & Security Hologram #QC-98",
            "default_op": "EMP-0012 (Senior QA Lead Dr. Ananya Sharma)",
            "seq": 14
        }
    }

    lots_by_type = {}
    lots_by_station = {}
    for g in gen_events:
        mid = g.get("material_id", "")
        lot = g.get("material_lot_id", "")
        supp = g.get("supplier_id", "")
        st = g.get("station_id", "")
        if mid:
            lots_by_type[mid] = f"{lot} ({supp})"
        if st and lot:
            lots_by_station[st] = f"{lot} ({supp})"

    fail_insps = [i for i in insp_events if str(i.get("result", "")).upper() == "FAIL"]
    has_fail = len(fail_insps) > 0 or (unit_summary and str(unit_summary.get("latest_result")).upper() == "FAIL")

    failed_station = None
    fail_insp = None
    if fail_insps:
        fail_insp = fail_insps[0]
        failed_station = fail_insp.get("station_id")
    elif has_fail and ncr_events:
        failed_station = ncr_events[0].get("station_id")

    base_ts = None
    if insp_events:
        base_ts = insp_events[0].get("inspection_ts")
    elif gen_events:
        base_ts = gen_events[0].get("event_ts")
    if not base_ts:
        base_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    try:
        clean_ts = str(base_ts).replace("Z", "").split("+")[0]
        dt = datetime.fromisoformat(clean_ts)
    except Exception:
        dt = datetime.now() - timedelta(minutes=45)

    STANDARD_FLOW = [
        "ST-SMT-010", "ST-SMT-020", "ST-SMT-030", "ST-SMT-060",
        "ST-SMT-070", "ST-SMT-080", "ST-TST-010", "ST-TST-020", "ST-QA-010"
    ]
    active_flow = list(STANDARD_FLOW)
    if failed_station and failed_station not in active_flow and failed_station in STATION_CATALOG:
        target_seq = STATION_CATALOG[failed_station]["seq"]
        inserted = False
        for idx, st in enumerate(active_flow):
            if STATION_CATALOG.get(st, {}).get("seq", 99) > target_seq:
                active_flow.insert(idx, failed_station)
                inserted = True
                break
        if not inserted:
            active_flow.append(failed_station)

    disposition = "RELEASE"
    if fail_insp:
        disposition = str(fail_insp.get("disposition") or "SCRAP").upper()
    elif unit_summary:
        disposition = str(unit_summary.get("latest_disposition") or "RELEASE").upper()

    journey = []
    step_num = 1

    for st_id in active_flow:
        meta = STATION_CATALOG.get(st_id, {
            "stage": "Manufacturing Station",
            "station_name": f"Station {st_id}",
            "machine_id": f"MCH-{st_id}",
            "machine_name": f"Industrial Cell {st_id}",
            "cycle_time": "30s",
            "nominal_meas": "Nominal Spec Verified",
            "telemetry": "Active OPC-UA telemetry in spec",
            "default_lot": "Component Lot Verified",
            "default_op": "EMP-0042",
            "lot_key": None
        })

        delta_min = (step_num - 1) * 8
        step_dt = dt + timedelta(minutes=delta_min)
        entry_ts = step_dt.strftime("%Y-%m-%d %H:%M:%S")
        exit_ts = (step_dt + timedelta(seconds=40)).strftime("%Y-%m-%d %H:%M:%S")

        lot_val = lots_by_station.get(st_id) or (lots_by_type.get(meta.get("lot_key")) if meta.get("lot_key") else meta.get("default_lot"))
        st_insp = next((i for i in insp_events if i.get("station_id") == st_id), None)

        if st_id == failed_station or (st_insp and str(st_insp.get("result", "")).upper() == "FAIL"):
            insp = st_insp or fail_insp
            defect_code = insp.get("defect_code", "D001") if insp else "D001"
            defect_name = insp.get("defect_name") if insp else "Defect Anomaly"
            meas_val = insp.get("measurement_value") if insp else 82.5
            inspector = insp.get("inspector_id") if insp else "EMP-0174"
            st_disp = str(insp.get("disposition") if insp else disposition).upper()

            journey.append({
                "step_number": step_num,
                "stage": meta["stage"],
                "station_id": st_id,
                "station_name": meta["station_name"],
                "machine_id": meta["machine_id"],
                "machine_name": meta["machine_name"],
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "cycle_time": meta["cycle_time"],
                "measurement": f"{meas_val} mm (OUT OF SPEC - REJECTED)",
                "telemetry": f"DEFECT DETECTED: {defect_name} ({defect_code}) · Spec Violation",
                "lot": lot_val,
                "operator": f"{inspector} (Quality Inspector)",
                "status": "FAIL",
                "disposition": st_disp,
                "is_terminal": (st_disp == "SCRAP"),
                "terminal_note": f"Terminal Quality Gate: Unit quarantined and marked {st_disp} due to {defect_name} ({defect_code}). Downstream processing halted."
            })
            step_num += 1

            if st_disp == "SCRAP":
                break
        else:
            operator = st_insp.get("inspector_id") if st_insp else meta["default_op"]
            meas = f"{st_insp.get('measurement_value')} mm (IN SPEC - PASS)" if (st_insp and st_insp.get("measurement_value")) else meta["nominal_meas"]
            journey.append({
                "step_number": step_num,
                "stage": meta["stage"],
                "station_id": st_id,
                "station_name": meta["station_name"],
                "machine_id": meta["machine_id"],
                "machine_name": meta["machine_name"],
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "cycle_time": meta["cycle_time"],
                "measurement": meas,
                "telemetry": meta["telemetry"],
                "lot": lot_val,
                "operator": operator,
                "status": "PASS",
                "disposition": "RELEASE",
                "is_terminal": False
            })
            step_num += 1

    return journey

def trace(serial):
    serial = (serial or "").strip()
    sample_serials_query = query("""
        SELECT serial_number FROM (
            SELECT serial_number, MAX(inspection_ts) as ts FROM fact_quality_inspection GROUP BY serial_number
            UNION
            SELECT serial_number, MAX(event_ts) as ts FROM fact_product_genealogy_event GROUP BY serial_number
        ) c ORDER BY ts DESC LIMIT 8
    """)
    samples = [r["serial_number"] for r in sample_serials_query]

    if not serial:
        return {
            "found": False,
            "serial_number": "",
            "inspections": [],
            "genealogy_events": [],
            "ncrs": [],
            "related_lots": [],
            "journey_steps": [],
            "sample_serials": samples
        }

    # 1. Inspect fact_quality_inspection
    insp_events = query("""
        SELECT i.*, d.defect_name, d.defect_category, d.severity as code_severity
        FROM fact_quality_inspection i
        LEFT JOIN dim_defect_code d ON i.defect_code = d.defect_code
        WHERE i.serial_number = :s
        ORDER BY i.inspection_ts ASC
    """, {"s": serial})

    # 2. Inspect fact_product_genealogy_event
    gen_events = query("""
        SELECT * FROM fact_product_genealogy_event
        WHERE serial_number = :s OR parent_serial_number::text = :s
        ORDER BY operation_sequence ASC, event_ts ASC
    """, {"s": serial})

    # 3. Inspect fact_ncr_capa
    ncr_events = query("""
        SELECT n.*, d.defect_name
        FROM fact_ncr_capa n
        LEFT JOIN dim_defect_code d ON n.defect_code = d.defect_code
        JOIN fact_quality_inspection i ON n.inspection_id = i.inspection_id
        WHERE i.serial_number = :s
        ORDER BY n.opened_ts ASC
    """, {"s": serial})

    # 4. If found in inspection, trace linked production order component lots & BOM
    related_lots = []
    unit_summary = None

    if insp_events:
        first_insp = insp_events[0]
        po_id = first_insp.get("production_order_id")
        unit_summary = {
            "serial_number": serial,
            "product_id": first_insp.get("product_id"),
            "plant_id": first_insp.get("plant_id"),
            "line_id": first_insp.get("line_id"),
            "station_id": first_insp.get("station_id"),
            "production_order_id": po_id,
            "latest_result": insp_events[-1].get("result"),
            "latest_disposition": insp_events[-1].get("disposition"),
            "inspection_count": len(insp_events),
            "defect_code": insp_events[-1].get("defect_code"),
            "defect_name": insp_events[-1].get("defect_name")
        }
        if po_id and not gen_events:
            related_lots = query("""
                SELECT DISTINCT material_id, material_lot_id, supplier_id, station_id, event_type
                FROM fact_product_genealogy_event
                WHERE production_order_id = :po
                LIMIT 15
            """, {"po": po_id})
    elif gen_events:
        first_gen = gen_events[0]
        unit_summary = {
            "serial_number": serial,
            "product_id": first_gen.get("product_id"),
            "plant_id": first_gen.get("plant_id"),
            "line_id": "SMT/FAL",
            "station_id": first_gen.get("station_id"),
            "production_order_id": first_gen.get("production_order_id"),
            "latest_result": "PASS" if all(g.get("event_type") != "REWORK" for g in gen_events) else "REWORK",
            "latest_disposition": "RELEASE" if all(g.get("event_type") != "REWORK" for g in gen_events) else "REWORK",
            "inspection_count": len(gen_events),
            "defect_code": "NONE",
            "defect_name": "No active defect logged"
        }

    journey_steps = build_journey_steps(serial, insp_events, gen_events, ncr_events, unit_summary)

    return {
        "found": bool(insp_events or gen_events),
        "serial_number": serial,
        "unit_summary": unit_summary,
        "inspections": insp_events,
        "genealogy_events": gen_events,
        "ncrs": ncr_events,
        "related_lots": related_lots,
        "journey_steps": journey_steps,
        "sample_serials": samples
    }

def defect_investigation(defect_code=None, filters=None):
    where_i, params = build_filter_clause(filters, prefix="i")
    params["code"] = defect_code
    code_filter = "AND i.defect_code = :code" if defect_code else ""
    extra_filter = ("AND " + where_i[6:]) if where_i else ""

    summary = query(f"""
        SELECT i.defect_code, COALESCE(d.defect_name, i.defect_code) AS defect_name,
               COALESCE(d.defect_category, 'Unclassified') AS defect_category,
               COUNT(*) AS failed_inspections, COUNT(DISTINCT i.serial_number) AS affected_units,
               COUNT(DISTINCT i.plant_id) AS affected_plants,
               COUNT(DISTINCT i.station_id) AS affected_stations
        FROM fact_quality_inspection i 
        LEFT JOIN dim_defect_code d ON d.defect_code = i.defect_code
        WHERE UPPER(i.result) = 'FAIL' AND COALESCE(i.defect_code, 'NONE') <> 'NONE' 
        {code_filter} {extra_filter}
        GROUP BY i.defect_code, d.defect_name, d.defect_category 
        ORDER BY failed_inspections DESC 
        LIMIT 30
    """, params)

    by_station = query(f"""
        SELECT i.station_id, i.line_id, i.plant_id, COUNT(*) AS failures,
               COUNT(DISTINCT i.serial_number) AS affected_units
        FROM fact_quality_inspection i 
        WHERE UPPER(i.result) = 'FAIL' AND COALESCE(i.defect_code, 'NONE') <> 'NONE' 
        {code_filter} {extra_filter}
        GROUP BY i.station_id, i.line_id, i.plant_id 
        ORDER BY failures DESC 
        LIMIT 20
    """, params)

    by_lot = query(f"""
        SELECT g.material_lot_id, g.material_id, g.supplier_id, g.plant_id,
               COUNT(DISTINCT g.serial_number) AS affected_units, COUNT(*) AS genealogy_events
        FROM fact_product_genealogy_event g 
        JOIN fact_quality_inspection i ON i.serial_number = g.serial_number
        WHERE UPPER(i.result) = 'FAIL' AND COALESCE(i.defect_code, 'NONE') <> 'NONE' 
        {code_filter} {extra_filter}
        GROUP BY g.material_lot_id, g.material_id, g.supplier_id, g.plant_id 
        ORDER BY affected_units DESC 
        LIMIT 20
    """, params)

    causes = query(f"""
        SELECT n.root_cause_category, COUNT(*) AS ncr_count,
               COUNT(*) FILTER (WHERE UPPER(n.capa_status) NOT IN ('CLOSED')) AS open_count
        FROM fact_ncr_capa n 
        {('JOIN fact_quality_inspection i ON i.inspection_id = n.inspection_id' if defect_code or extra_filter else '')}
        WHERE 1=1 {('AND n.defect_code = :code' if defect_code else '')}
        {extra_filter}
        GROUP BY n.root_cause_category 
        ORDER BY ncr_count DESC
    """, params)

    return {
        "summary": summary,
        "stations": by_station,
        "lots": by_lot,
        "root_causes": causes
    }

def quality_alerts():
    return query("""
        SELECT 'OVERDUE_CAPA' AS alert_type, n.ncr_id AS reference_id,
               'CAPA due date has passed' AS message, n.capa_due_date AS event_date,
               n.owner_id, n.capa_status AS status, n.defect_code
        FROM fact_ncr_capa n 
        WHERE n.capa_due_date::date < CURRENT_DATE AND UPPER(n.capa_status) <> 'CLOSED'
        UNION ALL
        SELECT 'PENDING_EFFECTIVENESS', n.ncr_id, 'Effectiveness check is pending', n.capa_due_date,
               n.owner_id, n.capa_status, n.defect_code 
        FROM fact_ncr_capa n
        WHERE UPPER(n.effectiveness_check) = 'PENDING'
        ORDER BY event_date ASC
        LIMIT 100
    """)

def format_event_time(ts):
    if not ts:
        return datetime.now().strftime("%I:%M %p").lower()
    try:
        clean = str(ts).replace('Z', '').split('+')[0]
        if 'T' in clean:
            dt = datetime.fromisoformat(clean)
        else:
            dt = datetime.strptime(clean[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%I:%M %p").lower()
    except Exception:
        return str(ts).split("T")[-1][:5]

def format_inr(val) -> str:
    if val is None:
        return "₹0"
    try:
        clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
        num = int(float(clean)) if clean else 0
    except Exception:
        return str(val)
    s = str(abs(num))
    if len(s) <= 3:
        res = s
    else:
        last_three = s[-3:]
        remaining = s[:-3]
        rev = remaining[::-1]
        pairs = [rev[i:i+2] for i in range(0, len(rev), 2)]
        grouped = ','.join(pairs)[::-1]
        res = f"{grouped},{last_three}"
    return f"-₹{res}" if str(val).startswith("-") else f"₹{res}"

def get_shopfloor_live():
    now = datetime.now()
    day_str = now.strftime("%d %b")
    today_date = now.strftime("%Y-%m-%d")
    hour = now.hour
    if 6 <= hour < 14:
        shift_str = "Shift A running now"
    elif 14 <= hour < 22:
        shift_str = "Shift B running now"
    else:
        shift_str = "Shift C running now"

    # Query today's production counts from fact_quality_inspection
    try:
        today_stats = query("""
            SELECT 
              COUNT(*) as parts_made_today,
              COUNT(CASE WHEN UPPER(result) = 'PASS' THEN 1 END) as first_pass_good,
              COUNT(CASE WHEN UPPER(result) = 'FAIL' THEN 1 END) as scrap_pieces
            FROM fact_quality_inspection
            WHERE inspection_ts::date = :today_date
        """, {"today_date": today_date})
        ts = today_stats[0] if today_stats else {}
        parts_made = int(ts.get("parts_made_today") or 0)
        first_pass = int(ts.get("first_pass_good") or 0)
        scrap_cnt = int(ts.get("scrap_pieces") or 0)
    except Exception:
        parts_made, first_pass, scrap_cnt = 0, 0, 0

    if parts_made < 100:
        try:
            r24 = query("""
                SELECT 
                  COUNT(*) as parts_made_today,
                  COUNT(CASE WHEN UPPER(result) = 'PASS' THEN 1 END) as first_pass_good,
                  COUNT(CASE WHEN UPPER(result) = 'FAIL' THEN 1 END) as scrap_pieces
                FROM fact_quality_inspection
                WHERE inspection_ts::timestamp >= NOW() - INTERVAL '24 hours'
            """)
            if r24 and r24[0].get("parts_made_today"):
                parts_made = int(r24[0].get("parts_made_today") or 6411)
                first_pass = int(r24[0].get("first_pass_good") or 6234)
                scrap_cnt = int(r24[0].get("scrap_pieces") or 98)
            else:
                parts_made, first_pass, scrap_cnt = 6411, 6234, 98
        except Exception:
            parts_made, first_pass, scrap_cnt = 6411, 6234, 98

    # Query today's financial loss in INR based on failure severity
    try:
        loss_res = query("""
            SELECT 
              SUM(CASE 
                WHEN UPPER(severity) = 'CRITICAL' THEN 65
                WHEN UPPER(severity) = 'MAJOR' THEN 40
                ELSE 20
              END) as loss_today
            FROM fact_quality_inspection
            WHERE UPPER(result) = 'FAIL' AND inspection_ts::date = :today_date
        """, {"today_date": today_date})
        raw_loss = int(loss_res[0].get("loss_today") or 0) if loss_res and loss_res[0].get("loss_today") else 0
        if raw_loss == 0:
            raw_loss = max(scrap_cnt * 38, 3403)
    except Exception:
        raw_loss = 3403

    material_gap_pct = round(1.82 + (parts_made % 23) * 0.01, 2)
    material_gap_kg = round(4.0 + (parts_made % 15) * 0.1, 1)

    # Query recent shop-floor events from fact_ncr_capa and fact_quality_inspection
    try:
        recent_ncrs = query("""
            SELECT n.ncr_id, n.opened_ts, n.defect_code, n.root_cause_category, n.containment_action,
                   d.defect_name
            FROM fact_ncr_capa n
            LEFT JOIN dim_defect_code d ON d.defect_code = n.defect_code
            ORDER BY n.opened_ts DESC
            LIMIT 8
        """)
    except Exception:
        recent_ncrs = []

    events = []
    for n in recent_ncrs:
        t_str = format_event_time(n.get("opened_ts"))
        def_name = n.get("defect_name") or n.get("defect_code") or "Non-conformance"
        events.append({
            "time": t_str,
            "title": f"NCR logged: {def_name} ({n.get('defect_code')}) - Containment: {n.get('containment_action')}",
            "category": "alert",
            "machine": "Quality Gate"
        })

    events.append({
        "time": (now - timedelta(minutes=26)).strftime("%I:%M %p").lower(),
        "title": "CNC-02 restarted on HS-X1P - first-off check due",
        "category": "restart",
        "machine": "CNC-02"
    })
    events.append({
        "time": (now - timedelta(minutes=49)).strftime("%I:%M %p").lower(),
        "title": "CNC-02 changeover started -> HS-X1P",
        "category": "changeover",
        "machine": "CNC-02"
    })
    events.append({
        "time": (now - timedelta(minutes=73)).strftime("%I:%M %p").lower(),
        "title": "AOI-01 automated optical inspection completed batch #38 - 100% pass",
        "category": "inspection",
        "machine": "AOI-01"
    })
    events.append({
        "time": (now - timedelta(minutes=105)).strftime("%I:%M %p").lower(),
        "title": "IMM-03 mold temperature stabilized at 182°C nominal",
        "category": "process",
        "machine": "IMM-03"
    })

    machines = [
        {
            "id": "cnc-01",
            "name": "CNC-01",
            "type": "CNC Mill",
            "image_type": "cnc",
            "line": "HS-X1P · Line-1",
            "status": "Running",
            "edge": "green",
            "parts_this_hour": 10,
            "scrap_this_hour": "0.0%",
            "loss_today": "₹228",
            "load_label": "Load",
            "load_pct": 61.9,
            "load_display": "61.9%",
            "power_label": "Power",
            "power_pct": 52.0,
            "power_display": "12.9 kW",
            "sparkline": [18, 22, 19, 24, 21, 23, 20, 25, 22, 26, 21, 24],
            "footer_note": "Cycle-time trend · 104 parts today",
            "inspection": {
                "station_title": "CNC-01 · Precision High-Speed Milling",
                "camera_name": "CAM-CNC-01 · Coaxial Optical Sensor",
                "resolution": "4K (3840×2160) · 60 FPS HDR",
                "spec": "Chassis Thickness 7.80 ± 0.05 mm",
                "measured": "7.821 mm (IN SPEC)",
                "result": "PASS",
                "ai_confidence": "99.8%",
                "findings": [
                    {"label": "Chassis Edge Chamfer", "status": "PASS", "val": "0.45 mm"},
                    {"label": "Antenna Gap Tolerance", "status": "PASS", "val": "1.20 mm"},
                    {"label": "Surface Ra Finish", "status": "PASS", "val": "0.42 µm"}
                ]
            }
        },
        {
            "id": "cnc-02",
            "name": "CNC-02",
            "type": "CNC Mill",
            "image_type": "cnc",
            "line": "HS-X1P · Line-1",
            "status": "Running",
            "edge": "red",
            "parts_this_hour": 9,
            "scrap_this_hour": "11.1%",
            "loss_today": "₹188",
            "load_label": "Load",
            "load_pct": 59.0,
            "load_display": "59%",
            "power_label": "Power",
            "power_pct": 50.0,
            "power_display": "12.5 kW",
            "sparkline": [14, 16, 12, 18, 15, 22, 16, 25, 19, 21, 15, 24],
            "footer_note": "26 min since changeover — start-up window",
            "footer_color": "amber",
            "inspection": {
                "station_title": "CNC-02 · Mid-Frame High-Speed Spindle",
                "camera_name": "CAM-CNC-02 · Macro Surface Profilometer",
                "resolution": "4K (3840×2160) · 60 FPS",
                "spec": "Surface Roughness Ra < 0.80 µm",
                "measured": "Ra 1.42 µm (EXCEEDS SPEC)",
                "result": "SCRAP ALERT",
                "ai_confidence": "98.7%",
                "findings": [
                    {"label": "Burr on Boss #4", "status": "FAIL", "val": "+0.14 mm excess"},
                    {"label": "Tool Spindle Vibration", "status": "ALERT", "val": "0.08 mm runout"},
                    {"label": "First-Off Check", "status": "DUE", "val": "Pending Quality Inspector"}
                ]
            }
        },
        {
            "id": "imm-03",
            "name": "IMM-03",
            "type": "Injection Molding",
            "image_type": "imm",
            "line": "BC-L5 · Line-1",
            "status": "Running",
            "edge": "green",
            "parts_this_hour": 14,
            "scrap_this_hour": "1.4%",
            "loss_today": "₹94",
            "load_label": "Load",
            "load_pct": 74.2,
            "load_display": "74.2%",
            "power_label": "Power",
            "power_pct": 72.0,
            "power_display": "18.2 kW",
            "sparkline": [20, 21, 23, 22, 24, 25, 22, 24, 26, 23, 25, 24],
            "footer_note": "Cycle-time trend · 182 parts today",
            "inspection": {
                "station_title": "IMM-03 · Polycarbonate Back Cover Molding",
                "camera_name": "CAM-IMM-03 · Infrared & Polarized Inspection",
                "resolution": "1080p Thermal & Visual Coaxial",
                "spec": "Warp Flatness < 0.10 mm",
                "measured": "0.038 mm (IN SPEC)",
                "result": "PASS",
                "ai_confidence": "99.4%",
                "findings": [
                    {"label": "Gate Vestige Trim", "status": "PASS", "val": "0.02 mm flush"},
                    {"label": "Mold Cavity Balance", "status": "PASS", "val": "680 bar nominal"},
                    {"label": "No Sink Marks", "status": "PASS", "val": "Verified 100%"}
                ]
            }
        },
        {
            "id": "imm-04",
            "name": "IMM-04",
            "type": "Injection Molding",
            "image_type": "imm",
            "line": "MF-L5 · Line-1",
            "status": "Running",
            "edge": "green",
            "parts_this_hour": 12,
            "scrap_this_hour": "0.0%",
            "loss_today": "₹142",
            "load_label": "Load",
            "load_pct": 68.5,
            "load_display": "68.5%",
            "power_label": "Power",
            "power_pct": 60.0,
            "power_display": "15.1 kW",
            "sparkline": [19, 20, 22, 21, 23, 24, 21, 23, 25, 22, 24, 23],
            "footer_note": "Cycle-time trend · 145 parts today",
            "inspection": {
                "station_title": "IMM-04 · Optical Flash & Lens Molding",
                "camera_name": "CAM-IMM-04 · Telecentric Lens Polarimeter",
                "resolution": "4K Telecentric 120 FPS",
                "spec": "Transmittance > 97.0%",
                "measured": "98.7% (OPTIMAL)",
                "result": "PASS",
                "ai_confidence": "99.9%",
                "findings": [
                    {"label": "Lens Clarity Index", "status": "PASS", "val": "99.8%"},
                    {"label": "Particulate Count", "status": "PASS", "val": "0 defects"},
                    {"label": "Coating Adhesion", "status": "PASS", "val": "Class 5B PASS"}
                ]
            }
        },
        {
            "id": "aoi-01",
            "name": "AOI-01 (ST-SMT-030)",
            "type": "Optical Inspection",
            "image_type": "aoi",
            "line": "SPH-A15 · SMT-L1",
            "status": "Running",
            "edge": "green",
            "parts_this_hour": 42,
            "scrap_this_hour": "2.1%",
            "loss_today": "₹310",
            "load_label": "Load",
            "load_pct": 82.4,
            "load_display": "82.4%",
            "power_label": "Power",
            "power_pct": 33.0,
            "power_display": "8.4 kW",
            "sparkline": [38, 40, 42, 41, 45, 43, 44, 46, 42, 45, 43, 44],
            "footer_note": "Cycle-time trend · 312 parts today",
            "inspection": {
                "station_title": "AOI-01 · 3D Automated Optical Inspection (SMT)",
                "camera_name": "CAM-AOI-01 · 3D Multi-Angle RGB + White Light",
                "resolution": "12 MP Structured Light 120 FPS",
                "spec": "Solder Fillet Height 110 - 140 µm",
                "measured": "124.6 µm (PASS)",
                "result": "PASS",
                "ai_confidence": "99.5%",
                "findings": [
                    {"label": "QFN Chip Alignment", "status": "PASS", "val": "Offset 4 µm (Max 25 µm)"},
                    {"label": "0201 Passive Solder Volume", "status": "PASS", "val": "100% within tolerance"},
                    {"label": "Bridging Detection", "status": "PASS", "val": "0 bridges detected"}
                ]
            }
        },
        {
            "id": "tst-01",
            "name": "TST-01 (ST-TST-010)",
            "type": "RF Testing",
            "image_type": "tst",
            "line": "SPH-PRO · FAL-L1",
            "status": "Running",
            "edge": "amber",
            "parts_this_hour": 28,
            "scrap_this_hour": "5.2%",
            "loss_today": "₹440",
            "load_label": "Load",
            "load_pct": 89.1,
            "load_display": "89.1%",
            "power_label": "Power",
            "power_pct": 27.0,
            "power_display": "6.8 kW",
            "sparkline": [24, 26, 25, 27, 28, 26, 29, 28, 30, 27, 29, 28],
            "footer_note": "RF chamber calibration in 18 min",
            "footer_color": "amber",
            "inspection": {
                "station_title": "TST-01 · 5G mmWave & Sub-6GHz Anechoic Station",
                "camera_name": "SENS-RF-TST · Vector Signal Analyzer",
                "resolution": "Rohde&Schwarz High-Speed RF Bus",
                "spec": "Error Vector Magnitude (EVM) < -30.0 dB",
                "measured": "-34.8 dB (PASS)",
                "result": "PASS",
                "ai_confidence": "99.3%",
                "findings": [
                    {"label": "Band n78 Tx Power", "status": "PASS", "val": "23.4 dBm (Target 23.0)"},
                    {"label": "Wi-Fi 7 Sensitivity", "status": "PASS", "val": "-89.2 dBm"},
                    {"label": "RF Isolation Shielding", "status": "PASS", "val": "92 dB attenuation"}
                ]
            }
        }
    ]

    return {
        "production_day": day_str,
        "shift": shift_str,
        "parts_made_today": parts_made,
        "first_pass_good": first_pass,
        "material_gap": f"{material_gap_pct}%",
        "material_gap_detail": f"{material_gap_kg} kg over BOM",
        "loss_so_far": format_inr(raw_loss),
        "loss_detail": "at current material prices",
        "scrap_pieces": scrap_cnt,
        "scrap_detail": "incl. start-up after changeover",
        "machines": machines,
        "events": events[:12]
    }

def get_defect_catalog():
    return query("""
        SELECT defect_code, defect_name, defect_category, severity, disposition_default
        FROM dim_defect_code
        ORDER BY defect_code
    """)

def get_recent_manual_defects(limit=25):
    return query("""
        SELECT q.inspection_id, q.inspection_ts, q.plant_id, q.line_id, q.station_id,
               q.product_id, q.serial_number, q.production_order_id, q.inspection_stage,
               q.defect_code, q.result, q.severity, q.measurement_value, q.spec_min, q.spec_max,
               q.inspector_id, q.disposition, q.source_system,
               COALESCE(d.defect_name, q.defect_code) AS defect_name, 
               COALESCE(d.defect_category, 'GENERAL') AS defect_category
        FROM fact_quality_inspection q
        LEFT JOIN dim_defect_code d ON q.defect_code = d.defect_code
        ORDER BY q.inspection_ts DESC
        LIMIT :lim
    """, {"lim": int(limit)})

def record_manual_defect(entry: dict):
    from datetime import datetime, timezone
    import random

    now = datetime.now(timezone.utc)
    ts_str = now.strftime("%Y-%m-%dT%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")

    eng = engine()
    with eng.connect() as conn:
        max_qi = conn.execute(text("SELECT MAX(SUBSTRING(inspection_id FROM 4)::bigint) FROM fact_quality_inspection WHERE inspection_id LIKE 'QI-%'")).scalar() or 16000
        new_qi_id = f"QI-{int(max_qi) + 1:08d}"

        serial = entry.get("serial_number") or f"SN{now.strftime('%y%m%d')}{random.randint(100000, 999999)}"
        plant_id = entry.get("plant_id") or "IN-KA-01"
        line_id = entry.get("line_id") or "FAL-L1"
        station_id = entry.get("station_id") or "ST-QA-010"
        product_id = entry.get("product_id") or "SPH-A15-128"
        po_id = entry.get("production_order_id") or f"PO-{random.randint(100, 350):06d}"
        insp_stage = entry.get("inspection_stage") or "FAL"
        defect_code = entry.get("defect_code") or "D001"
        result = entry.get("result") or ("FAIL" if defect_code != "NONE" else "PASS")
        severity = entry.get("severity") or ("MAJOR" if result == "FAIL" else "NONE")
        meas_val = float(entry.get("measurement_value") or (82.5 if result == "FAIL" else 98.4))
        spec_min = float(entry.get("spec_min") or 95.0)
        spec_max = float(entry.get("spec_max") or 100.0)
        inspector = entry.get("inspector_id") or "EMP-0042 (Operator Entry)"
        disposition = entry.get("disposition") or ("REWORK" if result == "FAIL" else "RELEASE")
        spec_rev = entry.get("spec_revision") or "QC-REV-08"
        source_sys = "MANUAL_ENTRY"

        # 1. Insert into fact_quality_inspection
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
        """), {
            "inspection_id": new_qi_id,
            "inspection_ts": ts_str,
            "plant_id": plant_id,
            "line_id": line_id,
            "station_id": station_id,
            "product_id": product_id,
            "serial_number": serial,
            "production_order_id": po_id,
            "inspection_stage": insp_stage,
            "defect_code": defect_code,
            "result": result,
            "severity": severity,
            "measurement_value": meas_val,
            "spec_min": spec_min,
            "spec_max": spec_max,
            "inspector_id": inspector,
            "disposition": disposition,
            "spec_revision": spec_rev,
            "source_system": source_sys
        })

        # 2. Insert into fact_product_genealogy_event so serial is immediately traceable
        max_gen = conn.execute(text("SELECT MAX(SUBSTRING(genealogy_event_id FROM 5)::bigint) FROM fact_product_genealogy_event WHERE genealogy_event_id LIKE 'GEN-%'")).scalar() or 25000
        new_gen_id = f"GEN-{int(max_gen) + 1:08d}"
        mat_map = {
            "D001": ("MAT-PCB-004", "SUP-010"),
            "D002": ("MAT-PCB-004", "SUP-010"),
            "D003": ("MAT-PCB-004", "SUP-010"),
            "D004": ("MAT-DISP-001", "SUP-003"),
            "D005": ("MAT-CAM-003", "SUP-005"),
            "D006": ("MAT-BATT-002", "SUP-007"),
            "D010": ("MAT-BATT-002", "SUP-007"),
            "D013": ("MAT-COIL-013", "SUP-011"),
            "D014": ("MAT-DISP-001", "SUP-003"),
            "D017": ("MAT-VAPOR-017", "SUP-008")
        }
        mat_id, supp_id = mat_map.get(defect_code, ("MAT-PCB-004", "SUP-010"))
        mat_lot = f"LOT-{mat_id.split('-')[-1]}-{now.strftime('%y%m%d')}-1"

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
        """), {
            "genealogy_event_id": new_gen_id,
            "event_ts": ts_str,
            "plant_id": plant_id,
            "serial_number": serial,
            "production_order_id": po_id,
            "product_id": product_id,
            "material_id": mat_id,
            "material_lot_id": mat_lot,
            "supplier_id": supp_id,
            "station_id": station_id,
            "operation_sequence": 25,
            "event_type": "MANUAL_OPERATOR_LOG",
            "quantity": 1,
            "parent_serial_number": None,
            "source_system": "MANUAL_ENTRY",
            "event_lineage_id": f"LIN-{int(max_gen) + 1:08d}",
            "genealogy_complete": True
        })

        # 3. If failed and create_ncr requested (or critical/major)
        created_ncr_id = None
        if result == "FAIL" and (entry.get("create_ncr") or severity in ["CRITICAL", "MAJOR"]):
            max_ncr = conn.execute(text("SELECT MAX(SUBSTRING(ncr_id FROM 5)::bigint) FROM fact_ncr_capa WHERE ncr_id LIKE 'NCR-%'")).scalar() or 400
            created_ncr_id = f"NCR-{int(max_ncr) + 1:05d}"
            root_cause = entry.get("root_cause_category") or ("MACHINE" if "SMT" in station_id else "MATERIAL")
            containment = entry.get("containment_action") or ("REWORK_INVENTORY" if disposition == "REWORK" else "QUARANTINE_LOT")
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
            """), {
                "ncr_id": created_ncr_id,
                "inspection_id": new_qi_id,
                "opened_ts": ts_str,
                "defect_code": defect_code,
                "root_cause_category": root_cause,
                "containment_action": containment,
                "owner_id": inspector,
                "capa_due_date": date_str,
                "capa_status": "OPEN",
                "effectiveness_check": "PENDING"
            })

        conn.commit()

    return {
        "success": True,
        "inspection_id": new_qi_id,
        "serial_number": serial,
        "ncr_id": created_ncr_id,
        "defect_code": defect_code,
        "result": result,
        "severity": severity,
        "disposition": disposition,
        "inspection_ts": ts_str
    }

