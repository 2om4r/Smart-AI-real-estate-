import pytest
from utils.password_policy import validate_password
from models import User

def test_valid_strong_password():
    is_valid, errors = validate_password("StrongP@ssw0rd2026!")
    assert is_valid is True
    assert len(errors) == 0

def test_password_too_short():
    is_valid, errors = validate_password("Short1!")
    assert is_valid is False
    assert any("12 characters" in e for e in errors)

def test_missing_uppercase():
    is_valid, errors = validate_password("lowercase1234!")
    assert is_valid is False
    assert any("uppercase" in e for e in errors)

def test_missing_lowercase():
    is_valid, errors = validate_password("UPPERCASE123!")
    assert is_valid is False
    assert any("lowercase" in e for e in errors)

def test_missing_digit():
    is_valid, errors = validate_password("NoDigitsHere!!")
    assert is_valid is False
    assert any("digit" in e for e in errors)

def test_missing_special_char():
    is_valid, errors = validate_password("NoSpecialChar123")
    assert is_valid is False
    assert any("special character" in e for e in errors)

def test_contains_email_local_part():
    # Pass raw email string
    is_valid, errors = validate_password("Omar1234!@#$", email="omar@example.com")
    assert is_valid is False
    assert any("local part" in e or "email" in e for e in errors)

def test_contains_username():
    # Construct a dummy User object
    dummy_user = User(username="johndoe", email="johndoe@test.com")
    is_valid, errors = validate_password("Johndoe123!@#", user=dummy_user)
    assert is_valid is False
    assert any("username" in e or "name" in e for e in errors)

def test_common_breached_password():
    is_valid, errors = validate_password("Password123!")
    assert is_valid is False
    assert any("breach" in e or "common" in e for e in errors)
