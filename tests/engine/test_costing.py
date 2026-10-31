
import pytest
from dataclasses import replace
from models.project_spec import ProjectSpec
from services.engine.assumptions import TIERS, build_sizing
from services.engine.catalog import get_catalog
from services.engine.costing import BUILDERS, Estimate


def sizing_s(**overrides):
    base = {
        "traffic": {"daily_users": "between_100_1000"},
        "data": {"data_size": "gb_1_10"},
    }
    base.update(overrides)
    return build_sizing(ProjectSpec.model_validate(base))


def test_hetzner_s_cost():
    estimate = BUILDERS["hetzner_vps"](get_catalog(), sizing_s())
    assert estimate.total == pytest.approx(45.59, abs=0.02)
    assert estimate.complete


def test_aws_ec2_rds_s_cost():
    estimate = BUILDERS["aws_ec2_rds"](get_catalog(), sizing_s())
    assert estimate.total == pytest.approx(46.97, abs=0.05)


def test_aws_fargate_rds_s_cost():
    estimate = BUILDERS["aws_fargate_rds"](get_catalog(), sizing_s())
    assert estimate.total == pytest.approx(87.62, abs=0.05)



def test_gcp_request_based_s_cost_stays_in_free_quota():
    sizing = replace(sizing_s(), egress_gb=0)

    estimate = BUILDERS["gcp_cloud_run_sql"](
        get_catalog(),
        sizing,
    )

    run_lines = [
        line
        for line in estimate.lines
        if line.item_id.startswith("gcp.cloud_run")
    ]

    assert all(line.monthly == 0 for line in run_lines)
    assert estimate.total == pytest.approx(53.09, abs=0.02)


def test_gcp_instance_billing_uses_instance_prices():
    sizing = sizing_s(application={"has_background_jobs": True})
    estimate = BUILDERS["gcp_cloud_run_sql"](get_catalog(), sizing)

    ids = {line.item_id for line in estimate.lines}

    assert "gcp.cloud_run.vcpu_second_instance_based" in ids
    assert "gcp.cloud_run.vcpu_second_request_based" not in ids


def test_azure_s_cost_and_flagged_to_verify():
    estimate = BUILDERS["azure_vm_postgres"](get_catalog(), sizing_s())
    assert estimate.total == pytest.approx(92.48, abs=0.02)
    assert estimate.needs_verification


def test_no_database_removes_database_lines():
    sizing = build_sizing(
        ProjectSpec.model_validate({"data": {"database_type": "none"}})
    )

    estimate = BUILDERS["aws_ec2_rds"](get_catalog(), sizing)

    assert not any("rds" in line.item_id for line in estimate.lines)


def test_every_builder_works_for_every_tier_with_priced_items_only():
    for tier in TIERS:
        sizing = build_sizing(ProjectSpec(), tier=tier)

        for name, builder in BUILDERS.items():
            estimate = builder(get_catalog(), sizing)

            assert estimate.total > 0, (name, tier)
            assert estimate.complete, (
                name,
                tier,
                [u.item_id for u in estimate.unpriced],
            )


def test_missing_price_is_reported_never_counted_as_zero():
    estimate = Estimate(get_catalog())
    estimate.add("azure.sql_database", 1, "test")

    assert not estimate.complete
    assert estimate.total == 0
    assert estimate.unpriced[0].item_id == "azure.sql_database"


def test_unavailable_service_is_reported_never_counted_as_zero():
    estimate = Estimate(get_catalog())
    estimate.add("hetzner.object_storage", 10, "test")

    assert not estimate.complete
    assert estimate.lines == []


def test_hetzner_warns_when_files_have_no_object_storage():
    sizing = sizing_s(
        data={
            "data_size": "gb_1_10",
            "has_file_uploads": True,
        }
    )

    estimate = BUILDERS["hetzner_vps"](get_catalog(), sizing)

    assert any("Object Storage" in warning for warning in estimate.warnings)


def test_egress_tiers_charge_above_free_quota():
    estimate = Estimate(get_catalog())

    from services.engine.costing import AWS_EGRESS

    estimate.add_tiered_egress(AWS_EGRESS, 750)

    assert estimate.total == pytest.approx(58.5)

def test_gcp_request_based_charges_beyond_free_quota():
    sizing = build_sizing(ProjectSpec(), tier="m")
    estimate = BUILDERS["gcp_cloud_run_sql"](get_catalog(), sizing)
    by_id = {line.item_id: line for line in estimate.lines}

    assert by_id["gcp.cloud_run.vcpu_second_request_based"].monthly == pytest.approx(60.48, abs=0.02)
    assert by_id["gcp.cloud_run.memory_request_based"].monthly == pytest.approx(12.60, abs=0.02)
    assert by_id["gcp.cloud_run.requests"].monthly == pytest.approx(1.00, abs=0.02)


def test_gcp_tier_m_total():
    sizing = build_sizing(ProjectSpec(), tier="m")
    estimate = BUILDERS["gcp_cloud_run_sql"](get_catalog(), sizing)
    assert estimate.total == pytest.approx(267.64, abs=0.1)