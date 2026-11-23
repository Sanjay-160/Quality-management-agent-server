import urllib.request
import json

base = "http://127.0.0.1:8000/api"

# 1. Dates
dates_req = urllib.request.urlopen(f"{base}/agent/dates")
dates = json.loads(dates_req.read().decode())
print(f"Total available production dates: {len(dates)}")
for d in dates[:4]:
    print(f"  {d['date_iso']}: {d['date_str']}, FPY: {d['fpy']}%, Units: {d['inspections']}")

# 2. Reports for different dates
for dt in ["2026-11-13", "2026-11-08", "2026-11-02"]:
    rep_req = urllib.request.urlopen(f"{base}/agent/report?target_date={dt}")
    rep = json.loads(rep_req.read().decode())
    print(f"\nReport for {dt} ({rep['date_str']}):")
    print(f"  Report ID: {rep['report_id']}")
    print(f"  Primary Defect: {rep['primary_defect']}")
    print(f"  Affected Station/Line: {rep['worst_station']} on {rep['top_line']}")
    print(f"  Quarantined Lot: {rep['quarantined_lot']} (Supplier: {rep['supplier_id']})")
    print(f"  Key Metrics: {[m['label'] + ': ' + m['value'] for m in rep['key_metrics']]}")
    print(f"  Loss Prevented: {rep['financial_risk_mitigation']['loss_prevented']}")
    print(f"  Executive Problem Statement: {rep['executive_summary'][:150]}...")
