"""Run the analysis and write results/*.csv, results/summary.md and figures."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from plenty import model as M, analysis as A, occupations as O, rd as RD, flows as F

OUT = M.ROOT / "results"
OUT.mkdir(exist_ok=True)

# Archetypes whose own activity is not designing, making or running physical plant.
SERVICES = {"trade", "finance_insurance", "real_estate_housing", "professional_admin",
            "education", "health_services", "social_services", "arts_recreation", "hospitality",
            "personal_civic", "government", "media_publishing", "accounting", "software_data",
            "engineering_rd", "repair_maintenance", "warehousing_postal", "air_transport",
            "rail_transport", "water_transport", "truck_transport", "transit", "telecom",
            "waste_management"}


BREADTH_MIN = 9.0
OCC_VARIANT = "occupation-based usage (O*NET x OEWS)"
CAL_VARIANT = "score weights calibrated to occupations"


def md(df, floatfmt="{:.3f}"):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].map(floatfmt.format)
    cols = [df.index.name or ""] + list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [str(v) for v in row.values]) + " |")
    return "\n".join(lines)


TOP_OCCUPATIONS = 12   # occupations listed per capability in results/capability_flow_occupations.csv


def capability_flows(m, r):
    """Where today's value flows (plenty/flows.py): each need dollar traced through sectors and
    occupations to the taxonomy's capabilities. Writes results/capability_flow*.csv and returns
    (table, accounting)."""
    com, caps = m.t.commodities, F.capabilities()
    tax = pd.read_csv(F.TAXONOMY / "capabilities.csv", dtype=str).fillna("").set_index("id")
    ls, pc = F.listings(), F.product_capabilities()
    vn = F.need_value_added(m, r)
    out = {}
    for label, distinctive in (("flow", False), ("flow_distinctive", True)):
        theta = F.occupation_shares(ls, pc, caps, distinctive)
        work = F.sector_work(com, theta)
        out[label] = (theta, work) + F.flow(vn, work, caps)
    theta, work, flow, by_need, terms = out["flow"]
    flow_d, by_need_d = out["flow_distinctive"][2], out["flow_distinctive"][3]
    work.round(10).to_csv(OUT / "capability_flow_work.csv")
    by_need.round(12).to_csv(OUT / "capability_flow_by_need.csv")
    by_need_d.round(12).to_csv(OUT / "capability_flow_distinctive_by_need.csv")

    # the occupations each flow passes through
    ov = F.occupation_value(com, vn.mean(axis=1))
    o = O.oews()
    title = o.drop_duplicates("OCC_CODE").set_index("OCC_CODE").OCC_TITLE
    th = O._occupation_uses(ov.index, theta, "mean").fillna(0.0)
    listed, in_cap = ls.groupby("soc").size(), ls.merge(pc, on="product").groupby(["soc", "capability"]).size()
    rows = []
    for k in caps:
        through = (ov * th[k]).nlargest(TOP_OCCUPATIONS)
        for code, v in through[through > 0].items():
            rows.append(dict(capability=k, occupation=code, title=title.get(code, "?"), share_of_basket=ov[code],
                             products_in_capability=int(in_cap.get((code, k), 0)), products_listed=int(listed.get(code, 0)),
                             share_of_work=th.at[code, k], flow=v))
    pd.DataFrame(rows).round(10).to_csv(OUT / "capability_flow_occupations.csv", index=False)

    table = pd.DataFrame({
        "name": tax.name.reindex(caps), "domain": [k.split(".")[0] for k in caps],
        "flow": flow, "flow_distinctive": flow_d,
        "rank": flow.rank(ascending=False, method="min").astype(int),
        "rank_distinctive": flow_d.rank(ascending=False, method="min").astype(int),
        "occupations": (theta > 0).sum().reindex(caps),
        "products": pc.groupby("capability")["product"].nunique().reindex(caps).fillna(0).astype(int),
        "top_need": by_need.idxmax(axis=1), "top_need_distinctive": by_need_d.idxmax(axis=1),
    }).sort_values("flow", ascending=False)
    table.index.name = "capability"
    table.round(12).to_csv(OUT / "capability_flow.csv")
    acct = pd.DataFrame({label: F.unattributed(vn, out[label][1], caps) for label in out}).rename_axis("part")
    acct.round(6).to_csv(OUT / "capability_flow_accounting.csv")
    return table, acct


def main():
    m = M.build()
    r = A.run(m)
    s, c = r.sectors, r.capabilities
    needs = list(r.need_totals.index)
    m0 = M.build(endogenize_capital=False)
    r0 = A.run(m0)
    # Breadth from observed intermediate purchases only. Allocated capital purchases are spread
    # over buyers by assumption, which manufactures breadth for any capital good.
    s.insert(s.columns.get_loc("need_breadth") + 1, "need_breadth_observed", r0.sectors.need_breadth)

    # The two columns the site's derivations sum over keep full precision, so the sums match.
    exact = ["output_per_need_dollar_equal", "value_added_share_equal"]
    s.round(6).assign(**{c: s[c].round(12) for c in exact}).to_csv(OUT / "sectors.csv")
    T = r.need_totals
    pd.DataFrame({"final_demand_musd": T.round(0), "share": (T / T.sum()).round(4)}).rename_axis("need").to_csv(OUT / "needs.csv")
    r.sector_by_need.round(6).to_csv(OUT / "sector_by_need.csv")
    c.round(4).to_csv(OUT / "capabilities.csv")
    r.capability_by_need.round(4).to_csv(OUT / "capability_by_need.csv")

    phys = s[~s.archetype.isin(SERVICES)]
    phys_share = phys.value_added_per_basket_dollar.sum() / s.value_added_per_basket_dollar.sum()
    phys.round(6).to_csv(OUT / "physical_sectors.csv")

    # Thin but everywhere: physical sectors whose observed sales are spread over nearly all
    # needs (breadth >= BREADTH_MIN) and that reach at least 90% of the basket at 0.03 cents per
    # dollar (a floor that drops sectors too small to register). Thinnest first.
    thin = phys[(phys["reach_0.0003"] >= 0.9) & (phys.need_breadth_observed >= BREADTH_MIN)]
    thin = thin.sort_values("output_per_basket_dollar")
    thin.round(6).to_csv(OUT / "bottleneck_candidates.csv")

    # Top physical upstream sectors per need (excluding what the need buys directly).
    basket = pd.read_csv(M.CONFIG / "basket.csv").set_index("commodity").need
    rows = []
    for n in needs:
        col = r.sector_by_need.loc[phys.index, n]
        col = col[basket.reindex(col.index) != n].sort_values(ascending=False).head(8)
        for code, val in col.items():
            rows.append(dict(need=n, commodity=code, name=s.at[code, "name"], output_per_need_dollar=val))
    upstream = pd.DataFrame(rows)
    upstream.round(5).to_csv(OUT / "top_upstream_by_need.csv", index=False)

    # Archetype totals with and without capital.
    arch = pd.DataFrame({
        "output_per_basket_dollar": s.groupby("archetype").output_per_basket_dollar.sum(),
        "without_capital": r0.sectors.groupby("archetype").output_per_basket_dollar.sum(),
    })
    arch["capital_multiplier"] = arch.output_per_basket_dollar / arch.without_capital
    arch.sort_values("output_per_basket_dollar", ascending=False).round(5).to_csv(OUT / "archetypes.csv")

    # Occupation-based usage: wage-bill share of occupations whose O*NET software list maps to k.
    matches = O.software_matches()
    titles = pd.read_csv(O.OCC / "onet_occupations.csv").set_index("O*NET-SOC Code").Title
    u = O.uses(matches, titles.index.to_series())
    cov = O.coverage(matches, titles)
    cov.to_csv(OUT / "software_coverage.csv")
    shares = O.shares(m.t.commodities, u)
    shares.round(5).to_csv(OUT / "occupation_capability_shares.csv")
    S = A.capability_scores(m.t)
    occ = A.run(m, usage=O.usage_matrix(shares, S, cov)).capabilities.weight_equal_need
    # What weight each score earns, judged by occupations: the pooled mean share at each score
    # above the score-0 baseline, scaled so a 3 weighs 1 (the elicited mapping is 0.1 / 0.3 / 1).
    levels = O.score_levels(shares, S, cov)
    cal_weight = O.calibrated_score_weight(levels)
    levels["weight_assumed"] = pd.Series(A.SCORE_WEIGHT)
    levels["weight_calibrated"] = pd.Series(cal_weight)
    levels.round(4).to_csv(OUT / "score_weight_calibration.csv")
    cal = A.run(m, score_weight=cal_weight).capabilities.weight_equal_need
    measured = shares.source == "oews"
    elicited_w = S.loc[measured].replace(A.SCORE_WEIGHT)
    base = c.weight_equal_need
    # Business R&D per dollar of output (NSF BERD 2017): a second measured check, for the
    # capabilities config/capabilities.csv marks as product-design tools (rd_proxy).
    rdi = RD.intensity(m.t)
    rdi.round(6).to_csv(OUT / "rd_intensity.csv")
    has_rd = rdi.rd_per_output.notna()
    proxy = pd.read_csv(M.CONFIG / "capabilities.csv").set_index("capability").rd_proxy.astype(bool)
    agree = pd.DataFrame({
        "spearman_across_sectors": [np.nan if cov.at[k, "thin"] else spearmanr(elicited_w[k], shares.loc[measured, k])[0]
                                    for k in S.columns],
        "spearman_rd": [spearmanr(S.loc[has_rd, k].replace(A.SCORE_WEIGHT), rdi.rd_per_output[has_rd])[0]
                        if proxy[k] else np.nan for k in S.columns],
        "thin": cov.thin,
        "elicited_weight": base,
        "occupational_weight": occ,
        "elicited_rank": base.rank(ascending=False).astype(int),
        "occupational_rank": occ.rank(ascending=False).astype(int),
    }, index=S.columns)
    agree["rank_change"] = agree.elicited_rank - agree.occupational_rank
    agree.index.name = "capability"
    agree.round(4).to_csv(OUT / "score_agreement.csv")

    # Sensitivity of the capability ranking.
    variants = {
        OCC_VARIANT: occ,
        f"{CAL_VARIANT} ({cal_weight[1]:.2f}, {cal_weight[2]:.2f}, 1)": cal,
        "linear score weights (1/3, 2/3, 1)": A.run(m, score_weight=A.SCORE_WEIGHT_LINEAR).capabilities.weight_equal_need,
        "no capital endogenization": r0.capabilities.weight_equal_need,
        "capital spread by operating surplus only (no user rules)": A.run(M.build(capital_rules=False)).capabilities.weight_equal_need,
        "needs weighted by US spending": c.weight_spending,
        "exposure through critical sectors (instead of volume)": c.exposure_mean,
    }
    top5 = set(base.sort_values(ascending=False).index[:5])
    sens = pd.DataFrame([dict(variant=k, spearman_vs_headline=spearmanr(base, v)[0],
                              top5_overlap=len(top5 & set(v.sort_values(ascending=False).index[:5])),
                              top5=", ".join(v.sort_values(ascending=False).index[:5]))
                         for k, v in variants.items()]).set_index("variant")
    sens.round(3).to_csv(OUT / "sensitivity.csv")

    ranks = pd.DataFrame({
        "volume_rank": agree.elicited_rank,
        "exposure_rank": c.exposure_mean.rank(ascending=False).astype(int),
    })
    ranks["worst_rank"] = ranks.max(axis=1)
    desc = pd.read_csv(M.CONFIG / "capabilities.csv").set_index("capability")
    ranks["occupational_rank"] = agree.occupational_rank
    ranks["calibrated_rank"] = cal.rank(ascending=False).astype(int)
    cap_table = pd.DataFrame({
        "volume weight": base, "occupational weight": occ, "calibrated weight": cal, "exposure": c.exposure_mean,
        "reach 0.1c": c["reach_0.001"], "reach 1c": c["reach_0.01"], "reach 5c": c["reach_0.05"],
        "need breadth": c.need_breadth, "most exposed need": c.most_exposed_need,
        "least exposed need": c.least_exposed_need,
    }).join(ranks).sort_values("volume weight", ascending=False)
    cap_table.index.name = "capability"
    cap_table.round(4).to_csv(OUT / "capability_table.csv")
    flows, flow_acct = capability_flows(m, r)

    # ---- summary.md
    L = []
    L.append("## Basket\n")
    nt = pd.DataFrame({"final demand ($B, 2017)": T / 1e3, "share": T / T.sum()}); nt.index.name = "need"
    L.append(md(nt, "{:.2f}"))
    L.append(f"\nTotal basket: ${T.sum()/1e6:.2f} trillion. Physical sectors (farming, extraction, "
             f"utilities, construction, manufacturing) carry {phys_share:.0%} of the value added "
             f"embodied in it; the rest is services.\n")
    L.append("## Where today's value flows (taxonomy capabilities)\n")
    L.append(f"Each need dollar traced through sectors (value added) and occupations (wage mix) to the capabilities whose "
             f"software they list. Flowed: {flow_acct.at['flowed', 'flow']:.1%} of the basket; "
             f"{flow_acct.at['sectors_without_occupation_data', 'flow']:.1%} sits in sectors with no occupational data and "
             f"{flow_acct.at['work_not_placed', 'flow']:.1%} is work the chain could not place. Top 25 of {len(flows)}:\n")
    L.append(md(flows.head(25)[["name", "flow", "flow_distinctive", "rank_distinctive", "occupations", "top_need"]], "{:.4f}"))
    L.append("\n### By domain\n")
    L.append(md(flows.groupby("domain")[["flow", "flow_distinctive"]].sum().sort_values("flow", ascending=False), "{:.4f}"))
    L.append("\n## Engineering functions (elicited scores)\n")
    show = cap_table[["volume weight", "exposure", "reach 0.1c", "reach 1c", "reach 5c",
                      "need breadth", "volume_rank", "exposure_rank"]]
    L.append(md(show))
    L.append("\n## Capability weight by need (value-added share, score-weighted)\n")
    cbn = r.capability_by_need.loc[cap_table.index]; cbn.index.name = "capability"
    L.append(md(cbn, "{:.2f}"))
    L.append("\n## Largest physical sectors on the basket path\n")
    big = phys.sort_values("value_added_per_basket_dollar", ascending=False).head(15)[
        ["name", "value_added_per_basket_dollar", "need_breadth_observed", "top_need"]]
    L.append(md(big, "{:.4f}"))
    L.append("\n## Thin but everywhere (bottleneck candidates)\n")
    L.append(f"Physical sectors with observed need breadth of at least {BREADTH_MIN:g} of {len(needs)} "
             f"that reach at least 90% of the basket at 0.03 cents per dollar: {len(thin)} of "
             f"{len(phys)}. The 20 smallest by volume:\n")
    L.append(md(thin.head(20)[["name", "output_per_basket_dollar", "need_breadth_observed", "reach_0.001"]], "{:.4f}"))
    L.append("\n## What capital endogenization changes (output per basket $ by archetype)\n")
    L.append(md(arch.sort_values("capital_multiplier", ascending=False).head(12), "{:.4f}"))
    L.append("\n## Sensitivity of the capability ranking\n")
    L.append(md(sens))
    L.append("\n## Elicited scores against occupations\n")
    L.append(f"Occupation-based usage (O*NET 31.0 software lists x OEWS May 2021 wage bills) measured for "
             f"{int(measured.sum())} of {len(shares)} commodities; the rest, and capabilities with thin "
             f"coverage ({', '.join(cov.index[cov.thin]) or 'none'}), use elicited scores on the occupational "
             f"scale. Rank correlation of the capability ranking: {sens.at[OCC_VARIANT, "spearman_vs_headline"]:.2f}.\n")
    L.append(f"\nScore weights implied by occupations (mean share above score 0, scaled to score 3): "
             f"1 -> {cal_weight[1]:.2f}, 2 -> {cal_weight[2]:.2f}, 3 -> 1; assumed 0.1, 0.3, 1.\n")
    L.append(md(agree.sort_values("rank_change")[["elicited_rank", "occupational_rank", "rank_change",
                                                   "spearman_across_sectors", "thin"]], "{:.2f}"))
    L.append("\n## Top physical upstream sectors by need\n")
    for n in needs:
        top = upstream[upstream.need == n].head(5)
        L.append(f"- **{n}**: " + "; ".join(f"{x['name']} ({x.output_per_need_dollar:.3f})" for _, x in top.iterrows()))
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
