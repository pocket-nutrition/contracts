---
name: Feature request
about: Propose a new vector, token, string, or OpenAPI overlay entry
title: "[feature] "
labels: enhancement
assignees: ""
---

## What needs to be added

Check the one that applies (or describe if none fit):

- [ ] A new behavioural vector / suite (`vectors/`)
- [ ] A new design token or semantic role (`tokens/`)
- [ ] A new French string, or a new `scope` value (`strings/fr.json`)
- [ ] A new `overlay.yaml` entry (missing header, hidden endpoint, extensible enum, etc.)
- [ ] Something else (describe below)

## Why is this needed

What is the invariant or behaviour this pins, or what gap does it close? If this mirrors an
upstream source (sandbox, design stylesheet, live API), name it.

## Proposed content

Sketch the actual data if you can — a vector's `input`/`expected`/`why`, a token path and value, a
string key and its `scope`, or the `overlay.yaml` block with its `WHY:` comment.

## Is this additive or breaking

- [ ] Additive — a new case/token/string/entry that does not change existing behaviour. No approval
      needed per `AGENTS.md`.
- [ ] Breaking — changes an existing vector's `expected` value, renames a vector `id`, or otherwise
      changes behaviour two shipped apps already rely on. This needs a written migration plan and
      approval — see `AGENTS.md`, "Requires approval".

## Consumers affected

Which of backend (`api`), `pocket-nutrition/ios`, `pocket-nutrition/android`, and
`pocket-nutrition/sandbox` need to change to pick this up.
