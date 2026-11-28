"""Where today's value flows: the need dollar is split, never copied, on its way to capabilities."""
import numpy as np
import pandas as pd
import pytest
from plenty import model as M, analysis as A, flows as F, occupations as O


@pytest.fixture(scope="module")
def m():
    return M.build()


@pytest.fixture(scope="module")
def r(m):
    return A.run(m)


@pytest.fixture(scope="module")
def caps():
    return F.capabilities()


@pytest.fixture(scope="module")
def ls():
    return F.listings()


@pytest.fixture(scope="module")
def pc():
    return F.product_capabilities()


@pytest.fixture(scope="module")
def theta(ls, pc, caps):
    return F.occupation_shares(ls, pc, caps)


@pytest.fixture(scope="module")
def theta_d(ls, pc, caps):
    return F.occupation_shares(ls, pc, caps, distinctive=True)


@pytest.fixture(scope="module")
def work(m, theta):
    return F.sector_work(m.t.commodities, theta)


@pytest.fixture(scope="module")
def vn(m, r):
    return F.need_value_added(m, r)


def test_a_product_counts_once_however_many_capabilities_it_is_in(pc):
    assert np.allclose(pc.groupby("product").weight.sum(), 1)
    assert pc.groupby("product").capability.nunique().max() > 1   # multi-membership does occur


def test_occupation_shares_split_the_occupation(theta, theta_d):
    for t in (theta, theta_d):
        assert (t.values >= 0).all()
        assert (t.sum(axis=1) <= 1 + 1e-9).all()
    # the distinctive split only redistributes what the plain split attributes
    assert np.allclose(theta.sum(axis=1), theta_d.sum(axis=1))
    assert not np.allclose(theta.values, theta_d.values)


def test_distinctive_split_moves_weight_off_what_everyone_lists(theta, theta_d):
    common = (theta > 0).sum().idxmax()
    assert theta_d[common].sum() < 0.5 * theta[common].sum()


def test_need_value_added_shares(m, r, vn):
    assert np.allclose(vn.sum(), 1)
    assert np.allclose(vn.mean(axis=1), r.sectors.value_added_share_equal)


def test_flow_is_conserved(m, vn, work, caps):
    flow, by_need, terms = F.flow(vn, work, caps)
    assert np.allclose(terms.sum(), flow)
    assert np.allclose(by_need.mean(axis=1), flow)
    acct = F.unattributed(vn, work, caps)
    assert acct["flowed"] == pytest.approx(flow.sum())
    assert sum(acct.values()) == pytest.approx(1.0)
    assert 0.6 < acct["flowed"] < 1
    # no need sends more than its dollar
    assert (by_need.sum() <= 1 + 1e-9).all()


def test_sectors_are_measured_or_accounted_for(m, work, caps):
    assert list(work.index) == m.t.commodities
    measured = work.source.str.startswith("oews")
    assert measured.sum() > 385
    assert set(work.loc[["GSLGE", "GSLGH", "GSLGO"], "source"]) == {"oews_proxy"}
    w = work.loc[measured, caps].astype(float)
    assert ((w >= 0) & (w <= 1)).all().all() and (w.sum(axis=1) <= 1 + 1e-9).all()


def test_each_need_runs_on_its_own_domain(vn, m, ls, pc, caps):
    """Sanity: with general office tools set aside, the largest flow of the health, education
    and food needs is a capability of the matching domain."""
    work_d = F.sector_work(m.t.commodities, F.occupation_shares(ls, pc, caps, distinctive=True))
    by_need = F.flow(vn, work_d, caps)[1]
    assert by_need["health"].idxmax().startswith("health.")
    assert by_need["education"].idxmax().startswith("learn.")
    assert by_need["food"].idxmax().startswith("commerce.")


def test_occupation_value_sums_to_the_measured_share(m, vn, work):
    ov = F.occupation_value(m.t.commodities, vn.mean(axis=1))
    measured = work.source.str.startswith("oews")
    assert ov.sum() == pytest.approx(vn.mean(axis=1)[measured].sum())
