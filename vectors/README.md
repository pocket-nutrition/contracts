# Behavioural test vectors

144 cases across 17 suites — `index.json` is the authority; this line is prose and can go stale.
Generated from the sandbox's reference implementation; consumed by `pocket-nutrition/android` and
`pocket-nutrition/ios`.

**Generated files — never hand-edit.** They are produced by `pocket-nutrition/sandbox`:

```bash
cd ../sandbox
npm run vectors:build     # rewrites this directory
npm test                  # fails if this directory is stale
```

Start with `index.json`: it lists every suite, its case count, and its description.

## Why this exists

The OpenAPI contract makes the three clients agree on *wire format*. Nothing makes them agree on
*behaviour* — and behaviour is where divergence is invisible. Two independent reimplementations of
"round this portion ratio to one decimal" will not disagree at compile time, will not disagree in any
test either team writes, and will show the user two different numbers.

So the rules are stated once, as data, and all three clients assert against the same file.

## File shape

```jsonc
{
  "suite": "rounding",                 // kebab-case; matches the filename
  "description": "…",                  // what the suite covers, plus porting notes
  "generatedBy": "…",
  "cases": [
    {
      "id": "tie-half",                // stable; renaming one is a breaking change
      "why": "The defining case: …",    // why it exists, for a reader who cannot see the TypeScript
      "input":    { "value": 0.5 },
      "expected": 1
    }
  ]
}
```

There is deliberately **no timestamp and no version field**: the files must be byte-reproducible so
the freshness check can compare bytes without flaking. The corpus version is this repository's git
tag.

`input` is always self-contained — no case requires calling another function to reconstruct its
arguments, so a Kotlin or Swift test can decode it and go.

## How to consume it

Decode each file, loop the cases, feed `input` to your implementation, compare against `expected`.

**Assert on the id set as well.** Iterating only the cases you happen to have implemented makes a
skipped case indistinguishable from a passing one:

```kotlin
val suite = json.decodeFromString<VectorSuite>(read("rounding.json"))
assertEquals(
    setOf("tie-half", "tie-one-and-a-half", /* … */),
    suite.cases.map { it.id }.toSet(),
)
```

Compare on canonical JSON — object keys sorted, an absent key treated as absent rather than null.
That is how the sandbox compares, and it avoids false failures from key ordering.

## Porting rules the corpus enforces

### Rounding — read this first

Everything numeric depends on it. The rule is **`roundHalfUp(x) = floor(x + 0.5)`**: a tie goes to
the larger value.

| language | naive call | 12.5 → | agrees? |
|---|---|---|---|
| JS/TS | `Math.round(12.5)` | 13 | yes |
| Java | `Math.round(12.5)` | 13 | yes |
| Swift | `(12.5).rounded()` | 13 | yes |
| Kotlin | `kotlin.math.round(12.5)` | **12** | **no** |

`kotlin.math.round` breaks ties **towards even**, so the obvious Kotlin port of `Math.round` is
wrong. Use `floor(x + 0.5)`.

This is not a theoretical concern. `describe-quantity/between-anchors-portion-descriptor` feeds 80 g
against a 64 g portion: `80 / 64 = 1.25` exactly, so the label comes from `round(12.5) / 10`.
Half-up prints **"≈ 1,3 portion"**; ties-to-even prints **"≈ 1,2 portion"**. No exception, no
warning, just a different number on screen.

Rounding happens **once, at the end** of a calculation chain, never on intermediate values — see
`apply-method-change/method-swap-round-trips-through-the-raw-equivalent`, where a weight is converted
twice and only the final result is rounded.

### Number formatting

`french-number` is **not** a locale formatter. It is "stringify, then replace `.` with `,`". Platform
formatters add thousands separators, drop leading zeros, and change behaviour between OS versions. Do
not use `NumberFormat`, `String(format:)` or `DecimalFormat` here.

### Weight semantics

The highest-risk area, covered by `build-meal-ingredient` and `apply-method-change`.

- `measuredState` records **whether `quantity` is a raw or a cooked weight**. It is not decoration:
  get it wrong and every nutrition number is off by the yield factor.
- A recipe's component weight is always a **pre-cooking** weight, so a recipe override yields
  `measuredState: "raw"` even when `cookingMethod` is `"boiled"`.
- The yield factor is applied only when a cooked weight is wanted from a raw base.
- `quantity` and `basePortionG` are resolved by **different rules** and legitimately disagree — see
  `millilitre-food-without-serving-g-uses-the-unit-volume` (246 versus 200).

### Never invent food data

`yield-factor` pins it: a missing yield resolves to **1**, meaning no conversion. Not an estimate,
not an average. A gap belongs in `pocket-nutrition/knowledge`, reported through the feedback channel
— never guessed in a client.

The same applies to the two label tables: they classify a label and carry no nutritional values.
`base-portion-g/celeri-alone-falls-through` and `patate-falls-through` exist to record that an
unmatched food takes the generic 100 g rather than acquiring a made-up weight.

### Regex word boundaries

`cooking-method-default` and `base-portion-g` encode a class of bug worth knowing before porting:
**JavaScript's `\b` is ASCII-only**. In `"épinards"` there is no word boundary before `é`, because
`é` is not a `\w` character — so `/\bépinard/` could never match, at any position, and spinach was
silently classified raw at 100 g instead of steamed at 60 g.

Five patterns were dead for this and related reasons, all now fixed and pinned by vectors whose `why`
begins with `REGRESSION`:

| was | problem | now |
|---|---|---|
| `\bépinard` | ASCII `\b` cannot precede `é` | explicit accent-aware lookbehind |
| `\bbroccoli` | English spelling only; French is "brocoli" | `brocc?oli` |
| `\bchoux\b` | plural only; misses "chou", "chou-fleur" | `\bchoux?\b` |
| `\bmuseli` | not a spelling of the word | `\bmuesli` |
| `\bravet` | not a French food | `\brave` (céleri-rave, chou-rave) |

Kotlin and Swift both use ICU regex, where `\b` **is** Unicode-aware — so a literal port of the
*fixed* patterns is correct, while a port of the *original* ones would have accidentally worked and
disagreed with the web app. The vectors are what make the three agree either way.

One oddity is preserved on purpose rather than fixed:
`base-portion-g/pomme-de-terre-matches-the-fruit-row` — `\bpomme\b` matches "pomme de terre", so a
potato takes the 120 g fruit weight. Changing it would mean choosing a potato portion weight, which
is Knowledge's job, and the server's `servingG` overrides the whole table anyway. It is pinned so a
future reordering cannot change it silently.

### Row order is part of the contract

Both label tables are **ordered** and the first match wins, so a port using an unordered map will
disagree. Guarded by `pomme-de-terre-before-pomme`, `fromage-blanc-before-fromage` and
`pois-is-not-poisson`.

## What is out of scope

- **`id` generation.** `build-meal-ingredient` excludes the generated `id`, which embeds a timestamp.
  Each app mints its own identifiers.
- **Display formatting inside components.** The sandbox rounds in roughly twenty more places in its
  React components; those are per-platform view code, rewritten rather than ported. The rounding rule
  above still applies to them.
- **Anything requiring a network call.** Every case is pure.

## Changing the corpus

- **Adding** a suite or a case: free, no approval needed.
- **Changing an existing `expected` value, or renaming an `id`:** a behavioural change to two shipped
  apps, not a test fix. See `AGENTS.md` — it needs approval.
