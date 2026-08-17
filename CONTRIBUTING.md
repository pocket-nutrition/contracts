# Contributing

This repository has no build and no runtime code — it is committed JSON plus two small Python
scripts. See [README.md](README.md) for what it contains and why, and [AGENTS.md](AGENTS.md) for
the constraints an automated agent (or a human moving fast) must not break.

## Setup

The only dependency is [PyYAML](https://pyyaml.org/), used by `scripts/patch_spec.py` to read
`overlay.yaml`. There is no `requirements.txt` — install it once, globally or in a venv:

```bash
pip install pyyaml
```

`scripts/emit_tokens.py` and `scripts/check_codegen_parity.py` use only the standard library.

## What each directory is

| Directory | Contents | Source of truth |
|---|---|---|
| `openapi/` | `openapi.upstream.json` (verbatim API snapshot), `overlay.yaml` (the patch, with a `WHY:` per entry), `openapi.patched.json` (generated — the only file clients consume) | `pocket-nutrition/api/contract/openapi.json` |
| `vectors/` | Shared behavioural test corpus — 144 cases across 17 suites | `pocket-nutrition/sandbox/src/lib/__vectors__/` |
| `tokens/` | Design tokens (`tokens.json`), UI-role mapping (`semantic-map.json`), the derived `cooking-palette.json`, and generated `generated/Tokens.{kt,swift}` | `pocket-nutrition/design/foundations/pocket-nutrition.css` |
| `strings/` | `fr.json`, the FR copy deck, tagged by `scope` (`shared` / `sandbox` / `app`) | `pocket-nutrition/sandbox` |

None of these four are edited directly except `overlay.yaml`. The others are refreshed from their
upstream and regenerated here — see below.

## Running the validation scripts

Both scripts are byte-reproducible (no timestamps, no environment-dependent output), which is what
makes `--check` trustworthy in CI.

```bash
# OpenAPI: upstream + overlay -> patched
python3 scripts/patch_spec.py            # regenerate openapi/openapi.patched.json
python3 scripts/patch_spec.py --check    # CI mode: exit 1 if the committed file is stale

# Design tokens: tokens.json + semantic-map.json -> native sources
python3 scripts/emit_tokens.py           # regenerate tokens/generated/
python3 scripts/emit_tokens.py --check   # CI mode: exit 1 if the committed files are stale
```

Run both `--check` invocations before opening a PR. If either fails, run the non-`--check` form and
commit the resulting diff — do not hand-edit the generated files.

`scripts/check_codegen_parity.py` needs generated Kotlin and Swift client output as input, so it
only runs meaningfully alongside `pocket-nutrition/android` and `pocket-nutrition/ios` (see
README.md, "Generating clients"). It is not part of the two `--check` commands above.

## Proposing a change to a shared contract

Backend and two mobile clients all vendor this repository at a pinned tag, so a change here is a
change to three codebases that cannot deploy in lockstep. `AGENTS.md` has the authoritative list —
read "Allowed without approval" and "Requires approval" there before starting. In short:

- **Additive and low-risk** (new vectors, new tokens/strings, a `WHY:`-documented `overlay.yaml`
  entry, refreshing the upstream snapshot, a minor `VERSION` bump): open a PR directly.
- **Anything that changes existing behaviour a client already relies on** — an existing vector's
  `expected` value, a vector `id`, `required`-derivation semantics, a new dependency, or a major
  `VERSION` bump — needs a written case for *why*, and should be discussed in an issue first. These
  changes need a migration plan because shipped apps pin a tag and cannot be updated in lockstep
  with the server.

For an OpenAPI change specifically: refresh `openapi/openapi.upstream.json`, add a `WHY:`-documented
entry to `overlay.yaml` rather than hand-editing the patched output, run `patch_spec.py`, and review
the diff before bumping `VERSION` (minor for additive, major for breaking — see README, "Running
locally"). For vectors, the source of truth is the sandbox's `.cases.ts` tables, not this repo —
edit there, run `npm run vectors:build`, then commit the result here (see `vectors/README.md`).

## Pull requests

1. Make the change in its actual source (sandbox for vectors, this repo's `overlay.yaml`/
   `tokens.json`/`strings/fr.json` for the rest).
2. Regenerate anything derived and run both `--check` commands above.
3. Keep the diff reviewable: one logical change per PR, and include the `WHY:` for anything touching
   `overlay.yaml`.
4. If the change is breaking (see "Requires approval" above), say so in the PR description and
   bump `VERSION`'s major component.

## Reporting an issue

Use the issue templates under `.github/ISSUE_TEMPLATE/`. Most issues here are either "a vector's
`expected` value no longer matches reality" or "the OpenAPI snapshot is stale against the deployed
API" — both templates ask for the specifics that make those actionable (which file, which suite/
case or endpoint, what a fresh snapshot would show).

## License

By contributing, you agree your contribution is licensed under MPL-2.0, the same license as the
rest of this repository — see [LICENSE](LICENSE) and the "Licence" section of README.md.
