from app.guardrails.pii import redact


def test_card_number_masked_only_when_luhn_valid():
    r = redact("my card 4111 1111 1111 1111 was charged")
    assert "4111 1111" not in r.text and "••••1111" in r.text and r.kinds == ["card_number"]
    assert redact("order 1234 5678 9012 3456").text == "order 1234 5678 9012 3456"  # fails Luhn, kept


def test_ssn_account_email_phone():
    r = redact("SSN 123-45-6789, account number 9876543210, mail a@b.com, call 555-123-4567")
    assert "[SSN]" in r.text and "[NUMBER]" in r.text and "[EMAIL]" in r.text and "[PHONE]" in r.text
    assert set(r.kinds) == {"ssn", "account_number", "email", "phone"}


def test_amounts_and_dates_untouched():
    text = "A $214.37 charge on 2026-09-30 and $1,200 more"
    assert redact(text).text == text
