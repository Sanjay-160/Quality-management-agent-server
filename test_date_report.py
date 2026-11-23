from app.db import engine
from sqlalchemy import text
from app.analytics import query

for dt in ["2026-11-13", "2026-11-12", "2026-11-08", "2026-11-02"]:
    insp = query("""
        SELECT COUNT(*) as total_insp,
               COUNT(*) FILTER (WHERE UPPER(result)='FAIL') as total_fail,
               COUNT(DISTINCT line_id) as lines,
               COUNT(DISTINCT station_id) as stations
        FROM fact_quality_inspection
        WHERE inspection_ts::date = CAST(:dt AS DATE)
    """, {"dt": dt})[0]

    top_defect = query("""
        SELECT i.defect_code, COALESCE(d.defect_name, i.defect_code) as defect_name, COUNT(*) as count
        FROM fact_quality_inspection i
        LEFT JOIN dim_defect_code d ON i.defect_code = d.defect_code
        WHERE i.inspection_ts::date = CAST(:dt AS DATE) AND UPPER(i.result) = 'FAIL' AND COALESCE(i.defect_code, 'NONE') <> 'NONE'
        GROUP BY i.defect_code, d.defect_name
        ORDER BY count DESC
        LIMIT 1
    """, {"dt": dt})

    worst_station = query("""
        SELECT station_id, line_id, COUNT(*) as failures
        FROM fact_quality_inspection
        WHERE inspection_ts::date = CAST(:dt AS DATE) AND UPPER(result) = 'FAIL'
        GROUP BY station_id, line_id
        ORDER BY failures DESC
        LIMIT 1
    """, {"dt": dt})

    top_lot = query("""
        SELECT g.material_lot_id, g.supplier_id, g.material_id, COUNT(DISTINCT g.serial_number) as affected
        FROM fact_product_genealogy_event g
        JOIN fact_quality_inspection i ON i.serial_number = g.serial_number
        WHERE i.inspection_ts::date = CAST(:dt AS DATE) AND UPPER(i.result) = 'FAIL'
        GROUP BY g.material_lot_id, g.supplier_id, g.material_id
        ORDER BY affected DESC
        LIMIT 1
    """, {"dt": dt})

    fpy = round(100.0 * (insp['total_insp'] - insp['total_fail']) / max(insp['total_insp'], 1), 2)
    def_name = top_defect[0]['defect_name'] if top_defect else "None"
    st_name = f"{worst_station[0]['station_id']} · {worst_station[0]['line_id']}" if worst_station else "None"
    lot_name = top_lot[0]['material_lot_id'] if top_lot else "None"

    print(f"Date {dt}:")
    print(f"  Inspected: {insp['total_insp']}, Failed: {insp['total_fail']}, FPY: {fpy}%")
    print(f"  Primary Defect: {def_name}")
    print(f"  Worst Station/Line: {st_name}")
    print(f"  Quarantined Lot: {lot_name}")
    print()
