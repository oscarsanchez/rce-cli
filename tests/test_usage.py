"""`rce usage`: trial minutes used and left, or billed minutes once subscribed."""

from datetime import datetime, timezone

import pytest

from fake_rce import trial_status

USER_USAGE = "/api/v1/usage/user"


def test_usage_on_the_trial_shows_minutes_used_and_left(rce, fake_rce):
    fake_rce.trial = trial_status(mins_used=45, mins_limit=600)

    usage = rce.json("usage")

    assert usage == {
        "plan_status": "trial",
        "trial": {"mins_used": 45, "mins_limit": 600, "mins_left": 555},
        "billed": None,
    }


def test_usage_on_the_trial_for_people(rce, fake_rce):
    fake_rce.trial = trial_status(mins_used=45, mins_limit=600)

    result = rce.run("usage")

    assert result.returncode == 0, result.stderr
    assert "45 of 600 min used" in result.stdout
    assert "555 min left" in result.stdout


def test_usage_when_the_trial_is_used_up(rce, fake_rce):
    fake_rce.trial = trial_status(mins_used=600, mins_limit=600)

    result = rce.run("usage")

    assert result.returncode == 0, result.stderr
    assert "used up" in result.stdout
    assert "AWS Marketplace" in result.stdout


def test_usage_after_subscribing_shows_this_months_billed_minutes(rce, fake_rce):
    fake_rce.trial = {"plan_status": "exhausted", "trial": None}
    fake_rce.usage_buckets = [
        {"start": "2026-11-01T00:00:00Z", "stop": "2026-12-01T00:00:00Z", "value": 42},
    ]

    usage = rce.json("usage")

    [request] = fake_rce.requests_to("GET", USER_USAGE)
    month = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    assert request.query["start"] == [month]
    assert request.query["interval"] == ["1mo"]
    assert usage["trial"] is None
    assert usage["billed"]["start"] == month
    assert usage["billed"]["minutes"] == 42
    assert usage["billed"]["cost_usd"] == pytest.approx(0.14, abs=0.001)


def test_billed_usage_for_people(rce, fake_rce):
    fake_rce.trial = {"plan_status": "exhausted", "trial": None}
    fake_rce.usage_buckets = [
        {"start": "2026-11-01T00:00:00Z", "stop": "2026-12-01T00:00:00Z", "value": 42},
    ]

    result = rce.run("usage")

    assert result.returncode == 0, result.stderr
    assert "42 min" in result.stdout
    assert "$0.14" in result.stdout
