---
name: Bug report
about: Something in the contract is wrong or stale — a vector's expected value, a stale OpenAPI snapshot, an incorrect token, or a copy defect
title: "[bug] "
labels: bug
assignees: ""
---

## What is affected

Check the one that applies (or describe if none fit):

- [ ] `vectors/` — an `expected` value no longer matches real client/sandbox behaviour
- [ ] `openapi/` — the patched spec is stale against the deployed API, or a generator disagrees with it
- [ ] `tokens/` — a generated token value does not match `pocket-nutrition/design`'s stylesheet
- [ ] `strings/fr.json` — wording is wrong, missing, or has the wrong `scope`
- [ ] Something else (describe below)

## Which file / suite / endpoint

E.g. `vectors/rounding.json`, case id `tie-half` — or `GET /ingredients/search` — or
`tokens/tokens.json`, path `color.surface.paper`.

## What you expected vs. what you observed

Be specific: paste the `expected` value from the vector file, or the field/response you saw from a
live API call, or the hex value in the stylesheet vs. the one in `tokens.json`.

## Steps to reproduce

```bash
# e.g.
python3 scripts/patch_spec.py --check
```

or the client-side steps that surfaced the mismatch (which app, which screen, which build).

## Environment

- Repo commit / `VERSION`:
- Consuming app and version (if applicable): iOS / Android / sandbox
- OS / toolchain (if relevant to codegen, e.g. openapi-generator or swift-openapi-generator version):

## Why this matters

If this is a shared contract, a fix here affects backend + iOS + Android at once. Note if you think
this is additive (safe) or a breaking change to an `expected` value or `id` (needs the approval path
in `AGENTS.md`).
