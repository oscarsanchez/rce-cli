"""The recorded RCE answers in tests/fixtures/recorded/ hold no secret, no real
Run or organisation id and none of Roku's page, and "REDACTED" only where a
secret was.

Checked by pattern and by field, independently of scripts/record-live's own
redaction, so a re-record that slips a secret, or blanks a value that isn't
one, fails here before it is committed.
"""

import json
import re

import pytest

from fake_rce import RECORDED

FILES = sorted(RECORDED.glob("*.json"))
SECRET_FIELDS = {
    "serial_number", "email", "username", "user_email", "full_name", "account_name",
    "janus_pin", "janus_token", "credential", "creator_id", "idp_id",
}
SECRET_ELEMENTS = (
    "serial-number", "device-id", "advertising-id", "keyed-developer-id",
    "wifi-mac", "ethernet-mac", "network-name", "udn",
)
# device-info elements that may hold a redacted echo, such as a serial number in a name.
ECHO_ELEMENTS = ("friendly-device-name",)
RUN_UUID = "00000000-0000-4000-8000-000000000000"  # the one `instance_uuid` a recording may hold
ORGANISATION_ID = 1
LEAKS = {
    "a JWT (the token)": re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}"),
    "an email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "a serial number": re.compile(r"\bXY[0-9A-Z]{10}\b"),
    "a MAC address": re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b"),
    "a Run's UUID": re.compile(
        rf"\b(?!{RUN_UUID})[0-9a-fA-F]{{8}}-(?:[0-9a-fA-F]{{4}}-){{3}}[0-9a-fA-F]{{12}}\b"
    ),
    "Roku's copyright notice": re.compile(r"Roku, Inc\."),
}


def leaks(text: str) -> list[str]:
    """What a recording holds that must not be published."""
    found = [what for what, pattern in LEAKS.items() if pattern.search(text)]
    ids = organisation_ids(json.loads(text)["body"])
    return found + [f"an organisation id ({id})" for id in ids if id != ORGANISATION_ID]


def organisation_ids(value, parent=""):
    """Every organisation.id anywhere in a JSON body."""
    if isinstance(value, list):
        for item in value:
            yield from organisation_ids(item, parent)
    elif isinstance(value, dict):
        for key, item in value.items():
            if (parent, key) == ("organisation", "id"):
                yield item
            yield from organisation_ids(item, key)


def secret_values(value, parent=""):
    """Every value of a secret field, and organisation.name, anywhere in a JSON body."""
    if isinstance(value, list):
        for item in value:
            yield from secret_values(item, parent)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in SECRET_FIELDS or (parent, key) == ("organisation", "name"):
                yield key, item
            else:
                yield from secret_values(item, key)


def redacted_outside_secrets(value, parent=""):
    """The (parent, key) of every value that reads REDACTED outside a secret field."""
    if isinstance(value, list):
        for item in value:
            yield from redacted_outside_secrets(item, parent)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in SECRET_FIELDS or (parent, key) == ("organisation", "name"):
                continue
            if isinstance(item, str) and "REDACTED" in item:
                yield parent, key
            yield from redacted_outside_secrets(item, key)


def test_there_are_recordings():
    assert len(FILES) >= 14


def test_the_accounts_id_is_redacted():
    assert json.loads((RECORDED / "user-me.json").read_text())["body"]["id"] == "REDACTED"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_nothing_unpublishable_in_a_recording(path):
    assert leaks(path.read_text()) == []


def bad(name: str, old: str, new: str) -> str:
    """A committed recording with `old` made `new`, as a careless re-record could leave it."""
    text = (RECORDED / f"{name}.json").read_text()
    assert old in text
    return text.replace(old, new)


@pytest.mark.parametrize(
    "name, old, new, leak",
    [
        ("device-running", RUN_UUID, "12345678-1234-4123-8123-123456789abc", "a Run's UUID"),
        ("user-me", '"id": 1,', '"id": 2,', "an organisation id (2)"),
        ("install-installed", "<font", "<!-- (c) 2019-2023 Roku, Inc. --><font", "Roku's copyright notice"),
    ],
    ids=["run-uuid", "organisation-id", "copyright"],
)
def test_the_guard_fails_a_bad_recording(name, old, new, leak):
    assert leaks(bad(name, old, new)) == [leak]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_secret_fields_are_redacted(path):
    body = json.loads(path.read_text())["body"]
    if isinstance(body, str):
        for element in SECRET_ELEMENTS:
            for value in re.findall(rf"<{element}>([^<]*)</{element}>", body):
                assert value == "REDACTED", f"{path.name}: <{element}>"
        for value in re.findall(r'"dev_id":\s*"([^"]*)"', body):
            assert value == "REDACTED", f"{path.name}: dev_id"
    else:
        for key, value in secret_values(body):
            assert value in (None, "REDACTED"), f"{path.name}: {key}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_redacted_only_where_a_secret_was(path):
    answer = json.loads(path.read_text())
    body = answer.pop("body")
    assert "REDACTED" not in json.dumps(answer), f"{path.name}: request or headers"
    if isinstance(body, str):
        allowed = "|".join(SECRET_ELEMENTS + ECHO_ELEMENTS)
        rest = re.sub(rf"<({allowed})>[^<]*</\1>", "", body)
        rest = re.sub(r'"dev_id":\s*"REDACTED"', "", rest)
        assert "REDACTED" not in rest, f"{path.name}: REDACTED outside a secret element"
    else:
        account_id = [("", "id")] if path.stem == "user-me" else []
        misplaced = [p for p in redacted_outside_secrets(body) if p not in account_id]
        assert misplaced == [], f"{path.name}: REDACTED outside a secret field"
