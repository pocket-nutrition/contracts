# AGENTS.md

## What this repo is

The single pinnable coordinate shared by `pocket-nutrition/android`, `pocket-nutrition/ios` and
`pocket-nutrition/sandbox`: API schema, design tokens, FR copy deck, shared test vectors.

It has **no build and no runtime code** — committed JSON plus two Python scripts. Keep it that way.

## Key constraints

- **MPL-2.0 — the client tier.** This repo is vendored into the app binaries, so it carries the
  same licence as `android` and `ios`. The backend repos (`api`, `ml`,
  `ingest`, `community`, `data`, `knowledge`, …) remain AGPL-3.0-or-later. Copying *from* this repo into a
  backend repo is fine (MPL-2.0 combines into AGPL work); copying *from* an AGPL backend repo into
  this one is **not** — it would put AGPL code in a shipped binary and re-break App Store
  distribution. Use `SPDX-License-Identifier: MPL-2.0` (Exhibit A). **Never Exhibit B.**
- `openapi/openapi.upstream.json` is a **verbatim snapshot**. Never hand-edit it. Refresh it by
  copying `pocket-nutrition/api/contract/openapi.json`, then re-run `scripts/patch_spec.py`.
- `openapi/openapi.patched.json` is **generated and committed**. Never hand-edit it. Change
  `overlay.yaml` and regenerate.
- `vectors/*.json` are **generated and committed** too, from
  `pocket-nutrition/sandbox/src/lib/__vectors__/`. Never hand-edit them: the sandbox compares them
  byte-for-byte and `npm test` there will fail. Edit the `.cases.ts` table, run
  `npm run vectors:build`, then commit the result here. Every case needs a `why` of at least 40
  characters — CI enforces it, because that string is the only explanation a Kotlin or Swift porter
  ever sees.
- `tokens/generated/*` are **generated and committed**. Never hand-edit: run
  `python3 scripts/emit_tokens.py`. `tokens/tokens.json` is a **verbatim mirror** of
  `pocket-nutrition/design/foundations/pocket-nutrition.css` — a value that is not in that
  stylesheet does not belong there, with two documented exceptions that say so in their own
  `$description` (`color.chart.*`, transcribed from the sandbox, and `cooking-palette.json`, derived).
- `strings/fr.json` is extracted **verbatim** from the sandbox, defects included. When you find a
  copy inconsistency, record it in `$extensions` and leave the value alone — normalising copy is the
  design owner's decision, and a silent fix here would desync this file from the running app.
- Every `overlay.yaml` entry needs a `WHY:` comment. The overlay doubles as a bug report against the
  API — when an upstream fix lands, delete the section rather than letting it rot.
- `patch_spec.py` output must stay **byte-reproducible**: no timestamps, no environment-dependent
  values. `--check` compares bytes, and a clock would make CI fail spuriously.
- `required` is **derived** from springdoc's nullability encoding, not hand-listed. Before adding a
  schema to `requiredOverrides`, check whether the rule in `is_nullable()` should be extended
  instead — an override is a permanent maintenance burden in a file nobody will re-read.

## The two generators disagree, and one fails silently

`swift-openapi-generator` does not understand `oneOf: [{$ref}, {type: null}]`. It emits a warning
and then **omits the property entirely**, with a successful build. `openapi-generator` (Kotlin)
handles it correctly. This silently removed `IngredientSuggestionWithNutrition.nutrition` — the
whole nutritional payload of an enriched search result — from the iOS model.

Consequences for anyone working here:

- `scripts/patch_spec.py::normalize_nullable_refs` exists for this. Do not "simplify" it away.
- `scripts/check_codegen_parity.py` compares **generated output**, not the spec, because the spec
  was right and the generator was wrong. Do not weaken it to compare counts only: it also checks
  wire names and that spec-required fields are non-optional.
- If a parity check fails, **fix the spec encoding so both generators agree.** Do not work around it
  in app code and do not add a platform-specific special case — that recreates the divergence this
  repo exists to prevent.

## Allowed without approval

- Adding vectors, tokens, or strings.
- Refreshing the upstream snapshot and regenerating the patched spec.
- Adding a `WHY:`-documented entry to `overlay.yaml`.
- Bumping `VERSION` for an additive change (minor).

## Requires approval

- **Any change to `required` derivation semantics.** It decides optionality in two shipped binaries
  that cannot be updated in lockstep with the server.
- **A major `VERSION` bump**, i.e. any breaking change. Shipped apps pin a tag; this needs a written
  migration plan first.
- **Changing or removing an existing vector's `expected` value.** That is a behavioural change to
  both apps, not a test fix. Renaming a vector `id` is also breaking — consumers assert on the id
  set to prove no case was skipped.
- Adding a dependency. The current set is PyYAML; anything else needs justifying against "this repo
  has no build".
- Relaxing `check_codegen_parity.py` or `patch_spec.py --check`.

## Do not copy code from GPL-licensed reference implementations

If you consult a GPL-3.0 project implementing a similar feature set for inspiration, treat it as a
**behavioural specification only**.

Permitted: reading it, describing what it does in prose, and taking published scientific facts
(BMR/TDEE equations) and public-database nutrient lists.

Forbidden: copying or translating its source, strings, assets, or verbatim schemas. Translating its
code to another language is a derivative work.

This restriction survives the move to MPL-2.0, and matters more under it. You cannot relicense
GPL-3.0 code as MPL-2.0, so copied code would force the surrounding work to GPL-3.0 — leaving the
repo carrying two incompatible copyleft licences at once *and* re-imposing the GPL-3.0 §10 terms
that make App Store distribution non-viable. The rule is unchanged — read it, do not copy it.
