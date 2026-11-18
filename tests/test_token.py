"""`rce token set` and `rce token status`: store and check the RCE token without printing it."""

from __future__ import annotations

import base64
import json
import os
import pty
import select
import stat
import subprocess
import time

from conftest import RCE
from fake_rce import trial_status

NEW = "eyJnew.rce-token.SECRET"
DAY = 24 * 60 * 60


def output(result) -> str:
    return result.stdout + result.stderr


OWNER_ID = "6f1c2a52-0000-4000-8000-000000000001"  # the fake's user id


def jwt(exp: float, sub: str = OWNER_ID) -> str:
    """An RCE personal access token: a JWT with RCE's claims and an opaque signature."""

    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    claims = {
        "exp": int(exp),
        "iss": "rce",
        "jti": "jti-1",
        "org_id": 77,
        "sub": sub,
    }
    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(claims)}.signature-SECRET"


def use_token(rce, fake_rce, token: str) -> None:
    rce.write_rk_config({"token": token})
    fake_rce.token = token


def test_set_reads_the_token_from_stdin_and_creates_rks_file(rce, fake_rce):
    rce.rk_config.unlink()

    result = rce.run("token", "set", input=NEW + "\n")

    assert result.returncode == 0, result.stderr
    assert json.loads(rce.rk_config.read_text()) == {"token": NEW}
    assert stat.S_IMODE(rce.rk_config.stat().st_mode) == 0o600
    assert "SECRET" not in output(result)


def run_on_a_terminal(rce, *args: str, typed: str) -> tuple[int, str]:
    """Run `rce` on a pseudo-terminal, type `typed` at its prompt; return (exit code, screen)."""
    terminal, user_side = pty.openpty()
    process = subprocess.Popen(
        [str(RCE), *args],
        cwd=rce.cwd,
        env=rce.env,
        stdin=user_side,
        stdout=user_side,
        stderr=user_side,
        start_new_session=True,
    )
    os.close(user_side)

    def read(until: bytes | None) -> bytes:
        seen, deadline = b"", time.monotonic() + 20
        while time.monotonic() < deadline and not (until and until in seen.lower()):
            if not select.select([terminal], [], [], 0.1)[0]:
                continue
            try:
                chunk = os.read(terminal, 1024)
            except OSError:  # EIO: the child closed the terminal
                break
            if not chunk:
                break
            seen += chunk
        return seen

    try:
        screen = read(until=b"token")
        os.write(terminal, typed.encode() + b"\n")
        screen += read(until=None)
    finally:
        os.close(terminal)
        if process.poll() is None:  # still waiting at a prompt that never came
            process.kill()
    return process.wait(), screen.decode(errors="replace")


def test_set_on_a_terminal_reads_the_token_from_a_hidden_prompt(rce, fake_rce):
    code, screen = run_on_a_terminal(rce, "token", "set", typed=NEW)

    assert code == 0, screen
    assert json.loads(rce.rk_config.read_text()) == {"token": NEW}
    assert "token" in screen.lower()  # the prompt
    assert "SECRET" not in screen  # not echoed, not printed


def test_set_refuses_a_token_given_as_an_argument_without_echoing_it(rce, fake_rce):
    result = rce.run("token", "set", NEW)

    assert result.returncode == 2
    assert "stdin" in result.stderr
    assert "SECRET" not in output(result)
    assert NEW not in rce.rk_config.read_text()


def test_set_refuses_an_empty_token_and_leaves_rks_file_alone(rce, fake_rce):
    before = rce.rk_config.read_text()

    result = rce.run("token", "set", input="\n")

    assert result.returncode == 2
    assert rce.rk_config.read_text() == before


def test_set_keeps_other_keys_rk_stores_and_tightens_the_file_mode(rce, fake_rce):
    rce.write_rk_config({"token": "eyJold.rce-token.SECRET", "something_rk_stores": [1, 2]})
    rce.rk_config.chmod(0o644)

    result = rce.run("token", "set", input=NEW)

    assert result.returncode == 0, result.stderr
    assert json.loads(rce.rk_config.read_text()) == {"token": NEW, "something_rk_stores": [1, 2]}
    assert stat.S_IMODE(rce.rk_config.stat().st_mode) == 0o600


def test_status_shows_owner_expiry_and_trial_minutes_left(rce, fake_rce):
    use_token(rce, fake_rce, jwt(exp=4070908800))  # 2099-01-01
    fake_rce.trial = trial_status(mins_used=45, mins_limit=600)

    result = rce.run("token", "status", "--json")

    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status.pop("days_left") > 70 * 365
    assert status == {
        "source": str(rce.rk_config),
        "owner": {
            "id": OWNER_ID,
            "username": "dev@example.com",
            "full_name": "Dee Veloper",
            "email": "dev@example.com",
        },
        "token_owner_id": OWNER_ID,
        "organisation": "Example Org",
        "expires_at": "2099-01-01T00:00:00Z",
        "plan_status": "trial",
        "trial_minutes_left": 555,
    }
    assert len(fake_rce.requests_to("GET", "/api/v1/user/me")) == 1
    assert "SECRET" not in output(result)
    assert "warning" not in result.stderr


def test_status_reads_well_for_people(rce, fake_rce):
    use_token(rce, fake_rce, jwt(exp=4070908800))
    fake_rce.trial = trial_status(mins_used=45, mins_limit=600)

    result = rce.run("token", "status")

    assert result.returncode == 0, result.stderr
    assert "Dee Veloper <dev@example.com>" in result.stdout
    assert f"{OWNER_ID} (the token's own owner id matches)" in result.stdout
    assert "Example Org" in result.stdout
    assert "2099-01-01T00:00:00Z" in result.stdout
    assert "555 of 600 minutes left" in result.stdout
    assert "SECRET" not in output(result)


def test_status_shows_both_owners_when_the_token_names_another(rce, fake_rce):
    use_token(rce, fake_rce, jwt(exp=4070908800, sub="someone-else"))

    result = rce.run("token", "status")

    assert result.returncode == 0, result.stderr
    assert f"{OWNER_ID} (the token itself names someone-else)" in result.stdout
    assert "SECRET" not in output(result)


def test_status_of_a_token_without_an_expiry_still_checks_it_with_rce(rce, fake_rce):
    result = rce.run("token", "status", "--json")  # the fixture's token is not a JWT

    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert (status["expires_at"], status["days_left"]) == (None, None)
    assert status["token_owner_id"] is None
    assert status["owner"]["username"] == "dev@example.com"
    assert "SECRET" not in output(result)


def test_status_after_a_subscription_has_no_trial_minutes(rce, fake_rce):
    fake_rce.trial = {"plan_status": "exhausted", "trial": None}

    status = rce.json("token", "status")

    assert (status["plan_status"], status["trial_minutes_left"]) == ("exhausted", None)


def test_status_warns_when_the_token_expires_within_14_days(rce, fake_rce):
    use_token(rce, fake_rce, jwt(exp=time.time() + 3 * DAY + 3600))

    result = rce.run("token", "status", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["days_left"] == 3
    assert "warning" in result.stderr
    assert "3 days" in result.stderr
    assert "rce token set" in result.stderr
    assert "SECRET" not in output(result)


def test_status_does_not_warn_15_days_ahead(rce, fake_rce):
    use_token(rce, fake_rce, jwt(exp=time.time() + 15 * DAY))

    result = rce.run("token", "status")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_status_fails_clearly_when_the_token_has_expired(rce, fake_rce):
    use_token(rce, fake_rce, jwt(exp=time.time() - DAY))

    result = rce.run("token", "status", "--json")

    assert result.returncode == 4
    assert result.stdout == ""
    assert "expired" in result.stderr
    assert str(rce.rk_config) in result.stderr
    assert "rce token set" in result.stderr
    assert "SECRET" not in output(result)


def test_status_fails_clearly_when_rce_rejects_the_token(rce, fake_rce):
    rce.env["RCE_TOKEN"] = jwt(exp=4070908800)  # well-formed, unexpired, unknown to RCE

    result = rce.run("token", "status", "--json")

    assert result.returncode == 4
    assert result.stdout == ""
    assert "rejected" in result.stderr
    assert "$RCE_TOKEN" in result.stderr
    assert "SECRET" not in output(result)
