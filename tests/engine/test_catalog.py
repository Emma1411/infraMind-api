
import pytest
from pydantic import ValidationError

from models.catalog import PriceItem, PriceStatus
from services.engine.catalog import PriceNotAvailable, UnknownItem, get_catalog


def test_four_providers_are_loaded():
    assert set(get_catalog().providers) == {"hetzner", "aws", "azure", "gcp"}


def test_every_provider_has_date_and_source():
    for provider in get_catalog().providers.values():
        assert provider.as_of
        assert provider.source.strip()


def test_unavailable_service_is_never_priced():
    catalog = get_catalog()
    assert not catalog.is_priced("hetzner.object_storage")
    with pytest.raises(PriceNotAvailable):
        catalog.amount("hetzner.object_storage")


def test_missing_price_is_not_zero():
    catalog = get_catalog()
    assert catalog.item("azure.sql_database").status == PriceStatus.missing
    with pytest.raises(PriceNotAvailable):
        catalog.monthly_cost("azure.sql_database")


def test_hetzner_servers_are_flagged_to_verify():
    assert get_catalog().item("hetzner.cpx21").status == PriceStatus.to_verify


def test_real_free_price_is_allowed():
    catalog = get_catalog()
    assert catalog.is_priced("hetzner.ipv6_primary")
    assert catalog.amount("hetzner.ipv6_primary") == 0.0


def test_monthly_price_is_used_as_is():
    assert get_catalog().monthly_cost("hetzner.cpx11") == pytest.approx(20.49)


def test_hourly_price_is_converted_to_730_hours():
    assert get_catalog().monthly_cost("aws.rds.db_t4g_medium") == pytest.approx(46.72)


def test_fargate_example_matches_source():
    catalog = get_catalog()
    total = catalog.monthly_cost("aws.fargate.vcpu", 1) + catalog.monthly_cost("aws.fargate.memory", 2)
    assert total == pytest.approx(36.04, abs=0.01)


def test_per_gb_month_scales_with_quantity():
    assert get_catalog().monthly_cost("aws.rds.storage_gp3", 100) == pytest.approx(11.5)


def test_one_time_unit_does_not_convert_to_monthly():
    with pytest.raises(ValueError):
        get_catalog().monthly_cost("aws.nat_processing")


def test_unknown_item_raises():
    with pytest.raises(UnknownItem):
        get_catalog().item("aws.inexistant")


def test_model_rejects_amount_on_unavailable_item():
    with pytest.raises(ValidationError):
        PriceItem(id="x.y", category="compute", label="t", status="unavailable", unit="per_month", amount=0)


def test_model_rejects_priced_item_without_amount():
    with pytest.raises(ValidationError):
        PriceItem(id="x.y", category="compute", label="t", status="reported")


def test_aws_t3_small_matches_source():
    assert get_catalog().monthly_cost("aws.ec2.t3_small") == pytest.approx(15.26, abs=0.01)


def test_cloud_run_memory_example_matches_source():
    catalog = get_catalog()
    item_id = "gcp.cloud_run.memory_second_instance_based"
    price = catalog.amount(item_id)
    gross = price * 730 * 3600
    credit = price * catalog.item(item_id).free_quota
    assert gross == pytest.approx(5.256)
    assert credit == pytest.approx(0.90)
    assert gross - credit == pytest.approx(4.356)


def test_container_apps_hourly_prices_match_source():
    catalog = get_catalog()
    assert catalog.amount("azure.container_apps.vcpu_second") * 3600 == pytest.approx(0.0864)
    assert catalog.amount("azure.container_apps.memory_second") * 3600 == pytest.approx(0.0108)


def test_egress_tiers_are_priced():
    catalog = get_catalog()
    assert catalog.amount("aws.egress.tier_100gb_10tb") == pytest.approx(0.09)
    assert catalog.amount("gcp.egress.tier_1_1024gib") == pytest.approx(0.12)


def test_hetzner_included_traffic_is_known_for_two_plans_only():
    catalog = get_catalog()
    assert catalog.item("hetzner.ccx23").included_traffic_tb == 2
    assert catalog.item("hetzner.ccx43").included_traffic_tb is None
    assert catalog.item("hetzner.cpx21").included_traffic_tb == 2


def test_free_quota_requires_a_price():
    with pytest.raises(ValidationError):
        PriceItem(id="x.y", category="compute", label="t", status="missing", free_quota=10)


def test_every_provider_declares_its_reference_region():
    for provider in get_catalog().providers.values():
        assert provider.scope == "north_america"
        assert provider.reference_regions
        assert provider.region_note.strip()


def test_price_basis_mentions_regions_scope_and_date():
    text = get_catalog().price_basis("hetzner")
    assert "ash" in text and "hil" in text
    assert "Amérique du Nord" in text
    assert "2026-10" in text


def test_hetzner_ccx_prices_are_reported_and_extended():
    catalog = get_catalog()
    assert catalog.amount("hetzner.ccx13") == pytest.approx(50.99)
    assert catalog.amount("hetzner.ccx53") == pytest.approx(635.49)
    assert catalog.amount("hetzner.ccx63") == pytest.approx(1014.49)
    assert catalog.item("hetzner.ccx23").status == PriceStatus.reported


def test_hetzner_quotas_known_where_confirmed():
    catalog = get_catalog()
    assert catalog.item("hetzner.cpx51").included_traffic_tb == 5
    assert catalog.item("hetzner.ccx13").included_traffic_tb == 1
    assert catalog.item("hetzner.ccx23").included_traffic_tb == 2
    assert catalog.item("hetzner.ccx33").included_traffic_tb == 3
    assert catalog.item("hetzner.ccx43").included_traffic_tb is None
    assert catalog.item("hetzner.ccx53").included_traffic_tb is None


def test_azure_estimates_are_flagged_to_verify():
    catalog = get_catalog()
    for item_id in (
        "azure.sql.gp_vcore",
        "azure.sql.storage",
        "azure.postgresql.storage",
        "azure.backup.storage_lrs",
        "azure.backup.storage_zrs",
        "azure.backup.storage_grs",
        "azure.container_apps.requests",
    ):
        assert catalog.item(item_id).status == PriceStatus.to_verify, item_id


def test_azure_container_apps_requests_price_per_million():
    catalog = get_catalog()
    assert catalog.amount("azure.container_apps.requests") == pytest.approx(0.40)
    assert catalog.item("azure.container_apps.requests").free_quota == 2
