# The public repo starts from fresh history; `.scratch/` stays local

The private repo's history holds copies of RCE's OpenAPI specs, live-run notes and the local issue tracker under `.scratch/`, some of which may be non-public under RCE's EULA (§16.10). So the public `rce-cli` repo starts from one squashed commit without `.scratch/`, and becomes the only working repo from then on, with `.scratch/` gitignored so specs and tickets stay on the maintainer's machine. Outside reports go to GitHub Issues.

## Considered Options

- **Push the existing history after an audit**: rejected because one missed file in any of the 24 commits that touch `.scratch/` is public for good.
- **Rewrite history to strip `.scratch/`**: rejected because it keeps every other commit, recorded fixtures included, so it still needs the full audit and gains little over a fresh start.
- **Keep a private repo with `.scratch/` and sync it to a public mirror**: rejected because it is a sync job forever; a gitignored folder gives the same privacy.
