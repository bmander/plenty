import numpy as np
import pandas as pd
import pytest
from plenty import model as M, analysis as A


@pytest.fixture(scope="module")
def t():
    return M.load_tables()


@pytest.fixture(scope="module")
def m():
    return M.build()


def test_use_table_balances(t):
    """Intermediate use + final demand = commodity output (to BEA rounding)."""
    supply = t.U.sum(axis=1) + t.F.sum(axis=1)
    assert (supply - t.q).abs().max() < 50          # $M


def test_industry_accounts_balance(t):
    assert (t.U.sum(axis=0) + t.VA.sum(axis=0) - t.g).abs().max() < 50


def test_capital_matrix_conserves_investment(t, m):
    inv = t.F[M.INVESTMENT_COLUMNS].sum(axis=1)
    assert np.allclose(m.K.sum(axis=1), inv, atol=1e-6)


def test_capital_is_investment_times_shares(t, m):
    cap = M.capital_allocation(t)
    assert np.allclose(cap.K.values, m.K.values) and list(cap.K.columns) == t.industries
    assert np.allclose(cap.investment.sum(axis=1), t.F[M.INVESTMENT_COLUMNS].sum(axis=1))
    assert set(cap.group) == set(M.CAPITAL_COLUMNS) and (cap.weight >= 0).all()
    for h in cap.investment.columns:
        placed = cap.shares.loc[:, cap.group == h].sum(axis=1)
        bought = cap.investment[h] != 0
        assert np.allclose(placed[bought], 1.0) and not placed[~bought].any(), h   # all of a purchase is placed, and only purchases
    # each commodity an investor bought is in exactly one of that investor's sets
    for h in cap.investment.columns:
        listed = [c for x in cap.steps if x["group"] == h for c in x["commodities"]]
        assert sorted(listed) == sorted(cap.investment.index[cap.investment[h] != 0])
    # without the pairings only the housing one remains, and K still adds up
    plain = M.capital_allocation(t, use_rules=False)
    assert [x["note"] for x in plain.steps if x["note"]] == [M.HOUSING_RULE["note"]]
    assert np.allclose(plain.K.sum(axis=1), cap.K.sum(axis=1))


@pytest.mark.parametrize("endo", [False, True])
def test_leontief_reproduces_observed_output(endo):
    """L applied to all final demand left outside the model must return observed output."""
    m = M.build(endogenize_capital=endo)
    f = m.t.F.drop(columns=M.INVESTMENT_COLUMNS) if endo else m.t.F
    x = m.L.values @ f.sum(axis=1).values
    q = m.t.q.values
    big = q > 1000
    assert np.abs(x[big] - q[big]).max() / q[big].max() < 1e-3
    assert (np.abs(x[big] - q[big]) / q[big]).max() < 0.01


def test_leontief_is_productive(m):
    assert np.abs(np.linalg.eigvals(m.A.values)).max() < 1
    produced = m.t.q.values > 0
    assert (np.diag(m.L.values)[produced] >= 1 - 1e-9).all()
    real = [c for c in m.t.commodities if not c.startswith("S004")]
    assert m.L.loc[real].values.min() > -1e-3


def test_need_demand_adds_up(t):
    Dn = A.need_demand(t)
    fd = t.F["F01000"] + t.F[A.GOV_CONSUMPTION].sum(axis=1)
    basket = pd.read_csv(M.CONFIG / "basket.csv").set_index("commodity").need
    classified = fd[basket.reindex(fd.index) != "none"].sum()
    assert Dn.values.sum() == pytest.approx(classified, rel=1e-9)
    assert fd[basket.reindex(fd.index) == "none"].abs().sum() < 1e-6 * fd.sum()


def test_a_need_dollar_and_the_output_behind_it(m):
    d, x = A.need_dollars(m)
    assert list(d.columns) == A.included_needs() and list(d.index) == m.t.commodities
    assert np.allclose(d.sum(), 1.0) and (d.values >= 0).all()          # each need is one dollar
    assert np.allclose(x.values, m.L.values @ d.values)
    assert np.allclose(x.values, A.run(m).sector_by_need.values)        # the same figures the measures are built on
    assert (x.sum() > 1.5).all() and (x.sum() < 3).all()                # output behind a dollar, counting every sale


def test_configs_are_consistent(t):
    arch = pd.read_csv(M.CONFIG / "sector_archetypes.csv")
    caps = pd.read_csv(M.CONFIG / "archetype_capabilities.csv").set_index("archetype")
    names = pd.read_csv(M.CONFIG / "capabilities.csv").capability
    assert set(arch.commodity) == set(t.commodities)
    assert set(arch.archetype) <= set(caps.index)
    assert list(caps.columns) == list(names)
    assert caps.values.min() >= 0 and caps.values.max() <= 3
    needs = set(pd.read_csv(M.CONFIG / "needs.csv").need)
    assert set(pd.read_csv(M.CONFIG / "basket.csv").need) <= needs


def test_capability_weights_are_shares(m):
    c = A.run(m).capabilities
    assert ((c.weight_equal_need >= 0) & (c.weight_equal_need <= 1)).all()
    assert (c["reach_0.001"] >= c["reach_0.01"]).all() and (c["reach_0.01"] >= c["reach_0.05"]).all()
