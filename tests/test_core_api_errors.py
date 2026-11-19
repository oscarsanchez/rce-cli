"""How `rce` reacts when the Core API refuses, fails or rate-limits a request."""

import pytest
from conftest import TOKEN
from fake_rce import GATEWAY_RATE_LIMIT, UPSTREAM_ERROR, Response, rce_error

DEVICES = "/api/v1/devices"


def test_a_rejected_token_is_refused_naming_its_source_not_its_value(rce, fake_rce):
    rce.env["RCE_TOKEN"] = "eyJexpired.rce-token.SECRET"

    result = rce.run("device", "list")

    assert result.returncode == 4
    assert "$RCE_TOKEN" in result.stderr
    assert "SECRET" not in result.stdout + result.stderr


def test_a_gateway_rate_limit_is_retried(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player")
    fake_rce.fail_next("GET", DEVICES, GATEWAY_RATE_LIMIT)

    assert [d["id"] for d in rce.json("device", "list")] == [351]
    assert len(fake_rce.requests_to("GET", DEVICES)) == 2


def test_other_rate_limits_are_retried_on_reads(rce, fake_rce):
    fake_rce.fail_next("GET", DEVICES, rce_error(429, "too_many_requests", "Slow down."))

    assert rce.json("device", "list") == []
    assert len(fake_rce.requests_to("GET", DEVICES)) == 2


def test_a_rate_limit_that_persists_is_refused(rce, fake_rce):
    fake_rce.fail_next("GET", DEVICES, GATEWAY_RATE_LIMIT, times=10)

    result = rce.run("device", "list")

    assert result.returncode == 4
    assert "rate" in result.stderr
    assert len(fake_rce.requests_to("GET", DEVICES)) == 4


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_passing_gateway_error_on_a_read_is_retried(rce, fake_rce, status):
    fake_rce.add_device(351, "Personal RCE Player")
    fake_rce.fail_next("GET", DEVICES, Response(status, {"detail": "Service unavailable"}))

    assert [d["id"] for d in rce.json("device", "list")] == [351]
    assert len(fake_rce.requests_to("GET", DEVICES)) == 2


def test_a_gateway_error_that_persists_exits_1_with_rces_message(rce, fake_rce):
    fake_rce.fail_next("GET", DEVICES, Response(503, {"detail": "Service unavailable"}), times=10)

    result = rce.run("device", "list")

    assert result.returncode == 1
    assert len(fake_rce.requests_to("GET", DEVICES)) == 4
    assert "503" in result.stderr
    assert "Service unavailable" in result.stderr
    assert TOKEN not in result.stderr


def test_an_unreachable_rce_exits_1_naming_the_url(rce, fake_rce):
    rce.env["RCE_API_URL"] = "http://127.0.0.1:9/api/v1"

    result = rce.run("device", "list")

    assert result.returncode == 1
    assert "http://127.0.0.1:9/api/v1" in result.stderr
    assert "Traceback" not in result.stderr


def test_other_rate_limits_are_not_retried_on_writes(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player")
    start = "/api/v1/devices/351/start"
    fake_rce.fail_next("POST", start, rce_error(429, "too_many_requests", "Slow down."), times=2)

    result = rce.run("device", "start", "351")

    assert result.returncode == 4
    assert "too_many_requests" in result.stderr
    assert len(fake_rce.requests_to("POST", start)) == 1


def test_a_gateway_rate_limit_is_retried_on_writes(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player")
    start = "/api/v1/devices/351/start"
    fake_rce.fail_next("POST", start, GATEWAY_RATE_LIMIT)

    assert rce.run("device", "start", "351").returncode == 0
    assert len(fake_rce.requests_to("POST", start)) == 2


def test_a_gateway_error_on_a_write_is_not_retried(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player")
    start = "/api/v1/devices/351/start"
    fake_rce.fail_next("POST", start, Response(503, "upstream connect error"), times=2)

    rce.run("device", "start", "351")

    assert len(fake_rce.requests_to("POST", start)) == 1  # one start never makes two Runs


def test_a_gateway_error_on_a_runs_own_read_is_not_retried(rce, fake_rce):
    """On a Run's port proxy a 503 means dev mode is off or it is still booting."""
    fake_rce.add_device(351, "Personal RCE Player", "stb", running=True)
    ecp = "/instance/uuid-351/api/v0/ports/8060/http/query/device-info"  # glossary-ok
    fake_rce.fail_next("GET", ecp, UPSTREAM_ERROR, times=2)

    result = rce.run("ecp", "351", "query/device-info")

    assert result.returncode == 1
    assert "RCE answered 503: upstream connect error" in result.stderr
    assert len(fake_rce.requests_to("GET", ecp)) == 1
