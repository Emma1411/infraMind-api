import pytest

from models.project_spec import ProjectSpec
from services.engine.architectures import get_architectures
from services.engine.assumptions import TIERS, build_sizing
from services.engine.catalog import get_catalog
from services.engine.costing import BUILDERS
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable
from services.engine.graphs import build_graph, get_graphs

NO_FX = FxTable(per_usd={"USD": 1.0, "CAD": None, "EUR": None})

VARIANTS = [
    {},
    {"data": {"database_type": "none"}},
    {"data": {"has_file_uploads": True, "data_size": "gb_10_100"}},
    {"application": {"has_background_jobs": True}},
]

DB_NODE = {
    "aws_ec2_rds": "rds",
    "aws_fargate_rds": "rds",
    "gcp_cloud_run_sql": "sql",
    "azure_vm_postgres": "pg",
}
STORAGE_NODE = {
    "aws_ec2_rds": "s3",
    "aws_fargate_rds": "s3",
    "gcp_cloud_run_sql": "storage",
    "azure_vm_postgres": "blob",
}


def all_graphs(variant, tier):
    sizing = build_sizing(ProjectSpec.model_validate(variant), tier=tier)
    for arch_id, builder in BUILDERS.items():
        estimate = builder(get_catalog(), sizing)
        yield arch_id, estimate, build_graph(arch_id, estimate.lines)


def test_every_architecture_has_a_graph_starting_with_users():
    graphs = get_graphs()
    for arch in get_architectures():
        assert arch.id in graphs
        assert any(node.id == "users" for node in graphs[arch.id].nodes)


def test_node_costs_add_up_to_the_estimate():
    for variant in VARIANTS:
        for tier in TIERS:
            for arch_id, estimate, graph in all_graphs(variant, tier):
                total = sum(node.monthly_cost for node in graph.nodes)
                assert total == pytest.approx(estimate.total, abs=0.05), (arch_id, tier, variant)


def test_no_cost_line_is_left_without_a_node():
    for variant in VARIANTS:
        for tier in TIERS:
            for arch_id, _, graph in all_graphs(variant, tier):
                assert all(node.id != "other" for node in graph.nodes), (arch_id, tier, variant)


def test_database_node_disappears_without_database():
    for tier in TIERS:
        for arch_id, _, graph in all_graphs({"data": {"database_type": "none"}}, tier):
            ids = {node.id for node in graph.nodes}
            if arch_id in DB_NODE:
                assert DB_NODE[arch_id] not in ids
    for arch_id, _, graph in all_graphs({}, "s"):
        if arch_id in DB_NODE:
            assert DB_NODE[arch_id] in {node.id for node in graph.nodes}


def test_storage_node_appears_only_with_file_uploads():
    for arch_id, _, graph in all_graphs({"data": {"has_file_uploads": True}}, "s"):
        if arch_id in STORAGE_NODE:
            assert STORAGE_NODE[arch_id] in {node.id for node in graph.nodes}
    for arch_id, _, graph in all_graphs({}, "s"):
        if arch_id in STORAGE_NODE:
            assert STORAGE_NODE[arch_id] not in {node.id for node in graph.nodes}


def test_edges_only_connect_existing_nodes():
    for variant in VARIANTS:
        for arch_id, _, graph in all_graphs(variant, "s"):
            ids = {node.id for node in graph.nodes}
            assert graph.edges
            for edge in graph.edges:
                assert edge.source in ids and edge.target in ids, (arch_id, edge.id)


def test_evaluate_attaches_a_graph_to_every_architecture():
    result = evaluate(ProjectSpec(), fx=NO_FX)
    for item in result.ranking:
        assert item.graph is not None
        total = sum(node.monthly_cost for node in item.graph.nodes)
        assert total == pytest.approx(item.cost_low, abs=0.05)