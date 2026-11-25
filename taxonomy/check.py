"""Validate taxonomy/domains/*.json against the brief. Usage: python taxonomy/check.py [domain ...]"""
import json, pathlib, re, sys
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
CAP_FIELDS = {"id", "name", "definition", "crosswalk", "onet_categories", "see_also", "notes", "tasks"}
TASK_FIELDS = {"id", "name", "definition", "inputs", "outputs", "crosswalk", "onet_products",
               "state_of_art", "open_tools", "benchmarkable", "notes"}
TOP_FIELDS = {"domain", "summary", "capabilities", "existing_function_map", "handoffs",
              "unplaced_products", "open_questions"}


def check(domain: str, structure: dict, products: set, categories: set) -> tuple[list[str], dict]:
    errs, path = [], HERE / "domains" / f"{domain}.json"
    if not path.exists():
        return [f"{path.name} missing"], {}
    try:
        d = json.loads(path.read_text())
    except json.JSONDecodeError as ex:
        return [f"not valid JSON: {ex}"], {}
    spec = next(x for x in structure["domains"] if x["id"] == domain)
    errs += [f"missing top-level field {f}" for f in TOP_FIELDS - set(d)]
    if d.get("domain") != domain:
        errs.append(f"domain is {d.get('domain')!r}")
    ids, n_tasks = set(), 0
    for c in d.get("capabilities", []):
        cid = c.get("id", "?")
        errs += [f"{cid}: missing {f}" for f in CAP_FIELDS - set(c)]
        if not ID.match(cid) or cid.count(".") != 1 or not cid.startswith(domain + "."):
            errs.append(f"bad capability id {cid}")
        if cid in ids:
            errs.append(f"duplicate id {cid}")
        ids.add(cid)
        errs += [f"{cid}: unknown O*NET category {x!r}" for x in c.get("onet_categories", []) if x not in categories]
        for x in c.get("crosswalk", []):
            if x.get("basis") not in ("fetched", "memory"):
                errs.append(f"{cid}: crosswalk basis {x.get('basis')!r}")
            if x.get("basis") == "fetched" and not x.get("url"):
                errs.append(f"{cid}: fetched crosswalk without url")
        if not c.get("tasks"):
            errs.append(f"{cid}: no tasks")
        for t in c.get("tasks", []):
            tid = t.get("id", "?")
            n_tasks += 1
            errs += [f"{tid}: missing {f}" for f in TASK_FIELDS - set(t)]
            if not ID.match(tid) or not tid.startswith(cid + "."):
                errs.append(f"bad task id {tid}")
            if tid in ids:
                errs.append(f"duplicate id {tid}")
            ids.add(tid)
            errs += [f"{tid}: product not in products.csv: {p!r}" for p in t.get("onet_products", []) if p not in products]
            if not str(t.get("benchmarkable", "")).lower().startswith(("yes", "partly", "no")):
                errs.append(f"{tid}: benchmarkable must start with yes / partly / no")
    mapped = {m.get("function") for m in d.get("existing_function_map", [])}
    for f in spec["existing_functions"]:
        if f.split(" ")[0] not in mapped:
            errs.append(f"existing function not mapped: {f}")
    for m in d.get("existing_function_map", []):
        errs += [f"existing_function_map points at unknown node {n}" for n in m.get("nodes", []) if n not in ids]
    errs += [f"unplaced product not in products.csv: {p!r}" for p in d.get("unplaced_products", []) if p not in products]
    return errs, {"capabilities": len(d.get("capabilities", [])), "tasks": n_tasks}


def main():
    structure = json.loads((HERE / "structure.json").read_text())
    p = pd.read_csv(HERE / "input" / "products.csv")
    products, categories = set(p["product"]), set(p.onet_category)
    domains = sys.argv[1:] or [d["id"] for d in structure["domains"]]
    bad = 0
    for dom in domains:
        errs, n = check(dom, structure, products, categories)
        print(f"{dom:11s} {n.get('capabilities', 0):3d} capabilities {n.get('tasks', 0):4d} tasks  {'OK' if not errs else f'{len(errs)} problems'}")
        for e in errs[:40]:
            print("    " + e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
