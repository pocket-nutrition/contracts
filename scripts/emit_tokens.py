#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Generate Tokens.kt and Tokens.swift from tokens.json + semantic-map.json.

WHY GENERATE RATHER THAN HAND-PORT
----------------------------------
There is nothing clever about a colour constant, which is exactly the problem: a hand-copied
`#3e7a4e` is indistinguishable from a correct one until someone puts the two apps side by side.
Generating them means the design stylesheet, Android and iOS cannot disagree, and a token rename
becomes a compile error in both apps instead of a silent visual drift.

It also validates `semantic-map.json`: every {"token": "dotted.path"} reference must resolve
against tokens.json, so a typo fails here rather than producing a transparent button in one app.

    python3 scripts/emit_tokens.py            # write tokens/generated/
    python3 scripts/emit_tokens.py --check    # exit 1 if the committed output is stale (CI)

Output is byte-reproducible — no timestamps, no environment-dependent values — which is what makes
--check trustworthy. Same contract as scripts/patch_spec.py.

Standard library only, keeping this repo's PyYAML-and-nothing-else dependency promise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "tokens" / "tokens.json"
SEMANTIC = ROOT / "tokens" / "semantic-map.json"
COOKING = ROOT / "tokens" / "cooking-palette.json"
OUT_DIR = ROOT / "tokens" / "generated"
KOTLIN_OUT = OUT_DIR / "Tokens.kt"
SWIFT_OUT = OUT_DIR / "Tokens.swift"

HEADER_NOTE = (
    "GENERATED FILE — DO NOT EDIT.\n"
    " * Source: pocket-nutrition-contracts/tokens/{tokens,semantic-map,cooking-palette}.json\n"
    " * Regenerate: python3 scripts/emit_tokens.py\n"
    " *\n"
    " * Editing this by hand guarantees the two apps drift apart, which is the single thing the\n"
    " * contracts repository exists to prevent. Change the JSON and re-run."
)


# ── Token tree access ───────────────────────────────────────────────────────


def is_token(node: Any) -> bool:
    """A DTCG token is any mapping carrying $value. Everything else is a group."""
    return isinstance(node, dict) and "$value" in node


def resolve(tree: dict[str, Any], path: str) -> dict[str, Any]:
    node: Any = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise SystemExit(
                f"semantic-map.json references '{path}', which does not exist in tokens.json "
                f"(failed at '{part}'). Fix the path or add the token."
            )
        node = node[part]
    if not is_token(node):
        raise SystemExit(
            f"semantic-map.json references '{path}', which is a group rather than a token. "
            f"Point at a leaf that has a $value."
        )
    return node


def walk_tokens(node: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], dict]]:
    """Depth-first list of (path, token) pairs, skipping $-prefixed metadata keys."""
    if not isinstance(node, dict):
        return []
    if is_token(node):
        return [(prefix, node)]
    found: list[tuple[tuple[str, ...], dict]] = []
    for key, child in node.items():
        if key.startswith("$"):
            continue
        found += walk_tokens(child, prefix + (key,))
    return found


# ── Colour parsing ──────────────────────────────────────────────────────────

RGBA = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", re.IGNORECASE
)


def parse_color(value: str) -> tuple[int, int, int, float]:
    """Accept #rgb, #rrggbb, #rrggbbaa, rgb() and rgba(). Returns (r, g, b, alpha 0..1)."""
    value = value.strip()
    match = RGBA.match(value)
    if match:
        r, g, b = (int(match.group(i)) for i in (1, 2, 3))
        alpha = float(match.group(4)) if match.group(4) is not None else 1.0
        return r, g, b, alpha

    if value.startswith("#"):
        hex_part = value[1:]
        if len(hex_part) == 3:
            hex_part = "".join(c * 2 for c in hex_part)
        if len(hex_part) == 6:
            r, g, b = (int(hex_part[i : i + 2], 16) for i in (0, 2, 4))
            return r, g, b, 1.0
        if len(hex_part) == 8:
            r, g, b, a = (int(hex_part[i : i + 2], 16) for i in (0, 2, 4, 6))
            return r, g, b, a / 255
        raise SystemExit(f"unsupported hex colour '{value}'")

    if value == "transparent":
        return 0, 0, 0, 0.0

    raise SystemExit(
        f"unsupported colour '{value}'. Add a parser branch rather than approximating it by hand."
    )


def apply_alpha(
    rgba: tuple[int, int, int, float], alpha: float | None
) -> tuple[int, int, int, float]:
    """semantic-map's {"token": ..., "alpha": x} multiplies the token's own alpha."""
    r, g, b, a = rgba
    return (r, g, b, a if alpha is None else a * alpha)


# ── Identifier naming ───────────────────────────────────────────────────────


def camel(parts: tuple[str, ...]) -> str:
    """('surface', 'paper') -> 'surfacePaper'."""
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    return out[:1].lower() + out[1:]


def pascal(name: str) -> str:
    return name[:1].upper() + name[1:]


# `radius.default` produced `public static let default`, which is a hard error in Swift — caught by
# `swiftc -parse` on the first generated file. Escaping is done generically rather than by renaming
# the token, so the JSON keeps reading like the CSS it mirrors and a future token that happens to
# collide is handled without another round of this.
SWIFT_KEYWORDS = frozenset(
    """associatedtype class deinit enum extension fileprivate func import init inout internal let
    open operator private protocol public rethrows static struct subscript typealias var break case
    continue default defer do else fallthrough for guard if in repeat return switch where while as
    Any catch false is nil rethrows super self Self throw throws true try""".split()
)

# Kotlin's hard keywords. Most emitted names are PascalCase and cannot collide, but `object` and
# `interface` would, and the cost of being safe is one frozenset.
KOTLIN_KEYWORDS = frozenset(
    """as break class continue do else false for fun if in interface is null object package return
    super this throw true try typealias typeof val var when while""".split()
)


def swift_ident(name: str) -> str:
    return f"`{name}`" if name in SWIFT_KEYWORDS else name


def kotlin_ident(name: str) -> str:
    return f"`{name}`" if name in KOTLIN_KEYWORDS else name


# ── Value collection ────────────────────────────────────────────────────────


def collect_cooking(palette: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-method colours and glyphs, order preserved — it is the picker's order.

    Validated here rather than trusted: a method missing one of the four colour roles would
    compile fine and then render an invisible label on one platform.
    """
    required = ("base", "soft", "onBase", "onSoft")
    methods = []
    for entry in palette["methods"]:
        missing = [role for role in required if role not in entry.get("color", {})]
        if missing:
            raise SystemExit(
                f"cooking-palette.json: method '{entry['id']}' is missing colour role(s) "
                f"{missing}. All four are needed — base and soft are fills, onBase and onSoft "
                f"are the labels that sit on them."
            )
        methods.append(
            {
                "id": entry["id"],
                "emoji": entry["emoji"],
                "colors": {role: parse_color(entry["color"][role]) for role in required},
            }
        )
    return methods


def collect(tree: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    """Flatten everything the apps need into plain Python, validating as we go."""
    colors = [
        (camel(path[1:]), parse_color(token["$value"]), token.get("$description", ""))
        for path, token in walk_tokens(tree.get("color", {}), ("color",))
    ]

    # Semantic roles that resolve to a colour, including alpha-of-token forms. Flattened to role
    # names like `buttonPrimaryBackground` so both languages get identical identifiers.
    roles: list[tuple[str, tuple[int, int, int, float], str]] = []

    def scan(node: Any, prefix: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            return
        if isinstance(node.get("token"), str):
            value = resolve(tree, node["token"])["$value"]
            if isinstance(value, str) and (value.startswith("#") or RGBA.match(value)):
                origin = node["token"] + (f" @ {node['alpha']}" if "alpha" in node else "")
                roles.append((camel(prefix), apply_alpha(parse_color(value), node.get("alpha")), origin))
            return
        for key, child in node.items():
            if key.startswith("$"):
                continue
            scan(child, prefix + (key,))

    for key, child in semantic.items():
        if key.startswith("$"):
            continue
        scan(child, (key,))

    radii = [
        (camel(path[1:]), token["$value"], token.get("$description", ""))
        for path, token in walk_tokens(tree.get("radius", {}), ("radius",))
    ]
    durations = [
        (camel(path[2:]), token["$value"])
        for path, token in walk_tokens(
            tree.get("motion", {}).get("duration", {}), ("motion", "duration")
        )
    ]
    confidence = [
        {
            "min": entry["min"],
            "level": entry["level"],
            "background": apply_alpha(
                parse_color(resolve(tree, entry["background"]["token"])["$value"]),
                entry["background"].get("alpha"),
            ),
            "foreground": apply_alpha(
                parse_color(resolve(tree, entry["foreground"]["token"])["$value"]),
                entry["foreground"].get("alpha"),
            ),
        }
        for entry in semantic["confidence"]["thresholds"]
    ]

    return {
        "colors": colors,
        "roles": roles,
        "radii": radii,
        "durations": durations,
        "easing": tree["motion"]["easing"]["outExpo"]["$value"],
        "focus": {
            "color": parse_color(tree["focus"]["ringColor"]["$value"]),
            "width": tree["focus"]["ringWidth"]["$value"],
            "offset": tree["focus"]["ringOffset"]["$value"],
        },
        "fonts": {
            path[-1]: token["$value"]
            for path, token in walk_tokens(tree.get("fontFamily", {}), ("fontFamily",))
        },
        "confidence": confidence,
        "cooking": collect_cooking(json.loads(COOKING.read_text())),
    }


# ── Emitters ────────────────────────────────────────────────────────────────


def px(value: str) -> str:
    """'18px' -> '18'. Refuses anything else rather than guessing a conversion."""
    if value.endswith("px"):
        return value[:-2]
    raise SystemExit(f"expected a px dimension, got '{value}' — convert it in the JSON instead")


def ms(value: str) -> str:
    if value.endswith("ms"):
        return value[:-2]
    raise SystemExit(f"expected a ms duration, got '{value}'")


def argb(rgba: tuple[int, int, int, float]) -> str:
    r, g, b, a = rgba
    return f"0x{round(a * 255):02X}{r:02X}{g:02X}{b:02X}"


def kotlin(data: dict[str, Any]) -> str:
    lines = [
        "// SPDX-License-Identifier: MPL-2.0",
        "/*",
        f" * {HEADER_NOTE}",
        " */",
        "package org.pocketnutrition.core.design",
        "",
        "import androidx.compose.animation.core.CubicBezierEasing",
        "import androidx.compose.ui.graphics.Color",
        "import androidx.compose.ui.unit.Dp",
        "import androidx.compose.ui.unit.dp",
        "",
        "/** Raw palette. Prefer [PnRole] at call sites — a role survives a palette change. */",
        "object PnColor {",
    ]
    for name, value, description in data["colors"]:
        if description:
            lines.append(f"    /** {description} */")
        lines.append(f"    val {kotlin_ident(pascal(name))} = Color({argb(value)})")
    lines += ["}", ""]

    lines += [
        "/**",
        " * Semantic roles, resolved from tokens/semantic-map.json. This is what UI code should",
        " * reference: a role records a decision, a palette entry is only a value.",
        " */",
        "object PnRole {",
    ]
    for name, value, origin in data["roles"]:
        lines.append(f"    /** {origin} */")
        lines.append(f"    val {kotlin_ident(pascal(name))} = Color({argb(value)})")
    lines += ["}", ""]

    lines += ["object PnRadius {"]
    for name, value, description in data["radii"]:
        if description:
            lines.append(f"    /** {description} */")
        lines.append(f"    val {kotlin_ident(pascal(name))}: Dp = {px(value)}.dp")
    lines += ["}", ""]

    lines += [
        "object PnMotion {",
        "    /** Honour ANIMATOR_DURATION_SCALE: the design system disables all motion under",
        "     *  reduced-motion, so these must collapse to 0 in that case. */",
    ]
    for name, value in data["durations"]:
        lines.append(f"    const val {kotlin_ident(pascal(name) + 'Millis')} = {ms(value)}")
    a, b, c, d = data["easing"]
    lines += [f"    val OutExpo = CubicBezierEasing({a}f, {b}f, {c}f, {d}f)", "}", ""]

    focus = data["focus"]
    lines += [
        "/** One focus treatment system-wide, in the ACCENT colour so focus never reads as selected. */",
        "object PnFocus {",
        f"    val Ring = Color({argb(focus['color'])})",
        f"    val Width: Dp = {px(focus['width'])}.dp",
        f"    val Offset: Dp = {px(focus['offset'])}.dp",
        "}",
        "",
        "/** Platform-default families. The design ships no webfont, so there is nothing to bundle. */",
        "object PnFont {",
    ]
    for name, stack in data["fonts"].items():
        lines.append(f"    // {name}: {', '.join(stack)}")
    lines += ["}", ""]

    lines += [
        "/**",
        " * Confidence badge colours. The THRESHOLDS are contractual — a user comparing Android and",
        " * iOS on the same meal must see the same badge. Evaluated in order, lower bound inclusive.",
        " */",
        "object PnConfidence {",
        "    data class Level(",
        "        val min: Float,",
        "        val level: String,",
        "        val background: Color,",
        "        val foreground: Color,",
        "    )",
        "",
        "    val Levels = listOf(",
    ]
    for entry in data["confidence"]:
        lines.append(
            f'        Level({entry["min"]}f, "{entry["level"]}", '
            f"Color({argb(entry['background'])}), Color({argb(entry['foreground'])})),"
        )
    lines += [
        "    )",
        "",
        "    fun forConfidence(value: Float): Level = Levels.first { value >= it.min }",
        "}",
        "",
    ]

    lines += [
        "/**",
        " * Cooking methods, in picker order. Labels are NOT here — they are translatable and live in",
        " * strings/fr.json under `cookingMethods`, keyed by [id].",
        " *",
        " * `onBase` is dark rather than white for grilled and roasted, because white on those fills is",
        " * only 3.0:1 and 3.2:1. An active chip must also keep a border: those two fills are below the",
        " * 3:1 that WCAG 1.4.11 wants against paper, so the border carries the component boundary.",
        " */",
        "object PnCooking {",
        "    data class Method(",
        "        val id: String,",
        "        val emoji: String,",
        "        /** Fill of the active chip. */",
        "        val base: Color,",
        "        /** Inactive pill and lane drop-zone background. */",
        "        val soft: Color,",
        "        /** Label on [base]. */",
        "        val onBase: Color,",
        "        /** Label on [soft], and the lane header text. */",
        "        val onSoft: Color,",
        "    )",
        "",
        "    val Methods = listOf(",
    ]
    for method in data["cooking"]:
        colors = method["colors"]
        lines.append(
            f'        Method("{method["id"]}", "{method["emoji"]}", '
            f"Color({argb(colors['base'])}), Color({argb(colors['soft'])}), "
            f"Color({argb(colors['onBase'])}), Color({argb(colors['onSoft'])})),"
        )
    lines += [
        "    )",
        "",
        "    /** Null for an unknown method — the API can add one, so do not throw. */",
        "    fun byId(id: String): Method? = Methods.firstOrNull { it.id == id }",
        "}",
        "",
    ]
    return "\n".join(lines)


def swift(data: dict[str, Any]) -> str:
    def swift_color(value: tuple[int, int, int, float]) -> str:
        r, g, b, a = value
        hex_part = f"0x{r:02X}{g:02X}{b:02X}"
        return f"Color(pnHex: {hex_part})" if a == 1.0 else f"Color(pnHex: {hex_part}, opacity: {a})"

    lines = [
        "// SPDX-License-Identifier: MPL-2.0",
        "/*",
        f" * {HEADER_NOTE}",
        " */",
        "import SwiftUI",
        "",
        "extension Color {",
        "    /// 0xRRGGBB plus a separate opacity, matching the generated call sites below.",
        "    init(pnHex: UInt32, opacity: Double = 1.0) {",
        "        self.init(",
        "            .sRGB,",
        "            red: Double((pnHex >> 16) & 0xFF) / 255,",
        "            green: Double((pnHex >> 8) & 0xFF) / 255,",
        "            blue: Double(pnHex & 0xFF) / 255,",
        "            opacity: opacity",
        "        )",
        "    }",
        "}",
        "",
        "/// Raw palette. Prefer `PnRole` at call sites — a role survives a palette change.",
        "public enum PnColor {",
    ]
    for name, value, description in data["colors"]:
        if description:
            lines.append(f"    /// {description}")
        lines.append(f"    public static let {swift_ident(name)} = {swift_color(value)}")
    lines += ["}", ""]

    lines += [
        "/// Semantic roles, resolved from tokens/semantic-map.json. UI code should reference these:",
        "/// a role records a decision, a palette entry is only a value.",
        "public enum PnRole {",
    ]
    for name, value, origin in data["roles"]:
        lines.append(f"    /// {origin}")
        lines.append(f"    public static let {swift_ident(name)} = {swift_color(value)}")
    lines += ["}", ""]

    lines += ["public enum PnRadius {"]
    for name, value, description in data["radii"]:
        if description:
            lines.append(f"    /// {description}")
        lines.append(f"    public static let {swift_ident(name)}: CGFloat = {px(value)}")
    lines += ["}", ""]

    lines += [
        "public enum PnMotion {",
        "    /// Honour UIAccessibility.isReduceMotionEnabled: the design system disables all motion",
        "    /// under reduced-motion, so these must collapse to 0 in that case.",
    ]
    for name, value in data["durations"]:
        lines.append(f"    public static let {swift_ident(name + 'Seconds')}: Double = {int(ms(value)) / 1000}")
    a, b, c, d = data["easing"]
    lines += [
        "    public static let outExpo = UnitCurve.bezier(",
        f"        startControlPoint: UnitPoint(x: {a}, y: {b}),",
        f"        endControlPoint: UnitPoint(x: {c}, y: {d})",
        "    )",
        "}",
        "",
    ]

    focus = data["focus"]
    lines += [
        "/// One focus treatment system-wide, in the ACCENT colour so focus never reads as selected.",
        "public enum PnFocus {",
        f"    public static let ring = {swift_color(focus['color'])}",
        f"    public static let width: CGFloat = {px(focus['width'])}",
        f"    public static let offset: CGFloat = {px(focus['offset'])}",
        "}",
        "",
        "/// Platform-default families. The design ships no webfont, so there is nothing to bundle.",
        "public enum PnFont {",
    ]
    for name, stack in data["fonts"].items():
        lines.append(f"    // {name}: {', '.join(stack)}")
    lines += ["}", ""]

    lines += [
        "/// Confidence badge colours. The THRESHOLDS are contractual — a user comparing Android and",
        "/// iOS on the same meal must see the same badge. Evaluated in order, lower bound inclusive.",
        "public enum PnConfidence {",
        "    public struct Level: Sendable {",
        "        public let min: Double",
        "        public let level: String",
        "        public let background: Color",
        "        public let foreground: Color",
        "    }",
        "",
        "    public static let levels: [Level] = [",
    ]
    for entry in data["confidence"]:
        lines.append(
            f'        Level(min: {entry["min"]}, level: "{entry["level"]}", '
            f"background: {swift_color(entry['background'])}, "
            f"foreground: {swift_color(entry['foreground'])}),"
        )
    lines += [
        "    ]",
        "",
        "    public static func forConfidence(_ value: Double) -> Level {",
        "        levels.first { value >= $0.min } ?? levels[levels.count - 1]",
        "    }",
        "}",
        "",
    ]

    lines += [
        "/// Cooking methods, in picker order. Labels are NOT here — they are translatable and live in",
        "/// strings/fr.json under `cookingMethods`, keyed by `id`.",
        "///",
        "/// `onBase` is dark rather than white for grilled and roasted, because white on those fills is",
        "/// only 3.0:1 and 3.2:1. An active chip must also keep a border: those two fills are below the",
        "/// 3:1 that WCAG 1.4.11 wants against paper, so the border carries the component boundary.",
        "public enum PnCooking {",
        "    public struct Method: Identifiable, Sendable {",
        "        public let id: String",
        "        public let emoji: String",
        "        /// Fill of the active chip.",
        "        public let base: Color",
        "        /// Inactive pill and lane drop-zone background.",
        "        public let soft: Color",
        "        /// Label on `base`.",
        "        public let onBase: Color",
        "        /// Label on `soft`, and the lane header text.",
        "        public let onSoft: Color",
        "    }",
        "",
        "    public static let methods: [Method] = [",
    ]
    for method in data["cooking"]:
        colors = method["colors"]
        lines.append(
            f'        Method(id: "{method["id"]}", emoji: "{method["emoji"]}", '
            f"base: {swift_color(colors['base'])}, soft: {swift_color(colors['soft'])}, "
            f"onBase: {swift_color(colors['onBase'])}, onSoft: {swift_color(colors['onSoft'])}),"
        )
    lines += [
        "    ]",
        "",
        "    /// nil for an unknown method — the API can add one, so do not trap.",
        "    public static func byId(_ id: String) -> Method? {",
        "        methods.first { $0.id == id }",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ── Entry point ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit native token sources from the JSON tokens.")
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if the committed output is stale (for CI)"
    )
    args = parser.parse_args()

    data = collect(json.loads(TOKENS.read_text()), json.loads(SEMANTIC.read_text()))
    outputs = {KOTLIN_OUT: kotlin(data), SWIFT_OUT: swift(data)}

    if args.check:
        stale = [
            str(path.relative_to(ROOT))
            for path, content in outputs.items()
            if not path.exists() or path.read_text() != content
        ]
        if stale:
            print(
                f"FAIL: stale generated tokens: {', '.join(stale)}\n"
                f"      Run: python3 scripts/emit_tokens.py   then commit the result."
            )
            return 1
        print(
            f"OK: generated tokens up to date "
            f"({len(data['colors'])} palette, {len(data['roles'])} roles)"
        )
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content)
        print(f"wrote {path.relative_to(ROOT)} ({len(content)} bytes)")
    print(
        f"\n{len(data['colors'])} palette colours, {len(data['roles'])} semantic roles, "
        f"{len(data['radii'])} radii, {len(data['durations'])} durations, "
        f"{len(data['confidence'])} confidence levels"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
