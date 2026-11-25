"""The model's matrices arranged for looking at (plenty/matrix.py)."""
import numpy as np
import pytest
from plenty import model as M, matrix as MX


@pytest.fixture(scope="module")
def m():
    return M.build()


def test_every_sector_is_in_one_group(m):
    codes = m.t.commodities
    g = MX.groups(codes)
    assert set(g) == set(MX.ORDER) and len(MX.ORDER) == len(MX.GROUPS)
    assert g["491000"] == "Government" and g["484000"] == "Transportation and warehousing"
    assert g["336111"] == "Durable goods manufacturing" and g["311810"] == "Nondurable goods manufacturing"
    order = MX.ordered(codes)
    assert sorted(order) == sorted(codes)
    # within a group, the Bureau's order is kept
    for name in MX.ORDER:
        assert [c for c in order if g[c] == name] == [c for c in codes if g[c] == name]


def test_direct_requirements_split_into_purchases_and_capital(m):
    purchases, capital = MX.direct_parts(m)
    assert np.allclose(purchases.values + capital.values, m.A.values, atol=1e-12)
    assert 0.1 < capital.values.sum() / m.A.values.sum() < 0.25
    # without capital in the model, the whole of A is purchases
    plain = M.build(endogenize_capital=False)
    p0, k0 = MX.direct_parts(plain)
    assert np.allclose(p0.values, plain.A.values, atol=1e-12) and not k0.values.any()
    assert np.allclose(p0.values, purchases.values, atol=1e-12)


def test_group_sums_keep_the_economy_wide_total(m):
    q = m.t.q
    G = MX.by_group(m.A, q)
    assert list(G.index) == list(G.columns) == MX.ORDER
    by_group_output = q.groupby(MX.groups(q.index)).sum()
    assert float((G.sum() * by_group_output).sum()) == pytest.approx(float((m.A.sum() * q).sum()))
    # groups buy most from themselves or from the goods they process
    assert G.at["Durable goods manufacturing", "Durable goods manufacturing"] == G["Durable goods manufacturing"].max()
    assert G.at["Mining", "Nondurable goods manufacturing"] > 0.05
