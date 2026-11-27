"""What scripts/03_run.py writes to results/ about software capabilities, against config/ and taxonomy/."""
import pandas as pd
import pytest
from plenty import model as M

CONFIG, RESULTS, TAXONOMY = M.CONFIG, M.ROOT / "results", M.ROOT / "taxonomy"


def test_capability_flows_add_up():
    flow = pd.read_csv(RESULTS / "capability_flow.csv", index_col=0)
    by_need = pd.read_csv(RESULTS / "capability_flow_by_need.csv", index_col=0)
    acct = pd.read_csv(RESULTS / "capability_flow_accounting.csv", index_col=0)
    for k in flow.index:
        assert by_need.loc[k].mean() == pytest.approx(flow.at[k, "flow"], abs=1e-9), k
    # the flows and what could not be attributed make up the need dollar
    assert flow.flow.sum() == pytest.approx(acct.at["flowed", "flow"], abs=1e-5)
    assert acct.flow.sum() == pytest.approx(1, abs=1e-5)
    assert flow.flow_distinctive.sum() == pytest.approx(flow.flow.sum(), abs=1e-8)


def test_leaderboards_sit_on_real_capabilities():
    boards = pd.read_csv(CONFIG / "boards.csv").fillna("")
    caps = pd.read_csv(CONFIG / "capabilities.csv").set_index("capability")
    flow = pd.read_csv(RESULTS / "capability_flow.csv", index_col=0)
    functions = pd.read_csv(RESULTS / "capability_table.csv", index_col=0)
    became = pd.read_csv(TAXONOMY / "function_map.csv").fillna("")
    assert set(boards.capability) <= set(flow.index)
    assert set(boards.function) <= set(functions.index)
    # the same boards the 18 functions carry
    assert set(boards.board) == set(caps.board.dropna())
    for b in boards.itertuples():
        assert b.capability in set(became.node[became.function == b.function]), b.board


def test_score_rationale_config_is_consistent():
    r = pd.read_csv(CONFIG / "score_rationale.csv", dtype=str)
    assert list(r.columns) == ["archetype", "capability", "rationale", "sources"]
    scores = pd.read_csv(CONFIG / "archetype_capabilities.csv").set_index("archetype")
    assert set(r.archetype) <= set(scores.index)
    assert set(r.capability) <= set(scores.columns)
    assert not r.duplicated(["archetype", "capability"]).any()
