# Recorded RCE answers

Real RCE answers, redacted, that `tests/fake_rce.py` builds its answers from. The fake sets the ids, names, states, timestamps and identity each test relies on; the recordings give everything else (the fields, their types and formats, the page and XML templates).

Each file is `{"request", "status", "headers", "body"}`, written by `scripts/record-live` (with the hand edits noted below). The token, Dev Password, WebRTC credentials, serial numbers, emails, people's and the organisation's names, the account's id, `creator_id`, `idp_id` and the device's network identifiers read `REDACTED`. The Run's `instance_uuid` reads `00000000-0000-4000-8000-000000000000` wherever it appears, and the organisation's id reads `1`. Each installer page is trimmed to the lines `rce` and the fake read (its hidden status lines, its messages and its screenshot link): the rest of Roku's HTML and JavaScript, copyright comment included, is not kept. Cloud Device, Snapshot, firmware and Run ids are kept: they mean nothing outside the organisation. `tests/test_recorded_fixtures.py` fails on any secret it can spot by pattern or field, on any other UUID, on another organisation id and on Roku's copyright notice.

## Re-record

```sh
scripts/record-live <device>          # free Core API reads only
scripts/record-live <device> --run    # plus one Run (1 to 2 device-minutes); read docs/agents/live-rce.md first
```

`<device>` is the Device Name to record from: agents use the agents' Cloud Device, per `docs/agents/live-rce.md`.

Then run `scripts/check`. A test that fails after a re-record is either a fake that read a field it should set itself, or a live change that `rce` needs to handle.

## What is recorded

Recorded 2026-11-17 by `scripts/record-live player --run` from `player` (351), Roku OS 16.0.4 build 853: the Core API reads just before Run 4300, the rest during it. The Run started from its Dev Snapshot (dev mode on, ECP permissive, Home screen in the foreground). Trimmed and given their placeholders on 2026-11-18 by `scripts/record-live`'s own code, without a re-record.

| File | Answer |
|---|---|
| `user-me`, `devices`, `device`, `snapshots`, `snapshot`, `firmware-versions`, `trial-status`, `usage-user` | Core API reads, with no Run |
| `device-running` | `GET /devices/{id}` while the Run is running |
| `input-ready` | Instance API `input/ready` |
| `ecp-device-info`, `ecp-active-app` | ECP through the port proxy |
| `installer-wrong-password` | the installer's 401 Digest challenge to a wrong Dev Password |
| `installer-inspect` | the Utilities page after Screenshot with no dev app in the foreground (`Screenshot not ok`) |
| `install-installed`, `install-identical` | the Install page (`plugin_install`) after installing a tiny test app (`rce`'s `selftest_app`), then the same bytes again. Messages in a `JSON.parse('{"messages": [...]}')` call, which `rce` reads |
| `install-failed` | a failed install: **400**, the Install page with the reason as an `error` message. For an app whose BrightScript does not compile (its `Main` has no `end sub`), Roku OS 16.0.4 says `Install Failure: Unzip failed. Invalid or corrupt zip archive.  Unloading.`, though the zip is valid: Run 4291 sent it stored, Run 4300 deflated, and both got this page. No separate compile-failure message was seen. The fake serves this page as is for the next install after a test sets `next_install_fails` |
| `install-form-error` | the Install form posted without an archive: 200, `Install Failure: Application File is Empty.` |
| `ecp-launch-dev` | ECP `launch/dev` with the test app installed: **200**, empty (Run 4300; Run 4291 answered **204**). `rce` accepts any 2xx |
| `installer-inspect-screenshot` | the Utilities page after Screenshot with the test app in the foreground: `Screenshot ok`, and the screenshot's `<img src="pkgs/dev.jpg?time=...">` |

The start's 202 isn't recorded either (`record-live` starts through `rce device start`), but it isn't invented: the fake follows the shape seen live on Run 4615 (`auto`, 2026-11-19). The Cloud Device is `pending` with `running_device: null`, and the Run (still with no `instance_api_url`) shows on a later read. The fake builds that Run from `device-running`.

## What the fake still invents

| Shape | Why it is not recorded |
|---|---|
| `POST /devices/{id}/stop` 202 body | `record-live` stops through `rce device stop`, so it never sees it. The fake answers with the Cloud Device as it is. |
| `POST /devices` 201 (create), `PATCH /devices/{id}` | Create spends device quota for good; PATCH renames the Cloud Device. |
| `POST /devices/{id}/snapshots` 201, a Snapshot not yet ready | Takes a Snapshot, which counts against the Snapshot quota. |
| Error bodies: 429 `trial_device_run_limit`, 402 `trial_exhausted`, 409 `snapshot_not_ready`, 409 already running, 400 over the cap, 400 `trial_max_runtime_exceeded`, 422 Snapshot limit, gateway 429 `local_rate_limited`; a test's 409 to stopping a Cloud Device with no Run; a gateway error (502, 503, 504) to a start, with or without a Run made | Each needs a second Run, a used-up trial, 25 Snapshots or a start request that might succeed. Codes are from the Core API spec; the messages of the 409, 400, 422 and the gateway errors are guesses. What RCE answers a stop with no Run is untried, and a gateway error to a start hasn't been seen live. |
| 403 `{"detail": ""}` for a Cloud Device that isn't yours, and to a start from a Snapshot RCE doesn't have (`delete_snapshot`); 404s for a Snapshot or an ended Run | Both empty 403s were seen live (rce-cli research; a start from Snapshot id 1 on 2026-11-19, which made no Run), not recorded; the 404 bodies are FastAPI's defaults. A start from a Snapshot RCE deleted, rather than one that never existed, is untried. |
| `input/keypress` answer and its 503, `xi/developer-settings-combo` | Pressing keys changes what the device shows. The keypress body is the Instance API spec's example. |
| ECP Limited-mode 403 (`ECP command not allowed in Limited mode.`), `launch/dev`'s empty 404 with no dev app | Seen live (rce-cli ticket 06), but `player` is set up now: recording them means changing "Control by mobile apps" or removing the dev app. |
| ECP's empty 404 for a command the device doesn't know | Not tried; the fake answers it like `launch/dev` with no dev app. |
| ECP in Disabled mode | Never seen; needs the setting changed. The fake answers it like Limited mode. |
| `<in-guided-setup>true</in-guided-setup>` in device-info | Only before setup (seen live, ticket 06); the recording is from after it, where the element is absent. |
| A failed install removes the dev app (`launch/dev` then 404s) | Inferred from `"packages": []` on `install-failed` and `install-form-error` recorded after an installed app (Run 4291), not seen by launching after a failure. So `record-live` now records both failures before the install it launches (Run 4300). |
| The Utilities page's Form Error (`Failure: Form Error`) | Needs a malformed form; the fake renders it into `installer-inspect` like `Screenshot not ok`. |
| The screenshot JPEG | A picture of the screen; the fake's bytes only need to round-trip. |
| WebSocket bridges (console 8085, forwarded ports), their close codes, the 503 `upstream connect error` | `record-live` records HTTP only. Close code 1003 and the 503 text are from the Instance API spec and the rce-cli live checks. |
| `usage-user` buckets | Tests set them; the recording gives the envelope. |
