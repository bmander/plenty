"""Cross-domain review of taxonomy/domains/*.json: overlaps, dangling references, sourcing."""
import collections, json, pathlib, re, sys
HERE = pathlib.Path(__file__).resolve().parent
docs = {p.stem: json.loads(p.read_text()) for p in sorted((HERE / "domains").glob("*.json"))}
caps = {c["id"]: c for d in docs.values() for c in d["capabilities"]}
tasks = {t["id"]: (c["id"], t) for d in docs.values() for c in d["capabilities"] for t in c["tasks"]}
ids = set(caps) | set(tasks)
print(f"{len(docs)} domains, {len(caps)} capabilities, {len(tasks)} tasks\n")

print("== dangling see_also (points at a node that does not exist in a domain that is in)")
for cid, c in caps.items():
    for s in c.get("see_also", []):
        if s.split(".")[0] in docs and s not in ids:
            print(f"   {cid} -> {s}")

print("\n== products claimed by tasks in more than one domain")
where = collections.defaultdict(set)
for tid, (cid, t) in tasks.items():
    for p in t.get("onet_products", []):
        where[p].add(cid)
multi = {p: c for p, c in where.items() if len({x.split('.')[0] for x in c}) > 1}
for p, c in sorted(multi.items(), key=lambda kv: -len(kv[1]))[:60]:
    print(f"   {p[:48]:48s} {sorted(c)}")
print(f"   ({len(multi)} products in all; {len(where)} distinct products cited)")

print("\n== similar task names across domains")
def key(n): return frozenset(w for w in re.findall(r"[a-z]+", n.lower()) if len(w) > 3)
seen = collections.defaultdict(list)
for tid, (cid, t) in tasks.items():
    seen[key(t["name"])].append(tid)
for k, v in seen.items():
    if len({x.split('.')[0] for x in v}) > 1:
        print("   " + "  |  ".join(v))

print("\n== sourcing")
for dom, d in docs.items():
    xs = [x for c in d["capabilities"] for x in c.get("crosswalk", [])] + \
         [x for c in d["capabilities"] for t in c["tasks"] for x in t.get("crosswalk", [])]
    fetched = sum(x.get("basis") == "fetched" for x in xs)
    coded = sum(bool(x.get("code")) for x in xs)
    nox = sum(not c.get("crosswalk") for c in d["capabilities"])
    opens = sum(bool(t.get("open_tools")) for c in d["capabilities"] for t in c["tasks"])
    nt = sum(len(c["tasks"]) for c in d["capabilities"])
    bench = collections.Counter(str(t.get("benchmarkable", "")).split(":")[0].strip().lower() for c in d["capabilities"] for t in c["tasks"])
    print(f"   {dom:11s} crosswalk entries {len(xs):4d} (fetched {fetched:3d}, with code {coded:3d}); capabilities with none {nox}; "
          f"tasks with open tools {opens}/{nt}; benchmarkable {dict(bench)}")

print("\n== handoffs by target domain")
h = collections.Counter((dom, x.get("to_domain")) for dom, d in docs.items() for x in d.get("handoffs", []))
for (a, b), n in sorted(h.items()):
    print(f"   {a:11s} -> {b:11s} {n}")
print("\n== unplaced products:", {dom: len(d.get("unplaced_products", [])) for dom, d in docs.items()})
