#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Verify the Kotlin and Swift clients generated from openapi.patched.json agree.

WHY THIS EXISTS
---------------
This check earned its place. Running it during the initial go/no-go caught a defect that no build
failure, warnings-as-errors setting, or code review would plausibly have caught:

  swift-openapi-generator 1.13.0 does not understand springdoc's nullability encoding for $ref
  properties, `oneOf: [{$ref: ...}, {type: null}]`. It logs

      warning: Schema "null" is not supported, reason: "schema type", skipping

  and then OMITS THE PROPERTY ENTIRELY from the generated struct. The build succeeds.
  openapi-generator (Kotlin) handles the same input correctly.

The casualty was `IngredientSuggestionWithNutrition.nutrition` — the entire nutritional payload of
an enriched search result. The iOS app would have compiled, run, and shown no nutrition on search
results, with nothing anywhere reporting a problem. Kotlin generated 17 properties, Swift 16.

scripts/patch_spec.py now normalizes that encoding to a bare $ref (optionality is carried by the
`required` array instead, which both generators honour). This script is the regression guard. It
compares the *generated output* rather than trusting the spec, precisely because the failure mode
was a generator silently disagreeing with the spec.

Two hand-written clients would have diverged the same way — just more slowly, and in more places.
That is the argument for generating them.

USAGE
-----
    python3 scripts/check_codegen_parity.py \
        --kotlin-models path/to/generated/models \
        --swift-types   path/to/GeneratedSources/Types.swift

Both inputs are generated artifacts, so this runs after codegen in contracts CI. It is
deliberately tolerant about *how* the clients are generated and strict about the result.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCHED = ROOT / "openapi" / "openapi.patched.json"


def _schemas() -> dict[str, dict]:
    doc = json.loads(PATCHED.read_text())
    return {
        name: schema
        for name, schema in doc.get("components", {}).get("schemas", {}).items()
        if "properties" in schema
    }


def kotlin_properties(models_dir: Path, schema: str) -> set[str] | None:
    """Collect wire names from @SerialName, not Kotlin identifiers.

    Comparing wire names is the point: a generator that silently renames a field is still wrong
    even when the property count matches.
    """
    path = models_dir / f"{schema}.kt"
    if not path.exists():
        return None
    return set(
        re.findall(
            r'@SerialName\(value = "([^"]+)"\)\s*\n\s*(?:@Contextual\s*)?val ',
            path.read_text(),
        )
    )


def swift_struct_body(source: str, schema: str) -> str | None:
    """Extract one struct body by brace matching.

    A fixed-size window spills into the following type and silently inflates the count — that
    mistake produced six phantom mismatches on the first run of this check.
    """
    match = re.search(rf"struct {schema}: Codable[^{{]*\{{", source)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    return None


def swift_properties(types_source: str, schema: str) -> set[str] | None:
    body = swift_struct_body(types_source, schema)
    if body is None:
        return None
    keys = re.search(r"enum CodingKeys: String, CodingKey \{(.*?)\}", body, re.S)
    if keys is None:
        return None
    return set(re.findall(r"case (\w+)", keys.group(1)))


def swift_optional_properties(types_source: str, schema: str) -> set[str]:
    body = swift_struct_body(types_source, schema) or ""
    return set(re.findall(r"public var (\w+): [^\n]*\?\s*$", body, re.M))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare generated Kotlin and Swift clients against the patched OpenAPI spec."
    )
    parser.add_argument("--kotlin-models", type=Path, required=True)
    parser.add_argument("--swift-types", type=Path, required=True)
    args = parser.parse_args()

    for path in (args.kotlin_models, args.swift_types):
        if not path.exists():
            print(f"FAIL: {path} does not exist — run codegen first")
            return 1

    types_source = args.swift_types.read_text()
    schemas = _schemas()
    failures: list[str] = []

    header = f"{'schema':<38}{'spec':>5}{'kt':>5}{'swift':>7}   status"
    print(header)
    print("-" * len(header))

    for schema, definition in sorted(schemas.items()):
        expected = set(definition["properties"])
        required = set(definition.get("required", []))

        kotlin = kotlin_properties(args.kotlin_models, schema)
        swift = swift_properties(types_source, schema)

        if kotlin is None:
            failures.append(f"{schema}: no Kotlin model generated")
            print(f"{schema:<38}{len(expected):>5}{'--':>5}{'?':>7}   MISSING (kotlin)")
            continue
        if swift is None:
            failures.append(f"{schema}: no Swift struct generated")
            print(f"{schema:<38}{len(expected):>5}{len(kotlin):>5}{'--':>7}   MISSING (swift)")
            continue

        problems: list[str] = []
        if expected - kotlin:
            problems.append(f"absent from Kotlin: {sorted(expected - kotlin)}")
        if expected - swift:
            problems.append(f"absent from Swift: {sorted(expected - swift)}")
        if kotlin - expected:
            problems.append(f"extra in Kotlin: {sorted(kotlin - expected)}")
        if swift - expected:
            problems.append(f"extra in Swift: {sorted(swift - expected)}")

        # A property the spec marks required must not be generated optional: that pushes a `?? 0`
        # default decision to every call site, independently, in two languages.
        wrongly_optional = swift_optional_properties(types_source, schema) & required
        if wrongly_optional:
            problems.append(f"required but optional in Swift: {sorted(wrongly_optional)}")

        print(
            f"{schema:<38}{len(expected):>5}{len(kotlin):>5}{len(swift):>7}   "
            f"{'OK' if not problems else '*** MISMATCH ***'}"
        )
        for problem in problems:
            print(f"      {problem}")
            failures.append(f"{schema}: {problem}")

    print()
    if failures:
        print(f"FAIL: {len(failures)} parity problem(s).")
        print(
            "A generator is disagreeing with the patched spec. Do not work around it in app code —\n"
            "fix the encoding in scripts/patch_spec.py so BOTH generators agree, then re-run.\n"
            "See this file's docstring for the oneOf-with-null precedent."
        )
        return 1

    print(f"OK: {len(schemas)} schemas agree across the spec, Kotlin and Swift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
