"""The work that has to get done: O*NET tasks and work activities, and the need dollar's flow to them."""
import numpy as np
import pandas as pd
import pytest
from plenty import model as M, analysis as A, flows as F, occupations as O, work as W


@pytest.fixture(scope="module")
def t():
    return W.tasks()


@pytest.fixture(scope="module")
def shares(t):
    return W.task_activity_shares(t)


@pytest.fixture(scope="module")
def theta(shares):
    return W.occupation_activity_shares(shares)


@pytest.fixture(scope="module")
def m():
    return M.build()


@pytest.fixture(scope="module")
def vn(m):
    return F.need_value_added(m, A.run(m))


@pytest.fixture(scope="module")
def work(m, theta):
    return F.sector_work(m.t.commodities, theta)


def test_every_task_has_weights_and_an_activity(t):
    raw = pd.read_csv(O.OCC / "onet_tasks.csv")
    links = pd.read_csv(O.OCC / "onet_task_activities.csv")
    assert t[list(W.WEIGHTS)].notna().all().all() and (t[list(W.WEIGHTS)] >= 0).all().all()
    assert len(t) >= 0.97 * len(raw)          # only occupations with no rated task at all are dropped
    assert set(zip(t.onet_soc, t.task_id)) <= set(zip(links.onet_soc, links.task_id))
    assert set(links.dwa) <= set(W.hierarchy().index)


def test_hierarchy_is_a_tree():
    H = W.hierarchy()
    assert H.index.is_unique
    assert H.groupby("iwa").gwa.nunique().max() == 1
    assert (H.gwa.nunique(), H.iwa.nunique(), len(H)) == (41, 332, 2087)


def test_an_occupations_work_is_split_once(shares, theta):
    assert np.allclose(shares.groupby("soc").share.sum(), 1)
    assert np.allclose(theta.sum(axis=1), 1) and (theta.values >= 0).all()
    # a task in several activities is divided among them, not copied
    per_task = shares.groupby(["onet_soc", "task_id"]).dwa.nunique()
    assert per_task.max() > 1


def test_frequency_weights_tell_the_same_story(t, theta):
    theta_f = W.occupation_activity_shares(W.task_activity_shares(t, "frequency"))
    assert np.allclose(theta_f.sum(axis=1), 1)
    a, b = theta.sum(), theta_f.reindex(columns=theta.columns, fill_value=0).sum()
    assert a.corr(b, method="spearman") > 0.9


def test_flow_through_the_work_is_conserved(vn, work, theta):
    cols = list(theta.columns)
    flow, by_need, terms = F.flow(vn, work, cols)
    acct = F.unattributed(vn, work, cols)
    assert sum(acct.values()) == pytest.approx(1.0)
    assert acct["flowed"] == pytest.approx(flow.sum()) and acct["flowed"] > 0.9
    assert np.allclose(by_need.mean(axis=1), flow) and (by_need.sum() <= 1 + 1e-9).all()


def test_each_need_pays_for_its_own_kind_of_work(vn, work, theta):
    H = W.hierarchy()
    by_need = F.flow(vn, work, list(theta.columns))[1]
    top = {n: H.dwa_name[by_need[n].idxmax()] for n in ("food", "health", "education")}
    assert top["food"] == "Cook foods."
    assert "patient" in top["health"].lower() or "medical" in top["health"].lower() or "health" in top["health"].lower()
    assert "student" in top["education"].lower()


def test_soc_value_divides_aggregate_codes(theta):
    socs = theta.index
    agg = "51-2090" if "51-2090" not in socs else None
    members = socs[socs.str.startswith("51-209")]
    if agg and len(members):
        v = W.soc_value(pd.Series({agg: 1.0}), socs)
        assert v.sum() == pytest.approx(1.0) and np.allclose(v[members], 1 / len(members))
    assert W.soc_value(pd.Series({socs[0]: 0.5}), socs)[socs[0]] == 0.5


def test_joint_flow_splits_an_activitys_flow_by_software(m, vn, theta):
    caps = F.capabilities()
    theta_c = F.occupation_shares(F.listings(), F.product_capabilities(), caps)
    sv = W.soc_value(F.occupation_value(m.t.commodities, vn.mean(axis=1)), theta.index)
    J = W.joint(sv, theta, theta_c)
    assert (J.values >= 0).all()
    # an activity shares no more with software than flows through it
    through = theta.mul(sv, axis=0).sum()
    assert (J.sum(axis=1) <= through.reindex(J.index) + 1e-12).all()
    # and a capability shares no more with the work than its occupations earn
    assert (J.sum() <= theta_c.mul(sv.reindex(theta_c.index).fillna(0), axis=0).sum() + 1e-12).all()
