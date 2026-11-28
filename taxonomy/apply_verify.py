"""Editor's pass 3: apply the verifiers' verdicts (taxonomy/verify/*.json) to the crosswalks.

confirmed    -> basis "fetched", url of the page read
corrected    -> code/label replaced with what the source says, basis "fetched"
contradicted -> entry removed
unverifiable -> basis "memory" (whatever the author had written)
Usage: python taxonomy/apply_verify.py [--write]
"""
import collections, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
WRITE = "--write" in sys.argv
if "## Pass 3" in (HERE / "EDITS.md").read_text():
    # Verdicts are matched on the entry's original code and label, which the first run changed.
    sys.exit("already applied (EDITS.md has pass 3); running it again would mark corrected entries as unchecked")
log, totals = [], collections.Counter()
# Later checks of one scheme across domains (*_extra.json) replace the per-domain verdicts.
extra = {}
for xp in sorted((HERE / "verify").glob("*_extra.json")):
    for e in json.loads(xp.read_text())["entries"]:
        if xp.stem == "acm_extra" and "ACMG" in e["scheme"]:
            continue   # ACMG/AMP is a medical-genetics guideline, not the ACM classification
        extra[(e["node"], e["scheme"], e.get("code", ""), e.get("label", ""))] = e
for vp in sorted((HERE / "verify").glob("*.json")):
    if vp.stem.endswith("_extra"):
        continue
    dom = vp.stem
    v = json.loads(vp.read_text())
    dp = HERE / "domains" / f"{dom}.json"
    d = json.loads(dp.read_text())
    nodes = {}
    for c in d["capabilities"]:
        nodes[c["id"]] = c
        for t in c["tasks"]:
            nodes[t["id"]] = t
    verdicts = collections.defaultdict(list)
    for e in v["entries"]:
        verdicts[(e["node"], e["scheme"], e.get("code", ""), e.get("label", ""))].append(e)
    count, unmatched = collections.Counter(), 0
    for nid, node in nodes.items():
        keep = []
        for x in node.get("crosswalk", []):
            q = verdicts.get((nid, x.get("scheme", ""), x.get("code", ""), x.get("label", "")))
            if not q:
                unmatched += 1
                x["basis"], x["url"] = "memory", ""
                keep.append(x)
                continue
            e = q.pop(0)
            e = extra.get((nid, x.get("scheme", ""), x.get("code", ""), x.get("label", "")), e)
            verdict = e["verdict"]
            count[verdict] += 1
            if verdict == "confirmed":
                x["basis"], x["url"] = "fetched", e.get("url", "")
            elif verdict == "corrected":
                old = (x.get("code", ""), x.get("label", ""))
                x["code"] = e.get("correct_code") or x.get("code", "")
                x["label"] = e.get("correct_label") or x.get("label", "")
                x["basis"], x["url"] = "fetched", e.get("url", "")
                log.append(f"| `{nid}` | {x['scheme']} | {old[0]} {old[1]} | {x['code']} {x['label']} |")
            elif verdict == "contradicted":
                log.append(f"| `{nid}` | {x['scheme']} | {x.get('code', '')} {x.get('label', '')} | removed: {e.get('evidence', '') or 'not in the scheme'} |")
                continue
            else:
                x["basis"], x["url"] = "memory", ""
            if x["basis"] == "fetched" and not x["url"]:
                x["basis"] = "memory"       # a verdict without a page is not a read
                count["confirmed_without_url"] += 1
            keep.append(x)
        if "crosswalk" in node:
            node["crosswalk"] = keep
    left = sum(len(q) for q in verdicts.values())
    print(f"{dom:11s} {dict(count)}  entries without a verdict: {unmatched}; verdicts without an entry: {left}")
    totals.update(count)
    if WRITE:
        dp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("total", dict(totals))
if WRITE:
    with open(HERE / "EDITS.md", "a") as f:
        f.write("\n## Pass 3: crosswalk verification\n\nEach domain's crosswalk was checked against the published source by a separate agent "
                "(`verify/*.json`, method in `VERIFY.md`). Only entries whose source page was read are marked `fetched`; everything else is `memory`.\n\n"
                f"Totals: {dict(totals)}\n\n| Node | Scheme | Was | Now |\n|---|---|---|---|\n" + "\n".join(log) + "\n")
