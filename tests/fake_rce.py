"""A local stand-in for RCE, for Seam A tests.

The fake serves RCE's Core API under /api/v1 over plain HTTP on 127.0.0.1, and
each running Cloud Device's Instance API at the path RCE gives it (`INSTANCE_API`). Its
answers are built from RCE's real ones, recorded by scripts/record-live into
tests/fixtures/recorded/ (`recorded(name)`): the fake sets the ids, names, states
and identity each test relies on, and the recording gives everything else. The
README there lists what the fake still invents, and why.

Device lifecycle, as RCE runs it: `POST .../start` puts a Cloud Device in
`pending` with a Run that has no address yet. Its 202 shows no Run
(`running_device: null`, as on Run 4615), and reads of the Cloud Device show
none for `run_hidden_reads` more reads (default 0: the next read shows it).
After `boot_delay` seconds it is `running`, its Run has an address on this
server, and that address's `input/ready` answers true after a further
`input_delay`. `POST .../stop` takes it to `shutdown` after `stop_delay`. The
delays default to 0 so tests stay fast; raise one to exercise a wait or a
timeout. Transitions happen when a request arrives, so the fake needs no
timers. Like the trial, it runs one Cloud Device at a time (429
trial_device_run_limit) unless a test sets `one_run_at_a_time` off, as for a Pool.

Extending it in later tickets:
- add a route: append (METHOD, path regex, handler) to `self.routes`; a handler
  takes (request, match) and returns a Response. Instance API routes match
  `INSTANCE_API` and can find their Run with `run_for(uuid)`;
- force an error or rate limit: `fail_next(method, path, Response(...))`, or
  close the connection without answering: `fail_next(method, path, NO_ANSWER)`;
- an accepted start: `start_delay` holds its answer, `start_status` sets it:
  `NO_ANSWER.status` never sends it (closing the connection after `start_delay`),
  a gateway error (502, 503, 504) answers that though the Run was made;
- a Pool: `one_run_at_a_time = False` (a subscription), `take_after(method, path, id)`
  for a Cloud Device another job claims mid-call, `free_after(method, path, id, times)`
  for one whose Run another job stops, `delete_snapshot` for a Snapshot gone;
- inspect traffic: `self.requests` records every request the fake received.
- a Run address elsewhere: `address_origin` replaces this server in instance_api_url
  (another host, scheme or port, or no scheme).

A proxy for everything else: with `rce` pointed at the fake as its HTTP(S) proxy
(`Rce.proxy_through`), a request for any other host comes here instead of leaving
the machine. The fake answers it 502 and records it in `self.proxied`: a CONNECT
with its target (host:port), or a plain-HTTP request with its full URL.

WebSocket TCP bridges: a running Run's `ports/<port>` answers a WebSocket
upgrade like RCE's bridge (binary frames only; a text frame closes it with
1003). `bridge(port)` scripts what that port does, in both directions: the
frames it sends each client, whether it echoes, and every byte it received.
The bridge closes when its Run ends. With `dev_mode` off it refuses the
upgrade with RCE's 503 `upstream connect error`.

The installer (port 80, through the Run's HTTP port proxy) takes the RCE
token in X-Authorization, because Authorization carries the device's Digest
(user `rokudev`, `dev_password`). It answers installs with the recorded Install
pages: installed, identical, a form without an archive (200), and failed (400,
and the dev app is gone) for the next install after a test sets
`next_install_fails`. It takes a screenshot only while the dev app is in the
foreground (`active_app`), and answers a missing or wrong Digest with a 401 Digest
challenge. `forms` records every multipart form it parsed.

The dev app: launching it (ECP launch/dev) "runs" the installed zip, so the
console bridge (port 8085) sends each client the lines its BrightScript
`print`s as string literals (`console_output`), after the scripted frames.
"""

from __future__ import annotations

import base64
import copy
import email
import email.policy
import hashlib
import io
import json
import secrets
import re
import select
import socket
import struct
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

API = "/api/v1"
RECORDED = Path(__file__).parent / "fixtures" / "recorded"


def recorded_answer(name: str) -> dict:
    """A recorded RCE answer (scripts/record-live): request, status, headers and body."""
    return json.loads((RECORDED / f"{name}.json").read_text())


def recorded(name: str) -> object:
    """The body of a recorded RCE answer, a fresh copy each call."""
    return recorded_answer(name)["body"]


INSTANCE_API = r"/instance/([^/]+)/api/v0"  # RCE's path; glossary-ok


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes
    at: float = field(default_factory=time.monotonic)  # when the fake received it

    def json(self) -> object:
        return json.loads(self.body)


@dataclass
class Response:
    status: int = 200
    body: object = None  # JSON-encoded unless bytes or str
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0  # seconds the answer is held, outside the fake's lock

    def encode(self) -> tuple[bytes, str]:
        if isinstance(self.body, bytes):
            return self.body, "application/octet-stream"
        if isinstance(self.body, str):
            return self.body.encode(), "text/plain"
        if self.body is None:
            return b"", "application/json"
        return json.dumps(self.body).encode(), "application/json"


def rce_error(status: int, code: str, message: str) -> Response:
    """A FastAPI error body with a code, e.g. 429 trial_device_run_limit."""
    return Response(status, {"detail": {"code": code, "message": message}})


# Not an answer: the fake closes the connection instead (after its delay), as a
# dropped one does. Any Response with status 0 is one.
NO_ANSWER = Response(0)

# Gateway rate limit: the request never reached the Core API service.
GATEWAY_RATE_LIMIT = Response(429, "local_rate_limited", {"x-local-rate-limit": "true"})
TRIAL_RUN_LIMIT = rce_error(
    429, "trial_device_run_limit", "Trial users may only run one device at a time."
)
TRIAL_EXHAUSTED = rce_error(402, "trial_exhausted", "Your free trial has ended.")
SNAPSHOT_NOT_READY = rce_error(409, "snapshot_not_ready", "The snapshot is still uploading.")
# The spec names no code for these two; the messages follow its descriptions.
ALREADY_RUNNING = Response(409, {"detail": "The device is already running or locked."})
OVER_CAP = Response(400, {"detail": "max_runtime exceeds the allowed maximum."})
TRIAL_OVER_CAP = rce_error(
    400, "trial_max_runtime_exceeded", "max_runtime exceeds your remaining trial time."
)
# The spec's 422 for the Snapshot limit is an HTTPValidationError; the message is a guess.
SNAPSHOT_LIMIT = Response(
    422,
    {"detail": [{"loc": ["body"], "msg": "Snapshot limit reached for this device.", "type": "value_error"}]},
)

# What RCE's gateway answers when the device's port refuses, e.g. a console
# bridge with dev mode off.
UPSTREAM_ERROR = Response(
    503,
    "upstream connect error or disconnect/reset before headers. reset reason: connection failure",
)

FIRMWARE_VERSIONS = recorded("firmware-versions")  # in RCE's order


@dataclass
class Bridge:
    """What the fake's WebSocket TCP bridge for one port does."""

    frames: list[bytes] = field(default_factory=list)  # sent to each client on connect
    echo: bool = False  # send every binary frame back to its client
    received: bytearray = field(default_factory=bytearray)  # bytes from all clients
    connections: int = 0  # upgrades accepted


CONSOLE_PORT = 8085
PRINT_LITERAL = re.compile(r'^\s*print\s+"([^"]*)"', re.I | re.M)


def dev_app_prints(archive: bytes | None) -> list[bytes]:
    """The console lines a sideloaded zip's BrightScript prints as string
    literals; none unless it is a zip with a manifest, as the device needs."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive or b"")) as app:
            if "manifest" not in app.namelist():
                return []
            sources = [app.read(n).decode() for n in app.namelist() if n.endswith(".brs")]
    except zipfile.BadZipFile:
        return []
    return [f"{text}\n".encode() for source in sources for text in PRINT_LITERAL.findall(source)]


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def device_out(
    id: int, name: str, device_type: str = "stb", status: str = "shutdown"
) -> dict:
    """A DeviceOut, as the recorded GET /devices/{id} gives it."""
    base, live = 2 * id + 295, 2 * id + 296  # 351 -> 997/998, like the live org
    return recorded("device") | {
        "id": id,
        "device_type": device_type,
        "name": name,
        "status": status,
        "created_at": "2026-11-11T17:02:11.123456Z",
        "serial_number": f"XY{id:010d}",
        "firmware_version_id": None,  # set by a Run; the live TV, never started, has none
        "firmware_version_display_name": None,
        # The Snapshot the last Run started from, not the live one: live, after
        # starting from base, 351 reports 997 "Initial snapshot" here.
        "last_snapshot_id": base,
        "last_snapshot_name": "Initial snapshot",
        "snapshots": [base, live],
        "running_device": None,
    }


USER_ID = "6f1c2a52-0000-4000-8000-000000000001"


def user_out() -> dict:
    """A UserOut, as the recorded GET /user/me gives it, for the fake's user."""
    user = recorded("user-me")
    user["organisation"]["name"] = "Example Org"
    return user | {
        "id": USER_ID,
        "username": "dev@example.com",
        "full_name": "Dee Veloper",
        "email": "dev@example.com",
    }


def trial_status(mins_used: int = 0, mins_limit: int = 600) -> dict:
    """A TrialStatusOut, as recorded for a trial with minutes left."""
    status = recorded("trial-status")
    status["trial"] |= {"mins_used": mins_used, "mins_limit": mins_limit}
    return status | {"plan_status": "trial" if mins_used < mins_limit else "exhausted"}


def snapshot_out(id: int, name: str, base: bool = False, live: bool = False) -> dict:
    """A SnapshotOut, as the recorded GET /devices/{id}/snapshots/{sid} gives it."""
    return recorded("snapshot") | {
        "id": id,
        "name": name,
        "created_at": "2026-11-11T15:35:01.531252Z",
        "parent_id": None,
        "started_at": None,
        "firmware_version_id": None,
        "firmware_version_display_name": None,
        "ready": True,
        "live": live,
        "base": base,
    }


# Run credentials the fake hands out. Tests assert none of them reach output.
WEBRTC_SECRETS = ("janus-pin-SECRET", "janus-token-SECRET", "turn-credential-SECRET")


def running_device(run_id: int, instance_uuid: str, host: str) -> dict:
    """A DeviceInstanceInfo as recorded, with WebRTC credentials of the fake's own."""
    pin, token, credential = WEBRTC_SECRETS
    run = recorded("device-running")["running_device"]
    return run | {
        "id": run_id,
        "creator_id": USER_ID,
        "created_at": "2026-11-16T21:00:00Z",
        "started_at": "2026-11-16T21:00:05Z",
        "running_at": "2026-11-16T21:01:11Z",
        "snapshot_id": 998,
        "snapshot_name": "Live snapshot",
        "instance_uuid": instance_uuid,
        "instance_api_url": f"https://{host}/instance/{instance_uuid}",  # glossary-ok
        "firmware_version_id": "395",
        "max_runtime": 3600,
        "janus_pin": pin,
        "janus_token": token,
        "janus_websocket_url": f"wss://{host}/instance/{instance_uuid}/janus",  # glossary-ok
        "janus_ice_servers": [
            server | {"username": "u", "credential": credential} for server in run["janus_ice_servers"]
        ],
    }


# The device's 403 body in Limited mode, live on 351 (2026-11-16, ticket 06).
ECP_FORBIDDEN = "ECP command not allowed in Limited mode."


def set_element(xml: str, tag: str, value: str) -> str:
    """`xml` with the text of its <tag> element set to `value`."""
    return re.sub(rf"<{tag}>[^<]*</{tag}>", lambda _: f"<{tag}>{value}</{tag}>", xml)


def device_info(ecp_mode: str, developer_enabled: bool, in_guided_setup: bool = False) -> str:
    """ECP query/device-info as recorded after setup, with the settings each test sets.
    Before setup it also has <in-guided-setup>true</in-guided-setup> (live, ticket 06)."""
    info = set_element(recorded("ecp-device-info"), "ecp-setting-mode", ecp_mode)
    info = set_element(info, "developer-enabled", "true" if developer_enabled else "false")
    if in_guided_setup:
        info = info.replace("</device-info>", "\t<in-guided-setup>true</in-guided-setup>\n</device-info>")
    return info


def active_app_answer(app: str) -> str:
    """ECP query/active-app as recorded, naming `app` (an <app> element)."""
    return re.sub(r"<app[ >].*</app>", lambda _: app, recorded("ecp-active-app"))


SCREENSHOT_NOT_OK = [("error", "Screenshot not ok")]  # recorded, with no dev app in the foreground
SCREENSHOT_JPEG = b"\xff\xd8\xff\xe0fake-jpeg-of-the-dev-app\xff\xd9"


def recorded_response(name: str) -> Response:
    """A recorded answer as the fake sends it: status, headers and body."""
    answer = recorded_answer(name)
    return Response(answer["status"], answer["body"], answer["headers"])


RENDERED_MESSAGE_LINE = re.compile(r"^\s*Shell\.create\('Roku\.Message'\).*\n", re.M)


def inspect_page(messages: list[tuple[str, str]]) -> str:
    """The installer's Utilities page (plugin_inspect) as recorded with no
    screenshot, rendering these messages as it does."""
    rendered = "".join(
        f"      Shell.create('Roku.Message').trigger('Set message type', '{kind}')"
        f".trigger('Set message content', '{text}').trigger('Render', node);\n"
        for kind, text in messages
    )
    page = RENDERED_MESSAGE_LINE.sub(lambda _: rendered, recorded("installer-inspect"), count=1)
    texts = " ".join(text for _, text in messages)  # the page also keeps them in a hidden <font>
    return re.sub(r"(<font color=\"red\">)[^<]*(</font>)", lambda m: f"{m[1]}{texts}{m[2]}", page)


# The device's 401 challenge, as recorded; each one the fake sends has a fresh nonce.
DIGEST_CHALLENGE = recorded_answer("installer-wrong-password")["headers"]["www-authenticate"]


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _digest_fields(header: str) -> dict[str, str]:
    return {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|[^,\s]+)', header)}


DIGEST_REALM = _digest_fields(DIGEST_CHALLENGE)["realm"]


class FakeRCE:
    def __init__(self, token: str):
        self.token = token
        self.devices: dict[int, dict] = {}
        self.snapshots: dict[int, list[dict]] = {}  # device id -> its Snapshots
        self.user = user_out()
        self.trial = trial_status()
        self.requests: list[Request] = []
        self.proxied: list[Request] = []  # what `rce` sent toward any other host (see above)
        self._scripted: list[tuple[str, str, Response]] = []
        self._takes: list[tuple[str, str, int]] = []  # see take_after
        self._frees: list[list] = []  # [method, path, device id, requests left]: see free_after
        self.deleted_snapshots: set[int] = set()  # see delete_snapshot
        self._next_run_id = 9000
        self._next_device_id = 400
        # Lifecycle timing in seconds (see the module docstring).
        # Where a Run's instance_api_url points: None is this server. Live RCE gives it
        # with its scheme, though the spec says without; a test may set any origin.
        self.address_origin: str | None = None
        self.boot_delay = 0.0
        self.input_delay = 0.0
        self.stop_delay = 0.0
        self.start_delay = 0.0  # an accepted start's answer is held this long
        self.start_status = 202  # an accepted start's answer; NO_ANSWER.status: none
        self.run_hidden_reads = 0  # reads after a start that still show no Run; math.inf: never
        self.one_run_at_a_time = True  # the trial's limit; False: a subscription, many Runs at once
        self._hidden_reads: dict[int, float] = {}  # device id -> reads left that show no Run
        self.snapshot_delay = 0.0  # a new Snapshot is ready this long after it is taken
        self.snapshot_limit = 25  # Snapshots per Cloud Device, like the org's max_snapshots
        self._next_snapshot_id = 1001
        self._saving: dict[int, tuple[dict, float]] = {}  # Snapshot id -> (it, ready when)
        self._due: dict[int, tuple[str, float]] = {}  # device id -> (next status, when)
        self._input_ready_at: dict[str, float] = {}  # Run's instance_uuid -> when
        self.usage_buckets: list[dict] = []  # GET /usage/user buckets (billed minutes)
        # Off: bridges answer 503 upstream connect error, and ECP device-info
        # reports developer-enabled false.
        self.dev_mode = True
        # A fresh Cloud Device is in guided setup until a person links it to a
        # Roku account; ECP device-info reports it as in-guided-setup.
        self.in_guided_setup = False
        self.bridges: dict[int, Bridge] = {}  # device port -> its bridge
        self.routes = [
            ("GET", re.compile(rf"{API}/devices"), self._list_devices),
            ("POST", re.compile(rf"{API}/devices"), self._create_device),
            ("GET", re.compile(rf"{API}/devices/(\d+)"), self._get_device),
            ("PATCH", re.compile(rf"{API}/devices/(\d+)"), self._update_device),
            ("GET", re.compile(rf"{API}/user/me"), lambda r, m: Response(200, self.user)),
            ("GET", re.compile(rf"{API}/usage/trial-status"), lambda r, m: Response(200, self.trial)),
            ("GET", re.compile(rf"{API}/devices/(\d+)/snapshots"), self._list_snapshots),
            ("GET", re.compile(rf"{API}/devices/(\d+)/snapshots/(\d+)"), self._get_snapshot),
            ("POST", re.compile(rf"{API}/devices/(\d+)/snapshots"), self._take_snapshot),
            ("POST", re.compile(rf"{API}/devices/(\d+)/start"), self._start_device),
            ("POST", re.compile(rf"{API}/devices/(\d+)/stop"), self._stop_device),
            ("GET", re.compile(rf"{API}/firmwareVersions"), self._firmware_versions),
            ("GET", re.compile(rf"{API}/usage/user"), self._user_usage),
            ("GET", re.compile(rf"{INSTANCE_API}/input/ready"), self._input_ready),
            ("POST", re.compile(rf"{INSTANCE_API}/input/keypress/(.+)"), self._keypress),
            ("POST", re.compile(rf"{INSTANCE_API}/xi/developer-settings-combo"), self._dev_settings),
            ("GET", re.compile(rf"{INSTANCE_API}/ports/8060/http/(.*)"), self._ecp),
            ("POST", re.compile(rf"{INSTANCE_API}/ports/8060/http/(.*)"), self._ecp),
            ("POST", re.compile(rf"{INSTANCE_API}/ports/80/http/plugin_install"), self._install),
            ("POST", re.compile(rf"{INSTANCE_API}/ports/80/http/plugin_inspect"), self._inspect),
            ("GET", re.compile(rf"{INSTANCE_API}/ports/80/http/pkgs/dev\.jpg"), self._screenshot),
            ("GET", re.compile(rf"{INSTANCE_API}/ports/(\d+)"), self._open_bridge),
        ]
        # The installer (port 80): the device's Dev Password, the archive it
        # has installed, whether the next install fails (as recorded), and
        # every multipart form it parsed ({field: (filename, bytes)}).
        self.dev_password = "dev-PASSWORD-secret"
        self.installed_archive: bytes | None = None
        self.next_install_fails = False
        self.forms: list[dict[str, tuple[str | None, bytes]]] = []
        self._nonces: set[str] = set()
        # The Run's ECP: its "Control by mobile apps" setting (permissive,
        # limited or disabled), a sideloaded dev app, and the foreground app.
        self.ecp_mode = "permissive"
        self.dev_app_installed = True
        self.active_app = '<app id="dev" type="appl" version="1.0.0">My Dev App</app>'
        self.console_output: list[bytes] = []  # what the launched dev app prints
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(self))

    # -- lifecycle -------------------------------------------------------------

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self._server.server_address[1]}"

    @property
    def api_url(self) -> str:
        return f"http://{self.host}{API}"

    def start(self) -> None:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # -- state for tests -------------------------------------------------------

    def add_device(
        self, id: int, name: str, device_type: str = "stb", running: bool = False
    ) -> dict:
        device = device_out(id, name, device_type, "running" if running else "shutdown")
        base, live = device["snapshots"]
        self.snapshots[id] = [
            snapshot_out(base, "Initial snapshot", base=True),
            snapshot_out(live, "Live snapshot", live=True),
        ]
        if running:
            self._give_run(device, f"uuid-{id}")
        self.devices[id] = device
        return device

    def _give_run(self, device: dict, uuid: str) -> None:
        """A running Run on the Cloud Device, as someone else's start leaves it."""
        device["status"] = "running"
        device["running_device"] = running_device(self._next_run_id, uuid, self.host)
        device["running_device"]["instance_api_url"] = self.address(uuid)
        self._input_ready_at[uuid] = 0.0
        self._next_run_id += 1

    def take_after(self, method: str, path: str, device_id: int) -> None:
        """Once the fake has answered the next request to METHOD path, another caller
        starts a Run on the Cloud Device: a lost race, as two jobs claiming at once see."""
        self._takes.append((method, path, device_id))

    def free_after(self, method: str, path: str, device_id: int, times: int = 1) -> None:
        """Once the fake has answered the next `times` requests to METHOD path, the Run on
        the Cloud Device ends, as when another job stops it: a member a waiting caller sees
        free on a later look."""
        self._frees.append([method, path, device_id, times])

    def add_snapshot(self, device_id: int, snapshot_id: int, ready: bool = True) -> dict:
        """Give a Cloud Device another Snapshot, e.g. its Dev Snapshot; `ready=False` while
        RCE is still saving it. One it doesn't have reads as 404 (a deleted Snapshot)."""
        snapshot = snapshot_out(snapshot_id, "Dev snapshot") | {"ready": ready}
        self.snapshots[device_id].append(snapshot)
        self.devices[device_id]["snapshots"].append(snapshot_id)
        return snapshot

    def delete_snapshot(self, device_id: int, snapshot_id: int) -> None:
        """RCE deletes a Snapshot (as it does one unused for 180 days): reads of it, and a
        start from it, answer 404. RCE's real answer to that start is unverified."""
        self.snapshots[device_id] = [s for s in self.snapshots[device_id] if s["id"] != snapshot_id]
        self.devices[device_id]["snapshots"].remove(snapshot_id)
        self.deleted_snapshots.add(snapshot_id)

    def address(self, uuid: str) -> str:
        """A Run's address, as the Core API gives it in instance_api_url."""
        origin = self.address_origin or f"http://{self.host}"
        return f"{origin}/instance/{uuid}"  # RCE's path; glossary-ok

    def run_for(self, uuid: str) -> dict | None:
        """The running Cloud Device whose Run has this instance_uuid, if any."""
        return next(
            (
                d
                for d in self.devices.values()
                if d["status"] == "running" and d["running_device"]["instance_uuid"] == uuid
            ),
            None,
        )

    def bridge(self, port: int) -> Bridge:
        """The WebSocket TCP bridge to a device port, to script and inspect."""
        return self.bridges.setdefault(port, Bridge())

    def fail_next(self, method: str, path: str, response: Response, times: int = 1) -> None:
        """Answer the next `times` requests to METHOD path (no query) with `response`."""
        self._scripted += [(method, path, response)] * times

    def requests_to(self, method: str, path: str) -> list[Request]:
        return [r for r in self.requests if r.method == method and r.path == path]

    # -- dispatch --------------------------------------------------------------

    def handle(self, request: Request) -> Response:
        with self._lock:  # two `rce` processes may call at once
            return self._handle(request)

    def proxy(self, request: Request) -> Response:
        """A request `rce` sent toward another host, with the fake as its proxy."""
        with self._lock:
            self.proxied.append(request)
        return Response(502, "the fake RCE proxies nowhere")

    def _handle(self, request: Request) -> Response:
        response = self._answer(request)
        for take in [t for t in self._takes if t[:2] == (request.method, request.path)]:
            self._takes.remove(take)
            device = copy.deepcopy(self.devices[take[2]])  # the answer may hold the old one
            self._give_run(device, f"uuid-{device['id']}-taken")
            self.devices[device["id"]] = device
        for free in [f for f in self._frees if f[:2] == [request.method, request.path]]:
            free[3] -= 1
            if not free[3]:
                self._frees.remove(free)
                device = copy.deepcopy(self.devices[free[2]])  # the answer may hold the old one
                device.update(status="shutdown", running_device=None)
                self.devices[device["id"]] = device
        return response

    def _answer(self, request: Request) -> Response:
        self.requests.append(request)
        self._advance_lifecycle()
        for i, (method, path, response) in enumerate(self._scripted):
            if method == request.method and path == request.path:
                del self._scripted[i]
                return response
        # On port 80 the token moves to X-Authorization: Authorization is the installer's Digest.
        installer = re.fullmatch(rf"{INSTANCE_API}/ports/80/http/.*", request.path)
        token_header = "x-authorization" if installer else "authorization"
        if request.headers.get(token_header) != f"Bearer {self.token}":
            return Response(401, {"detail": "Not authenticated"})
        for method, pattern, handler in self.routes:
            match = pattern.fullmatch(request.path)
            if method == request.method and match:
                return handler(request, match)
        return Response(404, {"detail": "Not Found"})

    def _advance_lifecycle(self) -> None:
        now = time.monotonic()
        for snapshot, when in list(self._saving.values()):
            if now >= when:
                snapshot["ready"] = True
                del self._saving[snapshot["id"]]
        for id, (status, when) in list(self._due.items()):
            if now < when:
                continue
            del self._due[id]
            device = self.devices[id]
            device["status"] = status
            if status == "shutdown":
                device["running_device"] = None
                self._hidden_reads.pop(id, None)
                continue
            run = device["running_device"]
            uuid = run["instance_uuid"]
            run["running_at"] = iso(datetime.now(timezone.utc))
            run["instance_api_url"] = self.address(uuid)
            self._input_ready_at[uuid] = now + self.input_delay

    # -- Core API routes -------------------------------------------------------

    def _read(self, device: dict) -> dict:
        """A Cloud Device as one read shows it: no Run yet while RCE lags its start."""
        left = self._hidden_reads.get(device["id"], 0)
        if not left:
            return device
        self._hidden_reads[device["id"]] = left - 1
        return device | {"running_device": None}

    def _list_devices(self, request: Request, match: re.Match) -> Response:
        return Response(200, [self._read(d) for d in self.devices.values()])

    def _get_device(self, request: Request, match: re.Match) -> Response:
        device = self.devices.get(int(match[1]))
        if device is None:  # RCE's answer for a device that isn't yours: an empty 403
            return Response(403, {"detail": ""})
        return Response(200, self._read(device))

    def _list_snapshots(self, request: Request, match: re.Match) -> Response:
        if int(match[1]) not in self.devices:
            return Response(403, {"detail": ""})
        return Response(200, self.snapshots[int(match[1])])

    def _get_snapshot(self, request: Request, match: re.Match) -> Response:
        if int(match[1]) not in self.devices:
            return Response(403, {"detail": ""})
        snapshot = next((s for s in self.snapshots[int(match[1])] if s["id"] == int(match[2])), None)
        if snapshot is None:  # the spec names no answer for this; FastAPI's usual 404
            return Response(404, {"detail": "Snapshot not found"})
        return Response(200, snapshot)

    def _take_snapshot(self, request: Request, match: re.Match) -> Response:
        device = self.devices.get(int(match[1]))
        if device is None:
            return Response(403, {"detail": ""})
        snapshots = self.snapshots[device["id"]]
        if len(snapshots) >= self.snapshot_limit:
            return SNAPSHOT_LIMIT
        snapshot = snapshot_out(self._next_snapshot_id, request.json()["name"])
        self._next_snapshot_id += 1
        snapshot.update(created_at=iso(datetime.now(timezone.utc)), ready=False)
        snapshots.append(snapshot)
        device["snapshots"].append(snapshot["id"])
        self._saving[snapshot["id"]] = (snapshot, time.monotonic() + self.snapshot_delay)
        return Response(201, snapshot)

    def _start_device(self, request: Request, match: re.Match) -> Response:
        device = self.devices.get(int(match[1]))
        if device is None:
            return Response(403, {"detail": ""})
        if device["status"] != "shutdown":
            return ALREADY_RUNNING
        if self.one_run_at_a_time and any(d["status"] != "shutdown" for d in self.devices.values()):
            return TRIAL_RUN_LIMIT
        body = request.json()
        if body["snapshot_id"] in self.deleted_snapshots:
            return Response(404, {"detail": "Snapshot not found"})
        uuid = f"uuid-{device['id']}-{self._next_run_id}"
        run = running_device(self._next_run_id, uuid, self.host)
        self._next_run_id += 1
        now = iso(datetime.now(timezone.utc))
        run.update(
            created_at=now,
            started_at=now,
            running_at=None,
            instance_api_url=None,  # RCE gives the address once the Run is running
            snapshot_id=body["snapshot_id"],
            firmware_version_id=body["firmware_version_id"],
            max_runtime=body["max_runtime"],
        )
        device.update(status="pending", running_device=run)
        self._due[device["id"]] = ("running", time.monotonic() + self.boot_delay)
        self._hidden_reads[device["id"]] = self.run_hidden_reads
        if self.start_status != 202:
            detail = HTTPStatus(self.start_status).phrase if self.start_status else ""
            return Response(self.start_status, {"detail": detail}, delay=self.start_delay)
        answer = device | {"running_device": None}  # as live RCE answers (Run 4615)
        return Response(202, answer, delay=self.start_delay)

    def _stop_device(self, request: Request, match: re.Match) -> Response:
        device = self.devices.get(int(match[1]))
        if device is None:
            return Response(403, {"detail": ""})
        self._due[device["id"]] = ("shutdown", time.monotonic() + self.stop_delay)
        return Response(202, device)

    def _firmware_versions(self, request: Request, match: re.Match) -> Response:
        device_type = request.query.get("device_type", [None])[0]
        return Response(
            200, [f for f in FIRMWARE_VERSIONS if device_type in (None, f["device_type"])]
        )

    def _user_usage(self, request: Request, match: re.Match) -> Response:
        query = {key: values[0] for key, values in request.query.items()}
        answer = recorded("usage-user") | {key: query[key] for key in ("start", "end", "interval")}
        return Response(200, answer | {"user_email": self.user["email"], "buckets": self.usage_buckets})

    def _create_device(self, request: Request, match: re.Match) -> Response:
        body = json.loads(request.body)
        device = self.add_device(self._next_device_id, body["name"], body["device_type"])
        self._next_device_id += 1
        self.user["organisation"]["current_devices"][body["device_type"]] += 1
        return Response(201, device)

    def _update_device(self, request: Request, match: re.Match) -> Response:
        device = self.devices.get(int(match[1]))
        if device is None:
            return Response(403, {"detail": ""})
        device.update(json.loads(request.body))
        return Response(200, device)

    # -- Instance API routes ---------------------------------------------------

    def _input_ready(self, request: Request, match: re.Match) -> Response:
        if self.run_for(match[1]) is None:
            return Response(404, {"detail": "Not Found"})
        ready = time.monotonic() >= self._input_ready_at[match[1]]
        return Response(200, recorded("input-ready") | {"ready": ready})

    def _keypress(self, request: Request, match: re.Match) -> Response:
        if self.run_for(match[1]) is None:
            return Response(404, {"detail": "Not Found"})
        if time.monotonic() < self._input_ready_at[match[1]]:
            return Response(503, {"detail": "On-screen input is unavailable."})
        # A KeyCommandResponse, as in the Instance API spec's example.
        return Response(
            200,
            {"response": "key-press", "response_id": "1", "status_code": 200, "status_message": "OK"},
        )

    def _dev_settings(self, request: Request, match: re.Match) -> Response:
        """The developer-settings shortcut: RCE presses the remote combo that opens the screen."""
        if self.run_for(match[1]) is None:
            return Response(404, {"detail": "Not Found"})
        if time.monotonic() < self._input_ready_at[match[1]]:
            return Response(503, {"detail": "On-screen input is unavailable."})
        return Response(200, None)

    def _ecp(self, request: Request, match: re.Match) -> Response:
        """ECP on port 8060, through the Run's HTTP port proxy (bodies pass through)."""
        if self.run_for(match[1]) is None:
            return Response(404, {"detail": "Not Found"})
        command = match[2]
        always = ("query/device-info", "query/active-app")  # answered before setup too
        if self.ecp_mode == "disabled" or (self.ecp_mode == "limited" and command not in always):
            return Response(403, ECP_FORBIDDEN)
        if request.method == "GET" and command == "query/device-info":
            return Response(200, device_info(self.ecp_mode, self.dev_mode, self.in_guided_setup))
        if request.method == "GET" and command == "query/active-app":
            return Response(200, active_app_answer(self.active_app))
        if request.method == "POST" and command == "launch/dev" and self.dev_app_installed:
            self.console_output = dev_app_prints(self.installed_archive)
            return recorded_response("ecp-launch-dev")
        return Response(404, "")  # live: launch/dev with no dev app is a 404, empty body

    # -- the installer (port 80) -----------------------------------------------

    def _digest_refusal(self, request: Request) -> Response | None:
        """The device's 401 challenge, unless the request has a valid Digest for its Dev Password."""
        header = request.headers.get("authorization", "")
        fields = _digest_fields(header)
        if header.startswith("Digest ") and fields.get("nonce") in self._nonces:
            ha1 = _md5(f"{fields.get('username')}:{DIGEST_REALM}:{self.dev_password}")
            ha2 = _md5(f"{request.method}:{fields.get('uri')}")
            parts = [fields.get(k) for k in ("nonce", "nc", "cnonce", "qop")]
            if fields.get("username") == "rokudev" and fields.get("response") == _md5(
                ":".join([ha1, *map(str, parts), ha2])
            ):
                return None
        nonce = secrets.token_hex(8)
        self._nonces.add(nonce)
        challenge = re.sub(r'nonce="[^"]*"', f'nonce="{nonce}"', DIGEST_CHALLENGE)
        return Response(401, "", {"www-authenticate": challenge})

    def _form(self, request: Request) -> dict[str, tuple[str | None, bytes]]:
        """A multipart form's fields; empty unless the Content-Type names its boundary."""
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("multipart/form-data") or "boundary=" not in content_type:
            return {}
        message = email.message_from_bytes(
            f"Content-Type: {content_type}\r\n\r\n".encode() + request.body,
            policy=email.policy.HTTP,
        )
        form = {
            part.get_param("name", header="content-disposition"): (
                part.get_filename(),
                part.get_payload(decode=True) or b"",
            )
            for part in message.iter_parts()
        }
        self.forms.append(form)
        return form

    def _installer_refusal(self, request: Request, match: re.Match) -> Response | None:
        if self.run_for(match[1]) is None:
            return Response(404, {"detail": "Not Found"})
        return self._digest_refusal(request)

    def _install(self, request: Request, match: re.Match) -> Response:
        if refusal := self._installer_refusal(request, match):
            return refusal
        form = self._form(request)
        if form.get("mysubmit", (None, b""))[1] != b"Install" or "archive" not in form:
            return recorded_response("install-form-error")
        archive = form["archive"][1]
        if self.next_install_fails:
            self.next_install_fails = False
            # Inferred from the recorded page's "packages": [], not seen by launching.
            self.installed_archive, self.dev_app_installed = None, False
            return recorded_response("install-failed")
        if archive == self.installed_archive:
            return recorded_response("install-identical")
        self.installed_archive = archive
        self.dev_app_installed = True
        return recorded_response("install-installed")

    def _inspect(self, request: Request, match: re.Match) -> Response:
        if refusal := self._installer_refusal(request, match):
            return refusal
        if self._form(request).get("mysubmit", (None, b""))[1] != b"Screenshot":
            return Response(200, inspect_page([("error", "Failure: Form Error")]))
        if 'id="dev"' not in self.active_app:
            return Response(200, inspect_page(SCREENSHOT_NOT_OK))
        return Response(200, recorded("installer-inspect-screenshot"))

    def _screenshot(self, request: Request, match: re.Match) -> Response:
        if refusal := self._installer_refusal(request, match):
            return refusal
        return Response(200, SCREENSHOT_JPEG)

    def _open_bridge(self, request: Request, match: re.Match) -> Response:
        if self.run_for(match[1]) is None:
            return Response(404, {"detail": "Not Found"})
        if request.headers.get("upgrade", "").lower() != "websocket":
            return Response(400, {"detail": "Use a WebSocket connection instead of HTTP GET."})
        if not self.dev_mode:
            return UPSTREAM_ERROR
        return Response(101, (match[1], int(match[2])))  # the handler upgrades

    def serve_bridge(self, sock: socket.socket, uuid: str, port: int) -> None:
        """Relay one WebSocket client of a port's bridge until it or the Run ends."""
        bridge = self.bridge(port)
        with self._lock:
            bridge.connections += 1
        with self._lock:
            frames = bridge.frames + (self.console_output if port == CONSOLE_PORT else [])
        for frame in frames:
            _send_frame(sock, 0x2, frame)
        while True:
            if not select.select([sock], [], [], 0.05)[0]:
                with self._lock:
                    self._advance_lifecycle()
                    ended = self.run_for(uuid) is None
                if ended:
                    return _send_frame(sock, 0x8, struct.pack("!H", 1001))
                continue
            opcode, payload = _read_frame(sock)
            if opcode == 0x8 or opcode is None:  # close, or the client hung up
                return _send_frame(sock, 0x8, payload[:2] if opcode else b"")
            if opcode == 0x1:  # text: RCE's bridge takes binary only
                return _send_frame(sock, 0x8, struct.pack("!H", 1003))
            if opcode == 0x9:
                _send_frame(sock, 0xA, payload)
            elif opcode in (0x0, 0x2):
                with self._lock:
                    bridge.received += payload
                if bridge.echo:
                    _send_frame(sock, 0x2, payload)


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()


def _send_frame(sock: socket.socket, opcode: int, payload: bytes) -> None:
    """One unmasked, final frame from server to client."""
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", 0x80 | opcode, length)
    elif length < 1 << 16:
        header = struct.pack("!BBH", 0x80 | opcode, 126, length)
    else:
        header = struct.pack("!BBQ", 0x80 | opcode, 127, length)
    try:
        sock.sendall(header + payload)
    except OSError:
        pass  # the client is gone


def _recv_exactly(sock: socket.socket, size: int) -> bytes | None:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def _read_frame(sock: socket.socket) -> tuple[int | None, bytes]:
    """One masked frame from the client: (opcode, payload); (None, b"") once it hangs up."""
    try:
        head = _recv_exactly(sock, 2)
        if head is None:
            return None, b""
        opcode, length = head[0] & 0x0F, head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recv_exactly(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recv_exactly(sock, 8))[0]
        mask = _recv_exactly(sock, 4) if head[1] & 0x80 else b"\0\0\0\0"
        payload = _recv_exactly(sock, length) if length else b""
    except (OSError, TypeError):
        return None, b""
    return opcode, bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def _handler_for(fake: FakeRCE) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            url = urlsplit(self.path)
            length = int(self.headers.get("content-length") or 0)
            # A proxy request names its target: host:port to CONNECT, or a full URL.
            proxied = self.command == "CONNECT" or "://" in self.path
            request = Request(
                method=self.command,
                path=self.path if proxied else url.path,
                query=parse_qs(url.query),
                headers={k.lower(): v for k, v in self.headers.items()},
                body=self.rfile.read(length),
            )
            response = fake.proxy(request) if proxied else fake.handle(request)
            if response.status == NO_ANSWER.status:
                time.sleep(response.delay)
                self.close_connection = True
                return
            if "sec-websocket-key" in request.headers:
                self.protocol_version = "HTTP/1.1"  # WebSocket clients require it
                self.close_connection = True
            if response.status == 101:
                return self._upgrade(*response.body)
            body, content_type = response.encode()
            time.sleep(response.delay)
            self.send_response(response.status)
            self.send_header("content-length", str(len(body)))
            for name, value in ({"content-type": content_type} | response.headers).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _upgrade(self, uuid: str, port: int) -> None:
            self.send_response(101)
            self.send_header("upgrade", "websocket")
            self.send_header("connection", "Upgrade")
            self.send_header("sec-websocket-accept", _accept_key(self.headers["sec-websocket-key"]))
            self.end_headers()
            self.wfile.flush()
            fake.serve_bridge(self.connection, uuid, port)

        do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = do_CONNECT = _serve

        def log_message(self, *args) -> None:
            pass

    return Handler
