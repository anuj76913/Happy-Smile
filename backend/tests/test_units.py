from datetime import datetime, timedelta

import pytest

from happysmile import calling_window
from happysmile.config import IST
from happysmile.experiment import bucket
from happysmile.phone import display, normalise_mobile
from happysmile.security import hash_password, verify_password


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "+919876543210"),
    ("+91 98765-43210", "+919876543210"),
    ("098765 43210", "+919876543210"),
    ("91 98765 43210", "+919876543210"),
    ("(+91) 6000 000 000", "+916000000000"),
    ("5876543210", None),      # must start 6-9
    ("987654321", None),       # 9 digits
    ("98765432101", None),     # 11 digits, no leading 0
    ("+44 7700 900123", None),
    ("", None),
])
def test_normalise_mobile(raw, expected):
    assert normalise_mobile(raw) == expected


def test_display():
    assert display("+919876543210") == "+91 98765 43210"


def at(h, m, day_offset=0):
    d = datetime.now(IST).date() + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=IST)


def test_calling_window():
    assert calling_window.can_call_now(at(9, 0))
    assert calling_window.can_call_now(at(14, 20))
    assert calling_window.can_call_now(at(20, 45))
    assert not calling_window.can_call_now(at(20, 50))   # EC-TIME-02: last 15 minutes
    assert not calling_window.can_call_now(at(23, 30))   # EC-TIME-01
    assert not calling_window.can_call_now(at(8, 59))
    assert calling_window.next_opening(at(23, 30)) == at(9, 0, 1)
    assert calling_window.next_opening(at(7, 0)) == at(9, 0)


def test_scheduled_time_rules():
    now = at(14, 20)
    assert calling_window.is_valid_scheduled_time(at(18, 0), now)
    assert not calling_window.is_valid_scheduled_time(at(13, 0), now)        # past
    assert not calling_window.is_valid_scheduled_time(at(22, 0), now)        # outside window
    assert not calling_window.is_valid_scheduled_time(at(10, 0, 9), now)     # too far ahead


def test_bucket_is_deterministic_and_balanced():
    assert bucket("s", "lead-1") == bucket("s", "lead-1")
    assert bucket("s", "lead-1") != bucket("t", "lead-1")
    values = [bucket("salt", f"id-{i}") for i in range(20000)]
    share = sum(v < 0.5 for v in values) / len(values)
    assert 0.48 < share < 0.52
    assert sum(v < 0.2 for v in values) / len(values) == pytest.approx(0.2, abs=0.015)


def test_passwords():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")
