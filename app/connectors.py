import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

DATA_FILE = Path(__file__).resolve().parent / "connectors_data.json"

DEFAULT_CONNECTORS = [
    {
        "id": "oracle",
        "badge": "OR",
        "badge_color": "#D0382B",
        "name": "Oracle",
        "status": "Not connected",
        "tag": "warehouse",
        "source_type": "Oracle Database",
        "category": "Database · Plant data warehouse",
        "subtitle": "Database · Plant data warehouse",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "jdbc:oracle:thin:@//oracle-warehouse.foxconn.internal:1521/ORCLPDB1",
        "database_name": "DW_QUALITY_STORE",
        "auth_type": "Oracle Wallet / TLS Authentication",
        "schedule": "Hourly batch",
        "records_count": 18450,
        "last_sync_ts": "Not connected",
        "latency_ms": 28,
        "entities": [
            "Plant Batch Quarantine Events",
            "Supplier Inward Inspection Records",
            "Calibration Logs",
            "Furnace Thermal Profiles"
        ],
        "is_system": False
    },
    {
        "id": "mysql",
        "badge": "MY",
        "badge_color": "#00758F",
        "name": "MySQL",
        "status": "Not connected",
        "tag": "lineside",
        "source_type": "MySQL Database",
        "category": "Database · Line-side application database",
        "subtitle": "Database · Line-side application database",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "mysql://line-side-db.internal:3306/smt_assembly_db",
        "database_name": "smt_assembly_db",
        "auth_type": "Native Password / TLS v1.3",
        "schedule": "Every 10 min",
        "records_count": 9320,
        "last_sync_ts": "Not connected",
        "latency_ms": 16,
        "entities": [
            "SMT Reel Load Audits",
            "Feeder Splicing Logs",
            "Nozzle Maintenance Cycles",
            "Operator Shift Sign-Offs"
        ],
        "is_system": False
    },
    {
        "id": "sap",
        "badge": "SAP",
        "badge_color": "#0A6ED1",
        "name": "SAP",
        "status": "Not connected",
        "tag": "erp",
        "source_type": "SAP ERP / CMMS",
        "category": "ERP / CMMS · Work orders, notifications and costs",
        "subtitle": "ERP / CMMS · Work orders, notifications and costs",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "https://sap-gateway.plant-spb1.corp:8443/sap/opu/odata/API_MAINTENANCE_ORDER",
        "database_name": "S4H_PRD_CLIENT_100",
        "auth_type": "OAuth 2.0 / X.509 Certificate",
        "schedule": "Every 15 min",
        "records_count": 5736,
        "last_sync_ts": "Not connected",
        "latency_ms": 34,
        "entities": [
            "Maintenance Work Orders (PM01)",
            "Quality Notifications (QM02)",
            "Scrap Cost Postings (262)",
            "Production Confirmations (AFRU)"
        ],
        "is_system": False
    },
    {
        "id": "sap-hana",
        "badge": "HA",
        "badge_color": "#1B365D",
        "name": "SAP HANA",
        "status": "Not connected",
        "tag": "in-memory",
        "source_type": "SAP HANA Database",
        "category": "Database · In-memory analytics store",
        "subtitle": "Database · In-memory analytics store",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "hana://hana-db01.corp.internal:39015/HDB_QUALITY_LAKE",
        "database_name": "HDB_QUALITY_LAKE",
        "auth_type": "Kerberos / TLS",
        "schedule": "Continuous Streaming",
        "records_count": 22100,
        "last_sync_ts": "Not connected",
        "latency_ms": 11,
        "entities": [
            "Real-Time Yield Aggregates",
            "In-Memory Material Genealogy",
            "Material Lot Tracking",
            "Process Parametric Limits"
        ],
        "is_system": False
    },
    {
        "id": "excel",
        "badge": "XL",
        "badge_color": "#107C41",
        "name": "Excel",
        "status": "Not connected",
        "tag": "file",
        "source_type": "SharePoint / OneDrive Excel",
        "category": "File · Spreadsheet export for the planner",
        "subtitle": "File · Spreadsheet export for the planner",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "https://foxconn-my.sharepoint.com/teams/QualityOps/Daily_Planner_Export_2026.xlsx",
        "database_name": "Daily_Planner_Export_2026.xlsx",
        "auth_type": "Microsoft Graph OAuth 2.0",
        "schedule": "Daily 06:30",
        "records_count": 1280,
        "last_sync_ts": "Not connected",
        "latency_ms": 42,
        "entities": [
            "Shift Production Targets",
            "Manual Quality Exceptions",
            "Rework Allocation Sheet",
            "Vendor Returns Log"
        ],
        "is_system": False
    },
    {
        "id": "snowflake",
        "badge": "SF",
        "badge_color": "#29B5E8",
        "name": "Snowflake",
        "status": "Not connected",
        "tag": "warehouse",
        "source_type": "Snowflake Cloud Lakehouse",
        "category": "Warehouse · Group reporting warehouse",
        "subtitle": "Warehouse · Group reporting warehouse",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "https://foxconn_global.snowflakecomputing.com",
        "database_name": "CORP_QUALITY_DW",
        "auth_type": "Key Pair Authentication",
        "schedule": "Hourly sync",
        "records_count": 68400,
        "last_sync_ts": "Not connected",
        "latency_ms": 31,
        "entities": [
            "Global Fleet PPM Metrics",
            "Multi-Plant Yield Benchmarks",
            "Raw Material Quality Claims",
            "Executive Summaries"
        ],
        "is_system": False
    },
    {
        "id": "api",
        "badge": "API",
        "badge_color": "#2D3748",
        "name": "API",
        "status": "Not connected",
        "tag": "rest",
        "source_type": "Generic REST Webhook",
        "category": "REST · Generic webhook for any in-house system",
        "subtitle": "REST · Generic webhook for any in-house system",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "https://api.foxconn-qcore.internal/v1/webhooks/quality-events",
        "database_name": "REST_INSPECTION_GATEWAY",
        "auth_type": "Bearer Token / API Key",
        "schedule": "Real-Time Webhook",
        "records_count": 15400,
        "last_sync_ts": "Not connected",
        "latency_ms": 19,
        "entities": [
            "AOI Optical Inspection Telemetry",
            "SPI Solder Paste Thickness",
            "Torque Wrench Wireless Stream",
            "Automated Packaging Verification"
        ],
        "is_system": False
    },
    {
        "id": "siemens-opcenter",
        "badge": "OP",
        "badge_color": "#008080",
        "name": "Siemens Opcenter MES",
        "status": "Not connected",
        "tag": "mes",
        "source_type": "Siemens Opcenter MES",
        "category": "MES · Production orders, downtime and line state",
        "subtitle": "MES · Production orders, downtime and line state",
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": "opcenter.plant.foxconn.internal:8080/MES_SERVICES/v2",
        "database_name": "OPCENTER_EXECUTION_EBR",
        "auth_type": "Industrial SSO / SAML 2.0",
        "schedule": "Every 5 min",
        "records_count": 31200,
        "last_sync_ts": "Not connected",
        "latency_ms": 17,
        "entities": [
            "Line OEE & Stoppage Codes",
            "Routing Step Verifications",
            "Electronic Batch Records (eBR)",
            "WIP Carrier Serialization"
        ],
        "is_system": False
    },
    {
        "id": "ms-teams",
        "badge": "MT",
        "badge_color": "#505AC9",
        "name": "Microsoft Teams",
        "status": "Not connected",
        "tag": "messaging",
        "source_type": "Microsoft Teams Webhook",
        "category": "Messaging · Shift handover channel",
        "subtitle": "Messaging · Shift handover channel",
        "events_count": 3,
        "events_text": "3 events available",
        "details": "Not connected · 3 events available",
        "endpoint": "https://outlook.office.com/webhook/qcore-containment-alerts",
        "database_name": "Teams Webhook Channel",
        "auth_type": "Webhook Secret",
        "schedule": "Instant Broadcast",
        "records_count": 410,
        "last_sync_ts": "Not connected",
        "latency_ms": 22,
        "entities": [
            "Critical Containment Orders",
            "P1 Line-Stop Broadcasts",
            "Shift Quality Handover Digest"
        ],
        "is_system": False
    },
    {
        "id": "power-bi",
        "badge": "BI",
        "badge_color": "#DDA006",
        "name": "Microsoft Power BI",
        "status": "Not connected",
        "tag": "reporting",
        "source_type": "Microsoft Power BI REST",
        "category": "Reporting · Leadership dashboards",
        "subtitle": "Reporting · Leadership dashboards",
        "events_count": 3,
        "events_text": "3 events available",
        "details": "Not connected · 3 events available",
        "endpoint": "https://app.powerbi.com/groups/foxconn-quality/reports",
        "database_name": "Power BI Embedded Workspace",
        "auth_type": "Service Principal / Azure AD",
        "schedule": "Daily 07:00 Refresh",
        "records_count": 680,
        "last_sync_ts": "Not connected",
        "latency_ms": 36,
        "entities": [
            "Executive Quality Dashboards",
            "Executive Incident Heatmaps",
            "Supplier Scorecards"
        ],
        "is_system": False
    }
]

def load_connectors() -> List[Dict[str, Any]]:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) >= 10:
                    return data
        except Exception:
            pass
    save_connectors(DEFAULT_CONNECTORS)
    return DEFAULT_CONNECTORS

def save_connectors(items: List[Dict[str, Any]]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except Exception as e:
        print(f"Error saving connectors: {e}")

def get_connector(conn_id: str) -> Optional[Dict[str, Any]]:
    conns = load_connectors()
    for c in conns:
        if c["id"] == conn_id:
            return c
    return None

def toggle_connector_status(conn_id: str) -> Dict[str, Any]:
    conns = load_connectors()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for c in conns:
        if c["id"] == conn_id:
            if c["status"] == "Connected":
                c["status"] = "Not connected"
                c["last_sync_ts"] = "Not connected"
                c["details"] = f"Not connected · {c.get('events_text', '4 events available')}"
                msg = f"Connector '{c['name']}' disconnected."
            else:
                c["status"] = "Connected"
                c["last_sync_ts"] = "Just now"
                c["details"] = f"Connected ({now_str}) · {c.get('records_count', 1200):,} records indexed · All events active"
                msg = f"Connector '{c['name']}' successfully connected & authenticated."
            save_connectors(conns)
            return {"ok": True, "connector": c, "message": msg}
    return {"ok": False, "error": f"Connector {conn_id} not found."}

def sync_connector(conn_id: str) -> Dict[str, Any]:
    conns = load_connectors()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for c in conns:
        if c["id"] == conn_id:
            c["status"] = "Connected"
            c["records_count"] = c.get("records_count", 1000) + 120
            c["last_sync_ts"] = "Just now"
            c["details"] = f"Last sync just now ({now_str}) · {c['records_count']:,} records synchronized"
            c["tag"] = "synced"
            save_connectors(conns)
            return {
                "ok": True,
                "connector": c,
                "message": f"Successfully synced connector '{c['name']}'. Ingested {c['records_count']:,} records."
            }
    return {"ok": False, "error": f"Connector {conn_id} not found."}

def test_connector(conn_id: str) -> Dict[str, Any]:
    conns = load_connectors()
    for c in conns:
        if c["id"] == conn_id:
            import random
            latency = random.randint(12, 36)
            return {
                "ok": True,
                "connector_id": conn_id,
                "status": c["status"],
                "latency_ms": latency,
                "protocol": c.get("auth_type", "Standard TLS Handshake"),
                "message": f"Ping to {c['name']} host succeeded ({latency} ms). Handshake verified."
            }
    return {"ok": False, "error": f"Connector {conn_id} not found."}

def add_connector(data: Dict[str, Any]) -> Dict[str, Any]:
    conns = load_connectors()
    slug = data.get("name", "custom-source").lower().replace(" ", "-").replace("/", "-")
    cid = f"conn-{slug[:18]}-{int(time.time())}"
    
    source_type = data.get("source_type", "Custom Database")
    badge_map = {
        "Oracle": ("OR", "#D0382B"),
        "MySQL": ("MY", "#00758F"),
        "SAP": ("SAP", "#0A6ED1"),
        "SAP HANA": ("HA", "#1B365D"),
        "Excel": ("XL", "#107C41"),
        "Snowflake": ("SF", "#29B5E8"),
        "API": ("API", "#2D3748"),
        "Siemens Opcenter MES": ("OP", "#008080"),
        "Microsoft Teams": ("MT", "#505AC9"),
        "Microsoft Power BI": ("BI", "#DDA006")
    }
    badge, badge_color = badge_map.get(source_type, (source_type[:2].upper(), "#6F3DBA"))

    new_conn = {
        "id": cid,
        "badge": badge,
        "badge_color": badge_color,
        "name": data.get("name", "New Data Source"),
        "status": "Not connected",
        "tag": "custom",
        "source_type": source_type,
        "category": data.get("category", f"{source_type} · Custom integration"),
        "subtitle": data.get("category", f"{source_type} · Custom integration"),
        "events_count": 4,
        "events_text": "4 events available",
        "details": "Not connected · 4 events available",
        "endpoint": data.get("endpoint", "localhost:5432/db"),
        "database_name": data.get("database_name", "PROD_DB"),
        "auth_type": data.get("auth_type", "Standard Auth"),
        "schedule": data.get("schedule", "Hourly"),
        "records_count": 0,
        "last_sync_ts": "Not connected",
        "latency_ms": 25,
        "entities": [e.strip() for e in data.get("entities_str", "Core tables").split(",")],
        "is_system": False
    }
    conns.append(new_conn)
    save_connectors(conns)
    return {"ok": True, "connector": new_conn}

def edit_connector(conn_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    conns = load_connectors()
    for i, c in enumerate(conns):
        if c["id"] == conn_id:
            c["name"] = data.get("name", c["name"])
            c["endpoint"] = data.get("endpoint", c["endpoint"])
            c["database_name"] = data.get("database_name", c["database_name"])
            c["schedule"] = data.get("schedule", c["schedule"])
            c["auth_type"] = data.get("auth_type", c.get("auth_type", "Standard Auth"))
            if "source_type" in data:
                c["source_type"] = data["source_type"]
            save_connectors(conns)
            return {"ok": True, "connector": c}
    return {"ok": False, "error": f"Connector {conn_id} not found."}

def remove_connector(conn_id: str) -> Dict[str, Any]:
    conns = load_connectors()
    filtered = [c for c in conns if c["id"] != conn_id or c.get("is_system")]
    if len(filtered) == len(conns):
        return {"ok": False, "error": "Cannot remove default connector or connector not found."}
    save_connectors(filtered)
    return {"ok": True, "message": f"Connector {conn_id} removed."}
