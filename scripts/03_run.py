"""Run the analysis and write results/*.csv, results/summary.md and figures."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from plenty import model as M, analysis as A, occupations as O

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

    s.round(6).to_csv(OUT / "sectors.csv")
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
    measured = shares.source == "oews"
    elicited_w = S.loc[measured].replace(A.SCORE_WEIGHT)
    agree = pd.DataFrame({
        "spearman_across_sectors": [np.nan if cov.at[k, "thin"] else spearmanr(elicited_w[k], shares.loc[measured, k])[0]
                                    for k in S.columns],
        "n_sectors": int(measured.sum()),
        "thin": cov.thin,
        "elicited_weight": c.weight_equal_need,
        "occupational_weight": occ,
    }, index=S.columns)
    agree["elicited_rank"] = agree.elicited_weight.rank(ascending=False).astype(int)
    agree["occupational_rank"] = agree.occupational_weight.rank(ascending=False).astype(int)
    agree["rank_change"] = agree.elicited_rank - agree.occupational_rank
    agree.index.name = "capability"
    agree.round(4).to_csv(OUT / "score_agreement.csv")

    # Sensitivity of the capability ranking.
    variants = {
        "occupation-based usage (O*NET x OEWS)": occ,
        "linear score weights (1/3, 2/3, 1)": A.run(m, score_weight=A.SCORE_WEIGHT_LINEAR).capabilities.weight_equal_need,
        "no capital endogenization": r0.capabilities.weight_equal_need,
        "capital spread by operating surplus only (no user rules)": A.run(M.build(capital_rules=False)).capabilities.weight_equal_need,
        "needs weighted by US spending": c.weight_spending,
        "exposure through critical sectors (instead of volume)": c.exposure_mean,
    }
    base = c.weight_equal_need
    top5 = set(base.sort_values(ascending=False).index[:5])
    sens = pd.DataFrame([dict(variant=k, spearman_vs_headline=spearmanr(base, v)[0],
                              top5_overlap=len(top5 & set(v.sort_values(ascending=False).index[:5])),
                              top5=", ".join(v.sort_values(ascending=False).index[:5]))
                         for k, v in variants.items()]).set_index("variant")
    sens.round(3).to_csv(OUT / "sensitivity.csv")

    ranks = pd.DataFrame({
        "volume_rank": base.rank(ascending=False).astype(int),
        "exposure_rank": c.exposure_mean.rank(ascending=False).astype(int),
    })
    ranks["worst_rank"] = ranks.max(axis=1)
    desc = pd.read_csv(M.CONFIG / "capabilities.csv").set_index("capability")
    ranks["occupational_rank"] = agree.occupational_rank
    cap_table = pd.DataFrame({
        "volume weight": base, "occupational weight": occ, "exposure": c.exposure_mean,
        "reach 0.1c": c["reach_0.001"], "reach 1c": c["reach_0.01"], "reach 5c": c["reach_0.05"],
        "need breadth": c.need_breadth, "most exposed need": c.most_exposed_need,
        "least exposed need": c.least_exposed_need,
    }).join(ranks).sort_values("volume weight", ascending=False)
    cap_table.index.name = "capability"
    cap_table.round(4).to_csv(OUT / "capability_table.csv")

    # ---- summary.md
    L = []
    L.append("## Basket\n")
    nt = pd.DataFrame({"final demand ($B, 2017)": T / 1e3, "share": T / T.sum()}); nt.index.name = "need"
    L.append(md(nt, "{:.2f}"))
    L.append(f"\nTotal basket: ${T.sum()/1e6:.2f} trillion. Physical sectors (farming, extraction, "
             f"utilities, construction, manufacturing) carry {phys_share:.0%} of the value added "
             f"embodied in it; the rest is services.\n")
    L.append("## Capabilities\n")
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
             f"scale. Rank correlation of the capability ranking: {spearmanr(base, occ)[0]:.2f}.\n")
    L.append(md(agree.sort_values("rank_change")[["elicited_rank", "occupational_rank", "rank_change",
                                                   "spearman_across_sectors", "thin"]], "{:.2f}"))
    L.append("\n## Top physical upstream sectors by need\n")
    for n in needs:
        u = upstream[upstream.need == n].head(5)
        L.append(f"- **{n}**: " + "; ".join(f"{x['name']} ({x.output_per_need_dollar:.3f})" for _, x in u.iterrows()))
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
