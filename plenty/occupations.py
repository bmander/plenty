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


def _occupation_uses(occ_codes: pd.Index, u: pd.DataFrame) -> pd.DataFrame:
    """uses[] for OEWS occupation codes. OEWS sometimes publishes an aggregate code ending in 0
    (e.g. 51-2090 for 51-2091..2099); it uses k if any O*NET occupation under it does."""
    rows = {}
    for code in occ_codes:
        if code in u.index:
            rows[code] = u.loc[code]
        else:  # an all-NaN row when nothing in O*NET sits under the code
            rows[code] = u[u.index.str.startswith(code.rstrip("0"))].max()
    return pd.DataFrame(rows).T


def shares(commodities: list[str], u: pd.DataFrame) -> pd.DataFrame:
    """Commodity x capability wage-bill shares in [0, 1], with provenance columns.

    Occupations with suppressed employment or wages are dropped (the share renormalizes over the
    rest). Occupations missing from O*NET count as not using any capability.
    """
    o = oews()
    det = o[o.O_GROUP.str.lower() == "detailed"]
    totals = o[o.OCC_CODE == "00-0000"]
    tot = totals.set_index("NAICS").wagebill
    wb = det.dropna(subset=["wagebill"]).groupby(["NAICS", "OCC_CODE"]).wagebill.sum().unstack(fill_value=0.0)
    ou = _occupation_uses(wb.columns, u)
    unmatched = ou.isna().all(axis=1)
    ou = ou.fillna(0.0)
    covers = {r.NAICS: oews_coverage(r.NAICS, r.NAICS_TITLE) for r in totals.itertuples()}
    ind = bea_industries(commodities, covers)
    rows = []
    for c in commodities:
        naics = [] if c in M.HOUSING else ind[c]
        rec = {"commodity": c, "source": "oews" if naics else f"fallback:{_fallback_reason(c)}",
               "oews_industries": ";".join(naics)}
        if naics:
            w = wb.loc[naics].sum()
            total = w.sum()
            rec.update((w @ ou / total).to_dict())
            rec["wagebill_musd"] = total / 1e6
            known = tot.reindex(naics).sum()
            rec["wagebill_dropped_frac"] = 1 - total / known if known > 0 else np.nan
            rec["wagebill_unmatched_frac"] = w[unmatched].sum() / total
        rows.append(rec)
    caps = list(u.columns)
    cols = ["source", "oews_industries"] + caps + ["wagebill_musd", "wagebill_dropped_frac", "wagebill_unmatched_frac"]
    return pd.DataFrame(rows).set_index("commodity").reindex(columns=cols)


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
    pooled = {s: X.values[S.values == s].mean() for s in range(4)}
    U = pd.DataFrame(index=scores.index, columns=caps, dtype=float)
    for k in caps:
        U[k] = scores[k].map(pooled)
        if k in ok:
            U[k] = scores[k].map({**pooled, **X[k].groupby(S[k]).mean()})
            U.loc[measured, k] = X[k]
    return U
