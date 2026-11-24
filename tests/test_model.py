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
