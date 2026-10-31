from models.project_spec import ProjectSpec
from services.engine.assumptions import TIERS, build_sizing, next_tier


def spec(**overrides) -> ProjectSpec:
    return ProjectSpec.model_validate(overrides)


def test_band_maps_to_tier():
    s = build_sizing(spec(traffic={"daily_users": "between_100_1000"}))
    assert s.tier == "s"
    assert s.users_per_day == 500


def test_peaks_bump_one_tier():
    s = build_sizing(spec(traffic={"daily_users": "between_100_1000", "has_peaks": True}))
    assert s.tier == "m"


def test_top_tier_does_not_overflow():
    assert next_tier("l") == "l"
    s = build_sizing(spec(traffic={"daily_users": "over_10000", "has_peaks": True}))
    assert s.tier == "l"


def test_unknown_traffic_assumes_middle_tier_and_says_so():
    s = build_sizing(spec())
    assert s.tier == "s"
    assert any("Trafic non précisé" in note for note in s.assumptions)


def test_egress_and_requests_are_derived_from_users():
    s = build_sizing(spec(traffic={"daily_users": "between_100_1000"}))
    assert s.egress_gb == 75.0
    assert s.requests_per_month == 450000


def test_no_database_means_no_db_storage():
    s = build_sizing(spec(data={"database_type": "none"}))
    assert not s.has_database
    assert s.db_gb == 0.0


def test_missing_database_type_assumes_relational():
    s = build_sizing(spec())
    assert s.has_database
    assert any("base relationnelle" in note for note in s.assumptions)


def test_uploads_add_file_storage():
    assert build_sizing(spec(data={"has_file_uploads": True})).files_gb == 20.0


def test_background_jobs_switch_to_instance_billing():
    assert build_sizing(spec(application={"has_background_jobs": True})).instance_billing
    assert not build_sizing(spec()).instance_billing


def test_tiers_are_ordered():
    assert TIERS == ("xs", "s", "m", "l")