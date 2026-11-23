import json, re
from .config import get_config
from .analytics import query
from .domo_llm import DomoTextLLM

SYSTEM = """You are Q-CORE, the Quality Management Agent for smartphone manufacturing. Your scope is quality intelligence and manufacturing excellence: inspection results, product disposition, defect patterns, non-conformance, containment, CAPA, root-cause evidence and product/component genealogy.

Use the read-only run_sql action to retrieve evidence before stating dataset-specific numbers. Never invent records, metrics, causes, supplier issues, process shifts or dates. Distinguish recorded root-cause categories from verified root causes. Recommend practical next investigation steps (5 Why, fishbone, station/process checks, supplier/material-lot checks) only as recommendations and explain what evidence supports them.

AVAILABLE TABLES AND COLUMNS:
1) fact_quality_inspection: inspection_id, inspection_ts, plant_id, line_id, station_id, product_id, serial_number, production_order_id, inspection_stage, defect_code, result, severity, measurement_value, spec_min, spec_max, inspector_id, disposition, spec_revision, source_system.
2) fact_ncr_capa: ncr_id, inspection_id, opened_ts, defect_code, root_cause_category, containment_action, owner_id, capa_due_date, capa_status, effectiveness_check.
3) dim_defect_code: defect_code, defect_name, defect_category, severity, disposition_default.
4) fact_product_genealogy_event: genealogy_event_id, event_ts, plant_id, serial_number, production_order_id, product_id, material_id, material_lot_id, supplier_id, station_id, operation_sequence, event_type, quantity, parent_serial_number, source_system, event_lineage_id, genealogy_complete.

RELATIONSHIPS: fact_quality_inspection.defect_code = dim_defect_code.defect_code; fact_ncr_capa.inspection_id = fact_quality_inspection.inspection_id; fact_ncr_capa.defect_code = dim_defect_code.defect_code; fact_product_genealogy_event.serial_number = fact_quality_inspection.serial_number. Use the supplied exact column names.

SAFETY: Never issue INSERT, UPDATE, DELETE, DDL, permission, file, or multi-statement SQL. Do not recommend or execute product release, disposition changes, CAPA closure or effectiveness approval. Human quality authority owns these decisions.

Return exactly one JSON object: {\"action\":\"run_sql\",\"input\":{\"query\":\"SELECT ...\"}} or {\"action\":\"final\",\"answer\":\"...\"}. Use one tool query at a time. When sufficient evidence is available, return a concise answer with findings, evidence, caveats and recommended next checks."""
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|do|execute|vacuum|refresh)\b",re.I)

def run_sql(q):
    q=q.strip().rstrip(';')
    if ';' in q or not re.match(r'^(select|with)\b',q,re.I) or FORBIDDEN.search(q):
        return "Blocked: only one read-only SELECT query is permitted."
    try:
        return str(query(f"SELECT * FROM ({q}) AS quality_agent_query LIMIT 50"))
    except Exception as exc:
        return f"Query error: {str(exc)[:300]}"

def ask(question, history=None):
    cfg=get_config()
    if not cfg.get("domo_token"):
        return {"answer":"The quality data workspace is available, but the AI assistant is waiting for DOMO_TOKEN in backend/.env. Add the Domo developer token and restart the backend to enable AI-powered investigations.","steps":[]}
    prompt = SYSTEM + "\n\nRecent conversation:\n" + "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in (history or [])[-6:]) + f"\n\nQuality investigation request: {question}\nReturn JSON only."
    steps=[]; scratch=[]; llm=DomoTextLLM(temperature=0,max_tokens=1300)
    for _ in range(4):
        raw=llm.invoke(prompt+"\n\nTool results so far: "+json.dumps(scratch,default=str))
        match=re.search(r"\{.*\}",raw,re.S)
        try: action=json.loads(match.group(0)) if match else {"action":"final","answer":raw}
        except Exception: return {"answer":raw,"steps":steps}
        if action.get("action")=="final": return {"answer":action.get("answer","No answer returned."),"steps":steps}
        if action.get("action")!="run_sql": return {"answer":"The model requested an unsupported action. Please rephrase the quality question.","steps":steps}
        sql=action.get("input",{}).get("query",""); result=run_sql(sql)
        steps.append({"tool":"read_only_quality_query","input":{"query":sql},"output":result[:2500]}); scratch.append(result[:5000])
    return {"answer":"The investigation reached its four-query limit. Narrow the question to a defect, plant, station, material lot or CAPA record to continue.","steps":steps}
