from app.phone_numbers import normalize_phone_number


def test_normalizes_myanmar_numbers_by_default() -> None:
    assert normalize_phone_number("+95 961 695 448") == "+95961695448"
    assert normalize_phone_number("95961695448") == "+95961695448"
    assert normalize_phone_number("0961695448") == "+95961695448"


def test_normalizes_vietnam_numbers_when_country_code_is_explicit() -> None:
    assert normalize_phone_number("+84 961 695 448") == "+84961695448"
    assert normalize_phone_number("84961695448") == "+84961695448"
    assert normalize_phone_number("0084961695448") == "+84961695448"


def test_normalizes_clear_vietnam_local_prefixes() -> None:
    assert normalize_phone_number("0361695448") == "+84361695448"
    assert normalize_phone_number("0561695448") == "+84561695448"
    assert normalize_phone_number("0761695448") == "+84761695448"
    assert normalize_phone_number("0861695448") == "+84861695448"


def test_ambiguous_vietnam_09_local_number_requires_country_hint() -> None:
    assert normalize_phone_number("0961695448") == "+95961695448"
    assert normalize_phone_number("VN 0961695448") == "+84961695448"
    assert normalize_phone_number("vietnam: 0961695448") == "+84961695448"
