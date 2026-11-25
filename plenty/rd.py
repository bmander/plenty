"""Business R&D intensity by BEA sector, from NSF/NCSES BERD 2017 (table 17).

R&D intensity = domestic R&D performed by companies in an industry (all funders) / BEA 2017
output of the sectors that industry maps to. BERD's own percentages divide by the sales of
companies that perform or fund R&D, which overstates intensity where few companies do any
(real estate shows 6.6%); dividing by the whole industry's output puts every sector on the same
footing as the input-output model.

BERD covers mining, utilities, construction, manufacturing and services (NAICS 21-23, 31-33,
42-81): not farms or government. It classifies a company by its main industry, so a drug maker's
R&D labs count under pharmaceuticals.
"""
from __future__ import annotations
import re
import pandas as pd
from . import model as M

RD = M.ROOT / "data" / "rd"
TOTAL_ROWS = ("All industries", "Manufacturing industries", "Nonmanufacturing industries")


def _expand(token: str) -> list[str]:
    """'313–16' -> 313..316; '336411–13' -> 336411..336413; '311' -> ['311']."""
    if "–" not in token:
        return [token]
    a, b = (x.strip() for x in token.split("–"))
    b = a[:len(a) - len(b)] + b
    return [str(i) for i in range(int(a), int(b) + 1)]


def parse_naics(spec: str) -> tuple[list[str], list[str], str | None]:
    """BERD's NAICS column -> (prefixes, excluded prefixes, parent of an 'other X' row).

    '3255, 3259' -> two prefixes; 'other 333' -> (['333'], [], '333'), whose exclusions are
    the sibling rows under 333; '44–45 (excluding 454111–12)' -> 44, 45 minus 454111, 454112.
    """
    excluded = []
    for inner in re.findall(r"\(excluding ([^)]*)\)", spec):
        excluded += [x for tok in inner.split(",") for x in _expand(tok.strip())]
    spec = re.sub(r"\(excluding [^)]*\)", "", spec)
    other = None
    if spec.startswith("other "):
        other = spec[len("other "):].strip()
        spec = other
    prefixes = [x for tok in spec.split(",") if tok.strip() for x in _expand(tok.strip())]
    return prefixes, excluded, other


def _musd(s: str) -> float:
    """'4697' -> 4697; a suppressed range '1,376 - 1,475' -> its midpoint; 'D' -> NaN."""
    nums = [float(x.replace(",", "")) for x in re.findall(r"[\d,]+(?:\.\d+)?", s)]
    return sum(nums) / len(nums) if nums else float("nan")


def berd_rows() -> pd.DataFrame:
    b = pd.read_csv(RD / "berd_2017_rd_by_industry.csv", dtype=str)
    b = b[~b.industry.isin(TOTAL_ROWS)].reset_index(drop=True)
    parsed = b.naics.map(parse_naics)
    b["prefixes"] = parsed.str[0]
    b["excluded"] = parsed.str[1]
    others = parsed.str[2]
    # an 'other X' row covers X except what its sibling rows under X claim
    for i, parent in others.items():
        if parent:
            b.at[i, "excluded"] = b.excluded[i] + [p for j, ps in b.prefixes.items() if j != i
                                                   for p in ps if p.startswith(parent) and p != parent]
    b["is_other"] = others.notna()
    b["rd"] = b.rd_musd.map(_musd)
    return b


def _nested(b: pd.DataFrame, j: int, i: int) -> bool:
    """Row j sits inside row i: every prefix of j extends one of i's, and j is not i's 'other' row."""
    if b.is_other[j] and not b.is_other[i] and set(b.prefixes[j]) == set(b.prefixes[i]):
        return True
    return all(any(p.startswith(q) and len(p) > len(q) for q in b.prefixes[i]) for p in b.prefixes[j])


def match_row(naics: str, b: pd.DataFrame) -> int | None:
    """The most specific BERD row covering a NAICS code; on a tie, an 'other X' row beats the X
    row it is part of."""
    # NAICS 2017 merged some 2012 codes that BERD still lists (454111 and 454112 became 454110):
    # a 6-digit code ending in 0 also matches the finer codes under its stem.
    stem = naics.rstrip("0") if len(naics) == 6 and len(naics.rstrip("0")) >= 5 else None

    def covers(p: str) -> bool:
        return naics.startswith(p) or (stem is not None and p.startswith(stem))

    best, best_key = None, (-1, False)
    for i, r in b.iterrows():
        if any(covers(x) for x in r.excluded):
            continue
        hit = [p for p in r.prefixes if covers(p)]
        key = (len(max(hit, key=len)), bool(r.is_other)) if hit else None
        if key and key > best_key:
            best, best_key = i, key
    return best


def intensity(t: M.Tables) -> pd.DataFrame:
    """Per BEA commodity: the BERD industry it falls in, that industry's R&D, the pooled BEA
    output of the sectors in it, and R&D per dollar of output. Uncovered sectors get NaN."""
    b = berd_rows()
    x = pd.read_csv(M.ROOT / "data" / "occupations" / "bea_naics_2017.csv", dtype=str)
    x = x[x.naics.str.fullmatch(r"\d+")]
    output = t.g.reindex(t.commodities).fillna(t.q)
    row_of = {}
    for c, codes in x.groupby("bea_detail").naics:
        deepest = codes[codes.str.len() == codes.str.len().max()]
        rows = [match_row(n, b) for n in deepest]
        rows = [r for r in rows if r is not None]
        if rows:
            row_of[c] = max(set(rows), key=rows.count)
    row = pd.Series(row_of).reindex(t.commodities)
    pooled = output.groupby(row).sum()
    # A parent row (Chemicals, 325) includes its children's R&D. Where some of its sectors fall in
    # child rows, the parent keeps only the remainder.
    used = set(row.dropna().astype(int))
    rd = b.rd.copy()
    for i in used:
        if b.is_other[i]:          # already published net of its siblings
            continue
        nested = [j for j in used if j != i and _nested(b, j, i)]
        rd[i] = b.rd[i] - b.rd[nested].sum()
    out = pd.DataFrame({
        "berd_industry": row.map(b.industry),
        "berd_naics": row.map(b.naics),
        "rd_musd": row.map(rd),
        "output_musd": row.map(pooled),
    }, index=pd.Index(t.commodities, name="commodity"))
    out["rd_per_output"] = out.rd_musd / out.output_musd
    return out
