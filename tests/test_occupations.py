import re
import numpy as np
import pandas as pd
import pytest
from plenty import model as M, analysis as A, occupations as O

# Share of the measured sectors' wage bill the join may lose. May 2021: 1.2% dropped for
# suppressed employment or wages, 1.1% in OEWS occupations with no O*NET software list.
MAX_DROPPED = 0.03
MAX_UNMATCHED = 0.03


@pytest.fixture(scope="module")
def t():
    return M.load_tables()


@pytest.fixture(scope="module")
def matches():
    return O.software_matches()


@pytest.fixture(scope="module")
def cov(matches):
    return O.coverage(matches)


@pytest.fixture(scope="module")
def sh(t, matches):
    codes = pd.read_csv(O.OCC / "onet_occupations.csv")["O*NET-SOC Code"]
    return O.shares(t.commodities, O.uses(matches, codes))


@pytest.fixture(scope="module")
def measured(sh):
    return sh[sh.source == "oews"]


def test_software_map_is_consistent(matches):
    smap = O.software_map()
    assert set(smap.capability) <= set(O.capabilities())
    assert set(smap.field) <= {"example", "category"}
    for r in smap.itertuples():
        re.compile(r.pattern)
        re.compile(r.exclude)
        assert len(O.software_matches(smap=smap.iloc[[r.Index]])) > 0, f"rule matches nothing: {r.pattern}"
    assert set(matches.capability) == set(O.capabilities())


def test_uses_needs_min_products_pooled_over_detailed_occupations():
    m = pd.DataFrame({
        "onet_soc": ["17-2141.00", "17-2141.00", "17-2141.01", "17-2141.01", "11-1021.00", "11-1021.00"],
        "example": ["Abaqus", "Nastran", "Femap", "Abaqus", "Abaqus", "Nastran"],
        "capability": "fea",
    })
    u = O.uses(m, pd.Series(["17-2141.00", "17-2141.01", "11-1021.00", "29-1141.00"]), min_products=3)
    assert u.at["17-2141", "fea"] == 1        # three distinct products across its detailed occupations
    assert u.at["11-1021", "fea"] == 0        # two products is incidental
    assert u.loc["29-1141"].sum() == 0        # listed nothing
    assert list(u.columns) == O.capabilities()


def test_oews_aggregate_occupations_take_any_of_their_members():
    u = pd.DataFrame({"cad": [1, 0]}, index=["51-2091", "51-2092"])
    ou = O._occupation_uses(pd.Index(["51-2090", "51-2092", "99-9999"]), u)
    assert ou.at["51-2090", "cad"] == 1
    assert ou.at["51-2092", "cad"] == 0
    assert np.isnan(ou.at["99-9999", "cad"])


def test_oews_industry_coverage():
    assert O.oews_coverage("333600", "Engine, Turbine") == ["3336"]
    assert O.oews_coverage("327000", "Nonmetallic Mineral Product Manufacturing") == ["327"]
    assert O.oews_coverage("3330A1", "Machinery Manufacturing (3331, 3332, 3334, and 3339 only)") == \
        ["3331", "3332", "3334", "3339"]


def test_shares_cover_every_commodity_with_fallbacks_marked(t, sh, measured):
    assert list(sh.index) == t.commodities
    caps = O.capabilities()
    vals = measured[caps]
    assert vals.notna().all().all()
    assert ((vals >= 0) & (vals <= 1)).all().all()
    assert sh.loc[sh.source != "oews", caps].isna().all().all()
    assert sh.source[sh.source != "oews"].str.startswith("fallback:").all()
    for c in ["1111A0", "112120", "GSLGE", "GSLGO", "S00500", "S00600", "531HSO", "531HST", "S00401"]:
        assert sh.at[c, "source"] != "oews", c
    assert len(measured) > 0.9 * len(sh)


def test_join_loses_little_of_the_wage_bill(measured):
    w = measured.wagebill_musd
    assert (w > 0).all()
    assert (measured.wagebill_dropped_frac * w).sum() / w.sum() < MAX_DROPPED
    assert (measured.wagebill_unmatched_frac * w).sum() / w.sum() < MAX_UNMATCHED


def test_cad_is_highest_in_engineering_services_and_machinery(measured):
    cad = measured.cad
    assert "541300" in cad.nlargest(5).index                     # architectural and engineering services
    assert cad[cad.index.str.startswith("333")].median() > cad.quantile(0.75)
    assert cad["52A000"] < 0.05                                   # banking


def test_gis_is_high_in_surveying_and_near_zero_in_food(measured):
    gis = measured.gis
    assert gis["541300"] > 0.2
    assert gis[gis.index.str.startswith("311")].max() < 0.03


def test_usage_matrix(t, sh, cov):
    S = A.capability_scores(t)
    U = O.usage_matrix(sh, S, cov)
    assert U.notna().all().all() and ((U >= 0) & (U <= 1)).all().all()
    meas = sh.source == "oews"
    ok = cov.index[~cov.thin]
    assert np.allclose(U.loc[meas, ok], sh.loc[meas, ok].astype(float))
    for k in cov.index[cov.thin]:                                 # thin: one level per elicited score
        assert (U[k].groupby(S[k]).nunique() == 1).all()


def test_run_with_usage_matches_scores_when_given_the_scores():
    m = M.build()
    base = A.run(m).capabilities
    S = A.capability_scores(m.t)
    same = A.run(m, usage=S.replace(A.SCORE_WEIGHT).astype(float)).capabilities
    assert np.allclose(base.weight_equal_need, same.weight_equal_need)
    assert np.allclose(base.exposure_mean, same.exposure_mean)
    with pytest.raises(ValueError):
        A.run(m, usage=S.replace(A.SCORE_WEIGHT).astype(float).iloc[:-1])


def test_bea_codes_reach_coarse_and_aggregate_oews_industries(sh):
    ind = sh.oews_industries.fillna("").str.split(";")
    # single-family housing: 2361, 2372 and the whole 3-digit 238 (specialty trades), not 2362
    assert set(ind["233411"]) == {"236100", "237200", "238100", "238200", "238300", "238900"}
    assert ind["333111"] == ["3330A1"]                            # farm machinery inside an OEWS aggregate
    assert ind["541300"] == ["541300"]
    assert ind["491000"] == ["491100"]                            # postal service is measured


def test_thin_capabilities_are_flagged(cov):
    assert (cov.thin == (cov.soc_occupations_counted < O.THIN_MIN_OCCUPATIONS)).all()
    assert not cov.loc[["cad", "fea", "gis", "controls"], "thin"].any()
