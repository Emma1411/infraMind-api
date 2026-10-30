from utils.sanitize import mask_secrets


def test_masks_aws_key():
    assert "AKIAIOSFODNN7EXAMPLE" not in mask_secrets("clé: AKIAIOSFODNN7EXAMPLE ok")


def test_masks_password_assignment():
    result = mask_secrets("password: hunter2")
    assert "hunter2" not in result
    assert "password" in result


def test_masks_connection_string_credentials():
    result = mask_secrets("postgres://admin:s3cret@db.exemple.com/app")
    assert "s3cret" not in result
    assert "db.exemple.com" in result


def test_clean_text_is_unchanged():
    text = "Application de réservation avec React et PostgreSQL, 200 clients par jour."
    assert mask_secrets(text) == text