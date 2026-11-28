import pandas as pd
import pytest
from plenty import model as M, rd

BERD_TOTAL = 400_100        # $M, "All industries" row of table 17
MIN_MAPPED = 0.95           # share of that R&D that reaches a BEA sector (2017: 97.7%)


@pytest.fixture(scope="module")
def r():
    return rd.intensity(M.load_tables())


def test_parse_naics():
    assert rd.parse_naics("311") == (["311"], [], None)
    assert rd.parse_naics("313–16")[0] == ["313", "314", "315", "316"]
    assert rd.parse_naics("336414–15, 336419")[0] == ["336414", "336415", "336419"]
    assert rd.parse_naics("other 333") == (["333"], [], "333")
    p, x, _ = rd.parse_naics("23, 44–45 (excluding 454111–12), 55–56, 624, 71–72, 81")
    assert p == ["23", "44", "45", "55", "56", "624", "71", "72", "81"] and x == ["454111", "454112"]


def test_suppressed_ranges_read_as_midpoints():
    assert rd._musd("4697") == 4697
    assert rd._musd("1,376 - 1,475") == pytest.approx(1425.5)
    assert pd.isna(rd._musd("D"))


def test_other_rows_take_what_siblings_leave():
    b = rd.berd_rows()
    other_333 = b.index[b.naics == "other 333"][0]
    assert rd.match_row("333120", b) == other_333          # construction machinery
    assert b.industry[rd.match_row("333111", b)] == "Agricultural implement"
    assert b.industry[rd.match_row("336411", b)] == "Aircraft, aircraft engine, and aircraft parts"


def test_rd_is_mapped_once_and_mostly(r):
    per_row = r.dropna().groupby("berd_industry").rd_musd.first()
    assert (per_row >= 0).all()
    assert MIN_MAPPED * BERD_TOTAL <= per_row.sum() <= BERD_TOTAL


def test_coverage_and_ordering(r):
    covered = r.rd_per_output.notna()
    assert covered.sum() > 0.9 * len(r)
    for c in ["1111A0", "112120", "GSLGE", "S00500"]:       # BERD leaves out farms and government
        assert not covered[c], c
    i = r.rd_per_output
    assert i["334413"] > 10 * i["311810"]                     # semiconductors vs bakeries
    assert i["325412"] > i["324110"]                          # pharmaceuticals vs refineries
