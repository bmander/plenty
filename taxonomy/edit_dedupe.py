"""Editor's pass 1: one owner for each task that two domains modeled. Run once; logs to EDITS.md."""
import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
if (HERE / "EDITS.md").exists():
    sys.exit("already applied (EDITS.md exists); kept as the record of what pass 1 did")
docs = {p.stem: json.loads(p.read_text()) for p in (HERE / "domains").glob("*.json")}

def find(cap_id, name):
    dom = cap_id.split(".")[0]
    cap = next(c for c in docs[dom]["capabilities"] if c["id"] == cap_id)
    hits = [t for t in cap["tasks"] if t["name"] == name]
    assert len(hits) == 1, (cap_id, name, [t["name"] for t in cap["tasks"]])
    return cap, hits[0]

# (capability, task name to remove) -> (capability, task name that keeps it), reason
MERGE = [
 ("simulate.design_exploration", "Tolerance stack-up analysis", "design.product_definition", "Tolerance stack-up and variation analysis", "tolerancing is part of the product definition"),
 ("produce.metrology", "Tolerance stack-up analysis", "design.product_definition", "Tolerance stack-up and variation analysis", "tolerancing is part of the product definition"),
 ("produce.process_planning", "Manufacturability analysis", "design.product_definition", "Design for manufacture and assembly review", "the review is of the design"),
 ("design.estimating", "Parametric and should-cost estimating", "produce.process_planning", "Manufacturing cost estimation", "product cost follows the process plan; design.estimating keeps construction"),
 ("produce.additive_prep", "Mesh preparation and repair", "design.geometry_exchange", "Tessellation and mesh repair", "same operation on the same data"),
 ("earth.mining", "Mine ventilation planning", "simulate.pipe_networks", "Mine and tunnel ventilation network analysis", "an engineered network"),
 ("earth.atmosphere", "Air emissions estimation", "operate.environmental_compliance", "Air emissions inventory calculation", "emission inventories are a compliance function"),
 ("move.supply_chain_planning", "Spare parts provisioning for availability", "operate.asset_strategy", "Critical spares optimization", "spares follow the asset strategy"),
 ("computing.operating_systems", "Screen reading and magnification", "learn.assistive_access", "Screen reading", "assistive technology has one home"),
 ("computing.storage", "File synchronization and sharing", "enterprise.communication", "File synchronization and sharing", "an end-user collaboration function"),
 ("media.web_publishing", "Collaborative wiki authoring", "enterprise.documents", "Team wiki and knowledge base", "same function"),
 ("enterprise.authoring", "Speech dictation to text", "media.language", "Speech recognition and transcription", "recognition is one function wherever it is used"),
 ("media.vector_graphics", "Diagrams and mind maps", "enterprise.process_workflow", "Flowchart and business diagramming", "same function"),
 ("enterprise.communication", "Client appointment booking", "commerce.service_scheduling", "Customer appointment booking", "customer-facing booking"),
 ("govern.legal_practice", "Legal document assembly", "enterprise.documents", "Document assembly from templates", "same function, legal templates are one use"),
 ("govern.legal_practice", "Legal time capture and billing", "enterprise.receivables_payables", "Time and expense billing", "same function"),
 ("govern.social_services", "Vocational transferable-skills analysis", "learn.career_guidance", "Transferable skills analysis", "same function"),
 ("govern.law_enforcement", "Digital evidence examination", "computing.security_operations", "Digital forensics", "same function"),
 ("commerce.point_of_sale", "Merchant payment fraud screening", "govern.compliance_financial_crime", "Card and payment fraud detection", "same function"),
 ("move.travel_reservation", "Tour and itinerary packaging", "commerce.hospitality", "Tour and activity booking", "tours sit with hospitality; move keeps transport reservation"),
 ("commerce.merchandising", "Store demand forecasting and replenishment", "move.supply_chain_planning", "Demand forecasting for replenishment", "same forecasting problem"),
 ("science.social_research", "Psychometric item calibration", "learn.assessment", "Item analysis and test calibration", "same function"),
 ("enterprise.process_workflow", "No-code tables and forms", "computing.databases", "Desktop and end-user databases", "same function"),
 ("operate.electrical_testing", "Field instrument calibration management", "produce.metrology", "Gauge and calibration management", "same function"),
 ("commerce.service_scheduling", "Repair and service order tracking", "operate.maintenance_management", "Repair shop order management", "same function"),
 ("commerce.customer_relationship", "Customer record deduplication", "computing.data_integration", "Master data management and record matching", "entity resolution is a general data function"),
 ("learn.classroom_interaction", "Dynamic mathematics manipulatives", "science.symbolic_math", "Interactive geometry and graphing", "same tools"),
 ("enterprise.authoring", "Live audience polling and questions", "learn.classroom_interaction", "Live polling and quiz games", "same function"),
 ("enterprise.projects", "Parametric effort and cost estimation", "computing.requirements_design", "Software effort estimation", "the products are software estimators; construction and product costing have their own nodes"),
 ("produce.process_specific_prep", "Print preflight", "media.page_layout", "PDF output and preflight", "same check on the same file"),
 ("learn.course_delivery", "Virtual classroom sessions", "enterprise.communication", "Video and audio meetings", "same function"),
]
RENAME = [
 ("operate.condition_monitoring", "Operating data historian and rounds", "Operator rounds and inspection data", "the historian itself is produce.supervisory_control"),
 ("produce.supervisory_control", "Control loop tuning and performance monitoring", "Control loop performance monitoring", "tuning design is simulate.system_dynamics"),
 ("enterprise.documents", "Scanning and text recognition", "Document scanning and capture", "recognition itself is media.language"),
 ("govern.legal_practice", "Contract review and lifecycle management", "Contract review and clause analysis", "lifecycle management is enterprise.procurement"),
 ("govern.public_administration", "Customs declaration and tariff classification", "Customs declaration processing and risk targeting", "the trader's side is move.trade_compliance"),
 ("govern.law_enforcement", "Crime scene and collision diagramming and reconstruction", "Crime scene and collision diagramming", "reconstruction physics is simulate.vehicle_vessel"),
 ("produce.metrology", "Gauge and calibration management", "Gauge and instrument calibration management", "now also holds field instrument calibration"),
]
log = ["# Editor's changes to the domain files\n", "## Pass 1: one owner per task\n",
       "Each row removes a task that another domain also modeled. Its products and tools were added to the task that keeps it, and the losing capability now points at the keeper.\n",
       "| Removed | Kept in | Why |", "|---|---|---|"]
for src_cap, src_name, keep_cap, keep_name, why in MERGE:
    sc, st = find(src_cap, src_name)
    kc, kt = find(keep_cap, keep_name)
    for f in ("onet_products", "state_of_art", "open_tools"):
        kt[f] = list(dict.fromkeys(list(kt.get(f, [])) + list(st.get(f, []))))
    sc["tasks"].remove(st)
    if keep_cap not in sc.setdefault("see_also", []):
        sc["see_also"].append(keep_cap)
    log.append(f"| `{st['id']}` {src_name} | `{kt['id']}` | {why} |")
log += ["\n## Pass 1: renames\n", "| Task | Was | Now | Why |", "|---|---|---|---|"]
for cap, old, new, why in RENAME:
    c, t = find(cap, old)
    t["name"] = new
    t["notes"] = (t.get("notes", "") + f" Editor: renamed from '{old}'; {why}.").strip()
    log.append(f"| `{t['id']}` | {old} | {new} | {why} |")
for dom, d in docs.items():
    (HERE / "domains" / f"{dom}.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
(HERE / "EDITS.md").write_text("\n".join(log) + "\n")
print(len(MERGE), "merged,", len(RENAME), "renamed")
