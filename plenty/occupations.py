"""Occupation-based capability usage: O*NET software lists x OEWS wage bills by industry.

For BEA commodity j, capability k and occupation o:

    share[j, k] = sum_o wagebill[j, o] * uses[o, k] / sum_o wagebill[j, o]

uses[o, k] is 1 when the occupation's O*NET software list has at least MIN_PRODUCTS products
that config/software_capabilities.csv maps to k. wagebill[j, o] is OEWS employment times mean annual
wage, pooled over the 4-digit NAICS industries the BEA commodity maps to.

Data: O*NET 31.0 (SOC 2018), OEWS May 2021 (SOC 2018, NAICS 2017), BEA-NAICS crosswalk from
USEPA/useeior. See data/occupations/README.md.
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from . import model as M

OCC = M.ROOT / "data" / "occupations"
# An occupation counts as using k when its O*NET list has at least this many distinct products
# mapped to k. With 1, a stray mention among a generalist's hundreds of listed products (Software
# Developers list 430, including Verilog and a genome assembler) puts that occupation's whole
# wage bill behind k in every industry; specialists list 5 to 40 products for their own field.
MIN_PRODUCTS = 3
# A capability used (in that sense) by fewer SOC occupations than this is too thin to measure and
# stays on its elicited scores.
THIN_MIN_OCCUPATIONS = 3
# OEWS prints '#' for annual wages at or above its top code ($208,000 in May 2021).
OEWS_TOP_CODE = 208_000.0
# Labels for sectors the join finds no OEWS industry for: crop and animal production (not
# surveyed); general government (OEWS reports it under 999xxx, with no BEA counterpart), government
# enterprises, scrap, used goods, imports and rest of world; and housing services, which the
# crosswalk maps to real-estate lessors but are imputed rents with no employees.
FARM_PREFIXES = ("111", "112")
SPECIAL_PREFIXES = ("GSLG", "S00") + tuple(M.HOUSING)
# Stand-ins for some of those, used when wage_mix(use_proxies=True): BEA commodity prefix -> NAICS
# prefixes of the OEWS industries whose occupational mix stands in for it. OEWS reports public
# schools and hospitals inside 611 and 622 (all ownerships) and other government under 999xxx;
# support activities for crop and animal production stand in for farms.
PROXY_PREFIXES = {
    "GSLGE": ["611"], "GSLGH": ["622"],
    "GSLGO": ["9992", "9993"], "S00201": ["9992", "9993"], "S00202": ["9992", "9993"], "S00203": ["9992", "9993"],
    "S00500": ["9991"], "S00600": ["9991"], "S00101": ["9991"], "S00102": ["9991"], "491000": ["9991"],
    "111": ["1151"], "112": ["1152"],
}


def soc6(code: pd.Series) -> pd.Series:
    """'17-2141.00' -> '17-2141'."""
    return code.str.slice(0, 7)


def capabilities() -> list[str]:
    return list(pd.read_csv(M.CONFIG / "capabilities.csv").capability)


def software_map() -> pd.DataFrame:
    return pd.read_csv(M.CONFIG / "software_capabilities.csv", dtype=str).fillna("")


def _search(pattern: str, values) -> set[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    return {v for v in values if rx.search(v)}


def software_matches() -> pd.DataFrame:
    """One row per (O*NET occupation, product, capability, map rule) the software map matches.

    Patterns are matched once per distinct product or category name, not once per listing."""
    sw = pd.read_csv(OCC / "onet_software_skills.csv").fillna("")
    example, category = sw["Workplace Example"], sw["Element Name"]
    names = {"example": example.unique(), "category": category.unique()}
    hits = []
    for rule, r in software_map().iterrows():
        target = example if r.field == "example" else category
        m = target.isin(_search(r.pattern, names[r.field]))
        if r.exclude:
            m &= ~example.isin(_search(r.exclude, names["example"]))
        hits.append(pd.DataFrame({"onet_soc": sw.loc[m, "O*NET-SOC Code"].values,
                                  "example": example[m].values, "capability": r.capability, "rule": rule}))
    return pd.concat(hits, ignore_index=True)


def product_counts(matches: pd.DataFrame) -> pd.DataFrame:
    """SOC (6-digit) x capability: distinct matched products, pooled over the detailed O*NET
    occupations under each SOC code."""
    return (matches.assign(soc=soc6(matches.onet_soc)).groupby(["soc", "capability"]).example
            .nunique().unstack(fill_value=0).reindex(columns=capabilities(), fill_value=0))


def uses(matches: pd.DataFrame, occupations: pd.Series, min_products: int = MIN_PRODUCTS) -> pd.DataFrame:
    """SOC (6-digit) x capability, 1 if the occupation lists at least min_products products for k."""
    idx = sorted(set(soc6(occupations)))
    return (product_counts(matches) >= min_products).astype(int).reindex(idx, fill_value=0)


def coverage(matches: pd.DataFrame, titles: pd.Series | None = None,
             min_products: int = MIN_PRODUCTS) -> pd.DataFrame:
    """Per capability: products and occupations matched, and whether coverage is too thin.

    titles (O*NET-SOC code -> title), if given, adds the counted occupations by name."""
    caps = capabilities()
    g = matches.assign(soc=soc6(matches.onet_soc)).groupby("capability")
    counted = product_counts(matches) >= min_products
    cov = pd.DataFrame({
        "products": g.example.nunique(),
        "onet_occupations": g.onet_soc.nunique(),
        "soc_occupations_any": g.soc.nunique(),
        "soc_occupations_counted": counted.sum(),
    }).reindex(caps).fillna(0).astype(int)
    cov["thin"] = cov.soc_occupations_counted < THIN_MIN_OCCUPATIONS
    top = (matches.drop_duplicates(["onet_soc", "example", "capability"])
           .groupby(["capability", "example"]).size().rename("n").reset_index())
    cov["top_products"] = (top.sort_values("n", ascending=False).groupby("capability").example
                           .apply(lambda s: "; ".join(s.head(4))).reindex(caps).fillna(""))
    if titles is not None:
        t = titles.groupby(soc6(titles.index.to_series())).first()
        cov["occupations_counted"] = [
            "; ".join(t.reindex(counted.index[counted[k]]).fillna("?")) for k in caps]
    cov.index.name = "capability"
    return cov


def _number(s: pd.Series, top: float | None = None) -> pd.Series:
    s = s.astype(str).str.replace(",", "").str.strip()
    if top is not None:
        s = s.where(s != "#", str(top))
    return pd.to_numeric(s, errors="coerce")


def oews() -> pd.DataFrame:
    """OEWS industry x occupation rows, with employment, wage and wage bill.

    Rows whose employment or wage is suppressed have wagebill NaN.
    """
    o = pd.read_csv(OCC / "oews_2021_nat4d.csv", dtype=str)
    o = o.assign(emp=_number(o.TOT_EMP), wage=_number(o.A_MEAN, OEWS_TOP_CODE))
    o["wagebill"] = o.emp * o.wage
    return o


def oews_coverage(code: str, title: str) -> list[str]:
    """NAICS prefixes an OEWS industry code covers.

    '333600' -> ['3336']; '327000' (a whole 3-digit industry) -> ['327'];
    '3330A1', titled 'Machinery Manufacturing (3331, 3332, 3334, and 3339 only)' -> those four.
    """
    if not code.isdigit():
        listed = re.findall(r"\b\d{4}\b", title)
        if not listed:
            raise ValueError(f"cannot read the industries covered by OEWS {code}: {title}")
        return listed
    return [code[:3]] if code[3:] == "000" else [code[:4]]


def bea_industries(commodities: list[str], industries: dict[str, list[str]]) -> dict[str, list[str]]:
    """BEA detail code -> the OEWS industries it draws its wage bill from.

    industries maps OEWS industry code -> NAICS prefixes it covers. A BEA code is matched through
    the most specific of its crosswalk codes on each branch, cut to 4 digits (residential
    construction maps to 2361, 2372 and the whole of 238); an OEWS industry is used when one of
    its prefixes nests with one of those.
    """
    x = pd.read_csv(OCC / "bea_naics_2017.csv", dtype=str)
    x = x[x.naics.str.fullmatch(r"\d+")]
    crosswalk = x.naics.str.slice(0, 4).groupby(x.bea_detail).apply(set)
    out = {}
    for c in commodities:
        codes = crosswalk.get(c, set())
        mine = {p for p in codes if not any(q != p and q.startswith(p) for q in codes)}
        out[c] = sorted(i for i, cov in industries.items()
                        if any(p.startswith(q) or q.startswith(p) for p in mine for q in cov))
    return out


def _fallback_reason(c: str) -> str:
    if c.startswith(FARM_PREFIXES):
        return "farm"
    if c.startswith(SPECIAL_PREFIXES):
        return "government_or_special"
    return "no_oews_match"


def _occupation_uses(occ_codes: pd.Index, u: pd.DataFrame, agg: str = "max") -> pd.DataFrame:
    """uses[] for OEWS occupation codes. OEWS sometimes publishes an aggregate code ending in 0
    (e.g. 51-2090 for 51-2091..2099); it takes agg over the O*NET occupations under it: "max"
    (uses k if any member does) for 0/1 uses, "mean" for shares."""
    rows = {}
    for code in occ_codes:
        if code in u.index:
            rows[code] = u.loc[code]
        else:  # an all-NaN row when nothing in O*NET sits under the code
            rows[code] = u[u.index.str.startswith(code.rstrip("0"))].agg(agg)
    return pd.DataFrame(rows).T


def wage_mix(commodities: list[str], use_proxies: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(W, info). W is commodity x OEWS occupation code: the wage bill ($) of each detailed
    occupation in the OEWS industries the commodity maps to, all zero where it maps to none.
    info has source, oews_industries, wagebill_musd and wagebill_dropped_frac per commodity.

    Occupations with suppressed employment or wages are dropped. use_proxies measures the
    commodities in PROXY_PREFIXES through their stand-in industries (source "oews_proxy")
    instead of leaving them to a fallback."""
    o = oews()
    det = o[o.O_GROUP.str.lower() == "detailed"]
    totals = o[o.OCC_CODE == "00-0000"]
    tot = totals.set_index("NAICS").wagebill
    wb = det.dropna(subset=["wagebill"]).groupby(["NAICS", "OCC_CODE"]).wagebill.sum().unstack(fill_value=0.0)
    covers = {r.NAICS: oews_coverage(r.NAICS, r.NAICS_TITLE) for r in totals.itertuples()}
    ind = bea_industries(commodities, covers)
    W, info = {}, []
    for c in commodities:
        pref = next((v for k, v in PROXY_PREFIXES.items() if c.startswith(k)), None) if use_proxies else None
        if pref:
            naics, source = sorted(i for i in wb.index if i.startswith(tuple(pref))), "oews_proxy"
        else:
            naics = [] if c in M.HOUSING else ind[c]
            source = "oews" if naics else f"fallback:{_fallback_reason(c)}"
        rec = {"commodity": c, "source": source, "oews_industries": ";".join(naics)}
        W[c] = wb.loc[naics].sum()
        if naics:
            total, known = W[c].sum(), tot.reindex(naics).sum()
            rec["wagebill_musd"] = total / 1e6
            rec["wagebill_dropped_frac"] = 1 - total / known if known > 0 else np.nan
        info.append(rec)
    return pd.DataFrame(W).T.reindex(columns=wb.columns), pd.DataFrame(info).set_index("commodity")


def shares(commodities: list[str], u: pd.DataFrame, agg: str = "max", use_proxies: bool = False) -> pd.DataFrame:
    """Commodity x column wage-bill-weighted means of u (SOC x column, values in [0, 1]), with
    provenance columns.

    The share renormalizes over the occupations OEWS reports (see wage_mix). Occupations missing
    from O*NET count as 0. agg: see _occupation_uses. use_proxies: see wage_mix.
    """
    W, info = wage_mix(commodities, use_proxies)
    ou = _occupation_uses(W.columns, u, agg)
    unmatched = ou.isna().all(axis=1)
    total = W.sum(axis=1)
    measured = total > 0
    sh = (W @ ou.fillna(0.0)).div(total, axis=0)[measured]
    info["wagebill_unmatched_frac"] = (W.loc[:, unmatched].sum(axis=1) / total)[measured]
    caps = list(u.columns)
    cols = ["source", "oews_industries"] + caps + ["wagebill_musd", "wagebill_dropped_frac", "wagebill_unmatched_frac"]
    return info.join(sh).reindex(index=commodities, columns=cols).rename_axis("commodity")


def score_levels(sh: pd.DataFrame, scores: pd.DataFrame, cov: pd.DataFrame) -> pd.DataFrame:
    """Mean occupational share by elicited score, pooled over measured sectors and non-thin
    capabilities (one observation per sector x capability cell)."""
    measured = sh.source == "oews"
    ok = [k for k in scores.columns if not cov.at[k, "thin"]]
    S = scores.loc[measured, ok].values.ravel()
    X = sh.loc[measured, ok].astype(float).values.ravel()
    return pd.DataFrame({"cells": [(S == s).sum() for s in range(4)],
                         "mean_share": [X[S == s].mean() for s in range(4)]},
                        index=pd.Index(range(4), name="score"))


def calibrated_score_weight(levels: pd.DataFrame) -> dict[int, float]:
    """Score -> weight implied by occupations: the mean share above the score-0 baseline,
    scaled so a 3 weighs 1, as analysis.SCORE_WEIGHT does."""
    above = levels.mean_share - levels.mean_share[0]
    w = (above / above[3]).to_dict()
    if not 0 < w[1] < w[2] < w[3] == 1:
        raise ValueError(f"occupational shares do not rise with score: {w}")
    return {int(s): float(v) for s, v in w.items()}


def usage_matrix(sh: pd.DataFrame, scores: pd.DataFrame, cov: pd.DataFrame) -> pd.DataFrame:
    """Commodity x capability usage for analysis.run(usage=...).

    Measured shares where the sector has OEWS data and the capability is not thin. Elsewhere the
    elicited score, put on the occupational scale: score s for capability k becomes the mean
    share of measured sectors scored s on k (pooled over non-thin capabilities when k is thin or
    no measured sector has that score).
    """
    caps = list(scores.columns)
    measured = sh.source == "oews"
    ok = [k for k in caps if not cov.at[k, "thin"]]
    S, X = scores.loc[measured, ok], sh.loc[measured, ok].astype(float)
    pooled = score_levels(sh, scores, cov).mean_share.to_dict()
    U = pd.DataFrame(index=scores.index, columns=caps, dtype=float)
    for k in caps:
        U[k] = scores[k].map(pooled)
        if k in ok:
            U[k] = scores[k].map({**pooled, **X[k].groupby(S[k]).mean()})
            U.loc[measured, k] = X[k]
    return U
