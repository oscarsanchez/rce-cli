import pytest


@pytest.mark.parametrize("command", ["delete", "rm"])
def test_delete_explains_rce_cannot_delete_and_points_to_retire(rce, fake_rce, command):
    fake_rce.add_device(351, "Personal RCE Player", "stb")

    result = rce.run("device", command, "351")

    assert result.returncode == 2
    assert "RCE can't delete Cloud Devices" in result.stderr
    assert "rce device retire" in result.stderr
    assert fake_rce.requests == []
