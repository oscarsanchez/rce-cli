# Coding standards

Read during review. Mechanical rules are enforced by the check command (see README), not restated here. These are the judgement calls.

## Money and permanence

- Every code path that starts a Run has a stop on its failure and interrupt paths, unless the user explicitly asked to keep it running.
  A script that starts a Run through the `rce` CLI starts it inside that stop path, and on interrupt waits for the `rce` child to exit (`subprocess.run` kills it 0.25 s after Ctrl-C, mid-way through its own stop).
  The Pool's exception (ADR-0002): a Pool try whose start got a 503, 502, 504 or no answer, or a Ctrl-C during that request, sends no stop, because a Run found there may be another job's Claim. `--max-runtime` bounds the cost.
- A command that spends quota for good (create) or changes saved device state (retire, setup-dev, Snapshot changes) asks first. Only an explicit flag skips the prompt, and a missing TTY means "no", not "yes".
- Cost shown to the user comes from RCE's timestamps and one rate constant (`USD_PER_MINUTE`), never a rate copied into code elsewhere.
  RCE has no rate endpoint, so that constant is the source of truth. Docs written for people (README, skill) may quote $0.20/h; update them with the constant.

## Secrets

- The token, Dev Passwords and WebRTC credentials appear in no output, including `--json`, errors and debug logs. Prefer a test that proves it over a reviewer's eye.
  Two exceptions, both only when the user asks for it: `setup-dev --show-password` and `device show --dev-password` print the stored Dev Password once, on stderr. Never in stdout or `--json`.
- Trust decisions read state `rce` owns (its config, the Core API's answer), never something a device or proxy response could forge.

## One source of truth

- The Run's address always comes from the Core API's response for that Run.
- Device Names, Dev Passwords and Dev Snapshot ids live only in the per-user config. The token lives only in rk's file or the environment.
  `RCE_DEV_PASSWORD` overrides the stored Dev Password (for pipelines). It is read only from the environment, never a flag.
  `RCE_POOL`, a CI variable from each Pool member's RCE id to its Dev Snapshot id, is the other exception: a runner has no per-user config (ADR-0002).
- Exit codes and `--json` shapes are a public contract: change them deliberately, with the README and skill updated in the same change.

## Tests

- Tests run `rce` as a subprocess against the fake RCE and assert on stdout, exit codes, files and the requests the fake received (Seam A). They never import `rce` internals.
- The fake builds its answers from the recorded RCE answers in `tests/fixtures/recorded/`, and sets only the ids, names, states, timestamps and identity a test relies on. A shape it still invents is listed, with the reason, in that folder's README.

## Vocabulary

- Use the terms in `GLOSSARY.md` in code, output and docs: Cloud Device, Device Name, Run, Snapshot, Dev Snapshot, Dev Password, Retired Cloud Device.
