from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .config import get_config, get_cors_origins
from .db import test_connection, engine, start_keep_alive
from .loader import load_datasets
from . import analytics
from .agent import ask
from .live_generator import streamer
from .workflow_engine import execute_agent_workflow, get_latest_run, get_latest_report, send_department_head_report, get_available_production_dates

_cached_counts = {}

def get_table_counts():
    global _cached_counts
    try:
        q = """
        SELECT 
          (SELECT COUNT(*) FROM fact_quality_inspection) AS fact_quality_inspection,
          (SELECT COUNT(*) FROM fact_ncr_capa) AS fact_ncr_capa,
          (SELECT COUNT(*) FROM dim_defect_code) AS dim_defect_code,
          (SELECT COUNT(*) FROM fact_product_genealogy_event) AS fact_product_genealogy_event
        """
        rows = analytics.query(q)
        if rows:
            _cached_counts = {k: int(v or 0) for k, v in rows[0].items()}
    except Exception:
        pass
    return _cached_counts

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Start Neon serverless keep-alive worker
    start_keep_alive()

    # 2. Check database connection and auto-seed if empty
    try:
        cfg = get_config()
        if cfg.get("database_url"):
            test_connection()
            counts = get_table_counts()
            if len(counts) < 4 or any(c == 0 for c in counts.values()):
                load_datasets()
                get_table_counts()
    except Exception as exc:
        print(f"Neon startup connection check notice: {exc}")

    # 3. Start real-time live data streaming worker (inserts records every 60s)
    streamer.start()

    yield

    streamer.stop()

app = FastAPI(
    title="Quality Management Agent API",
    version="2.0.0",
    description="Smartphone manufacturing quality intelligence, inspection, NCR/CAPA, genealogy, and autonomous agent services.",
    lifespan=lifespan
)

cors_origins = get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)

class FilterParams(BaseModel):
    date_preset: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    shifts: Optional[List[str]] = None
    line_id: Optional[str] = None
    station_id: Optional[str] = None
    product_id: Optional[str] = None
    from_hour: Optional[int] = None
    to_hour: Optional[int] = None
    granularity: Optional[str] = "week"

class InspectionsFilterIn(FilterParams):
    limit: Optional[int] = 250
    search: Optional[str] = None

class InvestigationIn(BaseModel):
    defect_code: Optional[str] = None
    filters: Optional[FilterParams] = None

class ChatIn(BaseModel):
    message: str
    history: list[dict] = []

class TraceIn(BaseModel):
    serial_number: str

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Quality Management Agent"}

@app.get("/api/system/status")
def system_status():
    cfg = get_config()
    db_ok = False
    db_error = None
    counts = _cached_counts
    if cfg.get('database_url'):
        try:
            test_connection()
            db_ok = True
            if not counts or len(counts) < 4:
                counts = get_table_counts()
        except Exception as e:
            db_error = str(e)[:220]

    streamer_status = streamer.get_status()
    return {
        "database_configured": bool(cfg.get('database_url')),
        "database_connected": db_ok,
        "database_error": db_error,
        "domo_configured": bool(cfg.get('domo_token')),
        "datasets_loaded": len(counts) == 4 and all(c > 0 for c in counts.values()),
        "counts": counts,
        "live_streamer": streamer_status
    }

@app.get("/api/filters/options")
def get_filter_options():
    try:
        return analytics.filter_options()
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.get("/api/dashboard")
def get_dashboard(
    date_preset: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    shifts: Optional[str] = None,
    line_id: Optional[str] = None,
    station_id: Optional[str] = None,
    product_id: Optional[str] = None,
    from_hour: Optional[int] = None,
    to_hour: Optional[int] = None,
    granularity: Optional[str] = "week"
):
    try:
        f = {
            "date_preset": date_preset,
            "start_date": start_date,
            "end_date": end_date,
            "shifts": shifts.split(",") if shifts else None,
            "line_id": line_id,
            "station_id": station_id,
            "product_id": product_id,
            "from_hour": from_hour,
            "to_hour": to_hour,
            "granularity": granularity or "week",
        }
        return analytics.dashboard(f)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.post("/api/dashboard")
def post_dashboard(body: FilterParams):
    try:
        return analytics.dashboard(body.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.get("/api/inspections")
def get_inspections(
    limit: int = 250,
    search: Optional[str] = None,
    date_preset: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    shifts: Optional[str] = None,
    line_id: Optional[str] = None,
    station_id: Optional[str] = None,
    product_id: Optional[str] = None,
    from_hour: Optional[int] = None,
    to_hour: Optional[int] = None
):
    try:
        f = {
            "date_preset": date_preset,
            "start_date": start_date,
            "end_date": end_date,
            "shifts": shifts.split(",") if shifts else None,
            "line_id": line_id,
            "station_id": station_id,
            "product_id": product_id,
            "from_hour": from_hour,
            "to_hour": to_hour,
        }
        return analytics.inspections(limit, search, f)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.post("/api/inspections")
def post_inspections(body: InspectionsFilterIn):
    try:
        f = body.model_dump()
        limit = f.pop("limit", 250)
        search = f.pop("search", None)
        return analytics.inspections(limit, search, f)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

class AcceptCapaIn(BaseModel):
    user_name: Optional[str] = "Dr. Ananya Sharma"
    user_role: Optional[str] = "Quality Assurance Director"

class BatchAcceptIn(BaseModel):
    ncr_ids: Optional[List[str]] = None
    count: Optional[int] = 5
    user_name: Optional[str] = "Dr. Ananya Sharma"
    user_role: Optional[str] = "Quality Assurance Director"

@app.get("/api/capa")
def get_capa(limit: int = 500):
    try:
        return analytics.capa_records(limit)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.post("/api/capa/{ncr_id}/accept")
def accept_capa(ncr_id: str, body: Optional[AcceptCapaIn] = None):
    try:
        user_name = body.user_name if body else "Dr. Ananya Sharma"
        user_role = body.user_role if body else "Quality Assurance Director"
        return analytics.accept_capa_effectiveness(ncr_id, user_name, user_role)
    except Exception as e:
        raise HTTPException(500, f"Failed to accept CAPA effectiveness: {str(e)[:300]}")

@app.post("/api/capa/batch-accept")
def batch_accept_capas(body: Optional[BatchAcceptIn] = None):
    try:
        ncr_ids = body.ncr_ids if body else None
        count = body.count if body else 5
        user_name = body.user_name if body else "Dr. Ananya Sharma"
        user_role = body.user_role if body else "Quality Assurance Director"
        return analytics.batch_accept_effectiveness(ncr_ids, count, user_name, user_role)
    except Exception as e:
        raise HTTPException(500, f"Failed to batch accept CAPAs: {str(e)[:300]}")

@app.get("/api/investigation")
def get_investigation(
    defect_code: Optional[str] = None,
    date_preset: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    shifts: Optional[str] = None,
    line_id: Optional[str] = None,
    station_id: Optional[str] = None,
    product_id: Optional[str] = None
):
    try:
        f = {
            "date_preset": date_preset,
            "start_date": start_date,
            "end_date": end_date,
            "shifts": shifts.split(",") if shifts else None,
            "line_id": line_id,
            "station_id": station_id,
            "product_id": product_id,
        }
        return analytics.defect_investigation(defect_code, f)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.post("/api/investigation")
def post_investigation(body: InvestigationIn):
    try:
        f = body.filters.model_dump() if body.filters else None
        return analytics.defect_investigation(body.defect_code, f)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.get("/api/alerts")
def alerts():
    try:
        return analytics.quality_alerts()
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.post("/api/trace")
def post_trace(body: TraceIn):
    try:
        return analytics.trace(body.serial_number)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.get("/api/trace")
def get_trace_query(serial_number: Optional[str] = None, serial: Optional[str] = None):
    sn = serial_number or serial
    if not sn:
        raise HTTPException(400, "serial_number parameter is required")
    try:
        return analytics.trace(sn)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

@app.get("/api/trace/{serial_number}")
def get_trace_by_serial(serial_number: str):
    try:
        return analytics.trace(serial_number)
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

class AgentRunIn(BaseModel):
    target_date: Optional[str] = None

# Agent Workflow Endpoints
@app.get("/api/agent/dates")
def get_production_dates():
    try:
        return get_available_production_dates()
    except Exception as e:
        raise HTTPException(500, f"Failed to retrieve dates: {str(e)[:300]}")

@app.post("/api/agent/run")
def run_agent(body: Optional[AgentRunIn] = None, target_date: Optional[str] = None):
    try:
        dt = (body.target_date if body else None) or target_date
        return execute_agent_workflow(target_date=dt)
    except Exception as e:
        raise HTTPException(500, f"Agent workflow execution failed: {str(e)[:300]}")

@app.get("/api/agent/latest")
def get_latest_agent_run(target_date: Optional[str] = None):
    run = get_latest_run(target_date=target_date)
    if not run:
        # If no run has been executed yet, trigger one automatically so initial state is populated
        return execute_agent_workflow(target_date=target_date)
    return run

@app.get("/api/agent/report")
def get_department_report(target_date: Optional[str] = None):
    return get_latest_report(target_date=target_date)

@app.post("/api/agent/report/send")
def send_report(body: dict):
    report_id = body.get("report_id", "")
    sender_name = body.get("sender_name", "Rajesh Kumar (Lead Quality Engineer)")
    return send_department_head_report(report_id, sender_name)

# Real-time Live Streamer Endpoints
@app.get("/api/live/status")
def get_live_status():
    return streamer.get_status()

@app.get("/api/shopfloor/live")
def get_shopfloor_live():
    try:
        return analytics.get_shopfloor_live()
    except Exception as e:
        raise HTTPException(500, f"Shop floor data fetch failed: {str(e)[:300]}")

@app.post("/api/live/tick")
def trigger_live_tick():
    try:
        res = streamer.execute_tick()
        get_table_counts()
        return {"ok": True, "result": res}
    except Exception as e:
        raise HTTPException(500, f"Live tick failed: {str(e)[:300]}")

@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        return ask(body.message, body.history)
    except Exception as e:
        raise HTTPException(502, f"AI request failed: {str(e)[:300]}")

@app.post("/api/data/load")
def load_data():
    try:
        test_connection()
        res = load_datasets()
        get_table_counts()
        return {"ok": True, "loaded": res}
    except Exception as e:
        raise HTTPException(400, str(e)[:400])

# ============================================================================
# MULTI-DATABASE CONNECTORS ENDPOINTS (Matching User Configured Sources)
# ============================================================================
from .connectors import (
    load_connectors, get_connector, sync_connector, test_connector,
    add_connector, edit_connector, remove_connector, toggle_connector_status
)

@app.get("/api/connectors")
def get_connectors():
    return load_connectors()

@app.post("/api/connectors/{conn_id}/connect")
def trigger_connector_connect(conn_id: str):
    res = toggle_connector_status(conn_id)
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Toggle failed"))
    return res

@app.post("/api/connectors/{conn_id}/sync")
def trigger_connector_sync(conn_id: str):
    res = sync_connector(conn_id)
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Sync failed"))
    return res

@app.post("/api/connectors/{conn_id}/test")
def trigger_connector_test(conn_id: str):
    res = test_connector(conn_id)
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Test failed"))
    return res

@app.post("/api/connectors")
def create_new_connector(body: dict):
    return add_connector(body)

@app.put("/api/connectors/{conn_id}")
def update_connector(conn_id: str, body: dict):
    res = edit_connector(conn_id, body)
    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Update failed"))
    return res

@app.delete("/api/connectors/{conn_id}")
def delete_connector(conn_id: str):
    res = remove_connector(conn_id)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "Delete failed"))
    return res

# ============================================================================
# MANUAL USER INPUT DEFECT ENDPOINTS
# ============================================================================
class ManualDefectIn(BaseModel):
    plant_id: Optional[str] = "IN-KA-01"
    line_id: Optional[str] = "FAL-L1"
    station_id: Optional[str] = "ST-QA-010"
    product_id: Optional[str] = "SPH-A15-128"
    serial_number: Optional[str] = None
    production_order_id: Optional[str] = None
    inspection_stage: Optional[str] = "FAL"
    defect_code: Optional[str] = "D001"
    defect_name: Optional[str] = None
    result: Optional[str] = "FAIL"
    severity: Optional[str] = "MAJOR"
    measurement_value: Optional[float] = 82.5
    spec_min: Optional[float] = 95.0
    spec_max: Optional[float] = 100.0
    inspector_id: Optional[str] = "EMP-0042 (Operator Entry)"
    disposition: Optional[str] = "REWORK"
    spec_revision: Optional[str] = "QC-REV-08"
    notes: Optional[str] = None
    create_ncr: Optional[bool] = True
    root_cause_category: Optional[str] = "MACHINE"
    containment_action: Optional[str] = "REWORK_INVENTORY"

@app.get("/api/defects/catalog")
def get_defects_catalog():
    try:
        return analytics.get_defect_catalog()
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch defect catalog: {str(e)[:300]}")

@app.get("/api/defects/recent")
def get_recent_defects(limit: int = 25):
    try:
        return analytics.get_recent_manual_defects(limit)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch recent defects: {str(e)[:300]}")

@app.post("/api/defects/manual-entry")
def post_manual_defect(body: ManualDefectIn):
    try:
        res = analytics.record_manual_defect(body.model_dump())
        get_table_counts()
        return res
    except Exception as e:
        raise HTTPException(500, f"Failed to record manual defect: {str(e)[:300]}")


