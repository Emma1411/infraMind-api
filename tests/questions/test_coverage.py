from models.project_spec import ProjectSpec
from services.questions.coverage import FieldStatus, compute_coverage


def test_empty_spec_has_everything_missing():
    report = compute_coverage(ProjectSpec())
    assert not report.is_complete
    assert len(report.missing) == len(report.fields)


def test_extra_keys_are_ignored():
    spec = ProjectSpec.model_validate(
        {"application": {"app_type": "web_app", "inconnu": 1}, "foo": "bar"}
    )
    assert spec.application.app_type is not None


def test_known_field_is_not_missing():
    spec = ProjectSpec.model_validate({"application": {"app_type": "web_app"}})
    report = compute_coverage(spec)
    paths_missing = [f.path for f in report.missing]
    assert "application.app_type" not in paths_missing
    assert "application.has_background_jobs" in paths_missing


def test_unknown_answer_is_not_missing():
    spec = ProjectSpec.model_validate({"unknown": ["traffic.daily_users"]})
    report = compute_coverage(spec)
    status = {f.path: f.status for f in report.fields}
    assert status["traffic.daily_users"] == FieldStatus.UNKNOWN


def test_backups_skipped_without_database_and_uploads():
    spec = ProjectSpec.model_validate(
        {"data": {"database_type": "none", "has_file_uploads": False}}
    )
    report = compute_coverage(spec)
    paths = [f.path for f in report.fields]
    assert "backups.acceptable_data_loss" not in paths
    assert "data.data_size" not in paths


def test_backups_asked_when_database_present():
    spec = ProjectSpec.model_validate({"data": {"database_type": "relational"}})
    report = compute_coverage(spec)
    paths = [f.path for f in report.fields]
    assert "backups.acceptable_data_loss" in paths


def test_domain_status_values():
    spec = ProjectSpec.model_validate({"application": {"app_type": "web_app"}})
    status = compute_coverage(spec).domain_status()
    assert status["application"] == "partial"
    assert status["traffic"] == "missing"