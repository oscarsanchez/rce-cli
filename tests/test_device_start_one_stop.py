"""`rce device start` sends one stop for a Run it stops, even when that stop fails."""

import math

from fake_rce import Response

STOP = "/api/v1/devices/351/stop"


def test_a_failed_start_whose_stop_fails_sends_no_second_stop(rce, fake_rce):
    fake_rce.add_device(351, "Personal RCE Player", "stb")
    rce.name_device("351", "player")
    fake_rce.run_hidden_reads = math.inf
    fake_rce.fail_next("POST", STOP, Response(500, {"detail": "Internal Server Error"}))

    result = rce.run("device", "start", "player", "--no-wait", "--timeout", "1")

    assert result.returncode == 5
    assert "could not stop the Run of player (351)" in result.stderr
    assert "stop it with `rce device stop player`" in result.stderr
    assert len(fake_rce.requests_to("POST", STOP)) == 1
