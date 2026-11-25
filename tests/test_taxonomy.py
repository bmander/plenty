"""The capability taxonomy (taxonomy/): the domain files obey the brief, the references between
domains resolve, and the flat tables are what build.py makes from them."""
import json, subprocess, sys
import pandas as pd
import pytest
from plenty import model as M

TAX = M.ROOT / "taxonomy"


@pytest.fixture(scope="module")
def docs():
    return {p.stem: json.loads(p.read_text()) for p in sorted((TAX / "domains").glob("*.json"))}


@pytest.fixture(scope="module")
def capabilities(docs):
    return {c["id"]: c for d in docs.values() for c in d["capabilities"]}


@pytest.fixture(scope="module")
def tasks(capabilities):
    return {t["id"]: t for c in capabilities.values() for t in c["tasks"]}


def test_domain_files_pass_the_brief_checks():
    r = subprocess.run([sys.executable, str(TAX / "check.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_every_domain_of_the_structure_has_a_file(docs):
    structure = json.loads((TAX / "structure.json").read_text())
    assert [d["id"] for d in structure["domains"]] and {d["id"] for d in structure["domains"]} == set(docs)


def test_ids_are_unique_across_domains(docs):
    ids = [c["id"] for d in docs.values() for c in d["capabilities"]]
    ids += [t["id"] for d in docs.values() for c in d["capabilities"] for t in c["tasks"]]
    assert len(ids) == len(set(ids))


def test_cross_references_resolve(capabilities, tasks):
    for cid, c in capabilities.items():
        for ref in c["see_also"]:
            assert ref != cid and (ref in capabilities or ref in tasks), f"{cid} -> {ref}"


def test_all_eighteen_functions_are_placed(docs, capabilities):
    functions = set(pd.read_csv(M.CONFIG / "capabilities.csv").capability)
    placed = {m["function"]: m["nodes"] for d in docs.values() for m in d["existing_function_map"]}
    assert functions <= set(placed)
    assert all(n in capabilities for nodes in placed.values() for n in nodes)


def test_a_checked_citation_names_the_page_read(capabilities, tasks):
    entries = [x for n in list(capabilities.values()) + list(tasks.values()) for x in n["crosswalk"]]
    assert entries
    for x in entries:
        assert x["basis"] in ("fetched", "memory")
        assert (x["basis"] == "fetched") == bool(x["url"]), x


def test_general_tools_sit_in_their_general_home(tasks):
    """The failure the taxonomy replaces: mainstream tools grouped by popularity, not function."""
    where = {}
    for tid, t in tasks.items():
        for p in t["onet_products"]:
            where.setdefault(p, set()).add(".".join(tid.split(".")[:2]))
    assert where["Python"] == where["C"] == where["C++"] == {"computing.languages"}
    assert where["Git"] == {"computing.dev_tooling"}
    assert where["Microsoft Excel"] == {"enterprise.spreadsheets"}
    assert where["Microsoft Access"] == {"computing.databases"}
    assert where["Dassault Systemes SolidWorks"] <= {"design.solid_modeling", "design.product_definition"}
    assert "computing.languages" not in where["Intuit QuickBooks"]


def test_flat_tables_are_in_sync_with_the_domain_files(tmp_path):
    subprocess.run([sys.executable, str(TAX / "build.py"), str(tmp_path)], check=True, capture_output=True)
    for name in ("capabilities.csv", "crosswalk.csv", "products_seed.csv", "function_map.csv"):
        assert (tmp_path / name).read_bytes() == (TAX / name).read_bytes(), f"{name}: run python taxonomy/build.py"
