"""Compile taxonomy/domains/*.json into flat tables: capabilities.csv, crosswalk.csv,
products_seed.csv and function_map.csv. Usage: python taxonomy/build.py [out-dir]"""
import json, pathlib, sys
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
structure = json.loads((HERE / "structure.json").read_text())
nodes, cross, prods, funcs = [], [], [], []
for spec in structure["domains"]:
    dom = spec["id"]
    d = json.loads((HERE / "domains" / f"{dom}.json").read_text())
    nodes.append(dict(id=dom, level=0, parent="", name=spec["name"], definition=spec["scope"]))
    # the 18 functions of config/capabilities.csv and the capabilities each became
    funcs += [dict(function=m["function"], node=n, note=m.get("note", "")) for m in d["existing_function_map"] for n in m["nodes"]]
    for c in d["capabilities"]:
        nodes.append(dict(id=c["id"], level=1, parent=dom, name=c["name"], definition=c["definition"],
                          see_also="; ".join(c.get("see_also", []))))
        for x in c.get("crosswalk", []):
            cross.append(dict(node=c["id"], **{k: x.get(k, "") for k in ("scheme", "code", "label", "basis", "url")}))
        for t in c["tasks"]:
            verdict, _, why = str(t["benchmarkable"]).partition(":")
            nodes.append(dict(id=t["id"], level=2, parent=c["id"], name=t["name"], definition=t["definition"],
                              inputs=t["inputs"], outputs=t["outputs"], benchmarkable=verdict.strip().lower(),
                              benchmark_note=why.strip(), state_of_art="; ".join(t["state_of_art"]),
                              open_tools="; ".join(t["open_tools"]), onet_products=len(t["onet_products"])))
            for x in t.get("crosswalk", []):
                cross.append(dict(node=t["id"], **{k: x.get(k, "") for k in ("scheme", "code", "label", "basis", "url")}))
            prods += [dict(task=t["id"], product=p) for p in t["onet_products"]]
N = pd.DataFrame(nodes).astype(object).fillna("")
N.to_csv(OUT / "capabilities.csv", index=False)
pd.DataFrame(cross).to_csv(OUT / "crosswalk.csv", index=False)
pd.DataFrame(prods).to_csv(OUT / "products_seed.csv", index=False)
pd.DataFrame(funcs).to_csv(OUT / "function_map.csv", index=False)
print(N.level.value_counts().sort_index().to_dict(), len(cross), "crosswalk entries,", len(prods), "product citations")
