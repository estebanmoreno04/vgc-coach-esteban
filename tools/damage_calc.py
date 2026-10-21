#!/usr/bin/env python3
"""Exact damage, KO, survival and speed calcs for Pokemon Champions.

Added in the estebanmoreno04 fork of NoahJenkins/vgc-coach. The primary
backend is @smogon/calc (Champions mechanics, generation 0) run through
Node (tools/calc/calc.mjs). The upstream browser backend
(tools/browser_damage_calc.py: Pikalytics + agent-browser) stays as the
fallback when Node or the calc package is unavailable.

The request and result contract is the same as tools/browser_damage_calc.py,
plus ``calc_type: "speed"`` (final speeds after nature, stat points, boosts,
items, abilities and Tailwind).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import browser_damage_calc as upstream  # noqa: E402
from vgc_data.pokedex import Pokedex  # noqa: E402


TOOLS_DIR = Path(__file__).resolve().parent
BRIDGE = TOOLS_DIR / "calc" / "calc.mjs"
CALC_PACKAGE = TOOLS_DIR / "calc" / "node_modules" / "@smogon" / "calc"
POKEDEX_PATH = TOOLS_DIR.parent / "data" / "current" / "pokedex.json"
NODE_TIMEOUT_SECONDS = 20
SUPPORTED_TYPES = {"damage", "ko", "survival", "speed"}
_EV_KEYS = {"hp": "hp", "at": "atk", "df": "def", "sa": "spa", "sd": "spd", "sp": "spe"}


class CalcBackendError(RuntimeError):
    """The smogon-calc backend could not run."""


def smogon_available() -> bool:
    return shutil.which("node") is not None and BRIDGE.exists() and CALC_PACKAGE.exists()


def parse_request(payload: dict[str, Any]) -> upstream.CalcRequest:
    return upstream.parse_request(payload)


def validation_errors(request: upstream.CalcRequest) -> list[str]:
    errors = [
        error for error in upstream.validation_errors(request)
        if not error.startswith("Only damage, ko, and survival") and not error.startswith("A move is required")
    ]
    if request.calc_type not in SUPPORTED_TYPES:
        errors.append("calc_type must be damage, ko, survival or speed.")
    if request.calc_type != "speed" and not request.move:
        errors.append("A move is required for damage, ko and survival calcs.")
    return errors


def _side(side: upstream.CalcSide, raw_boosts: dict[str, Any], dex: Pokedex, notes: list[str]) -> dict[str, Any]:
    species = side.species
    ability = side.ability or None
    if "-mega" not in species.lower() and side.item:
        mega = dex.mega_for(Pokedex().identity(species)[0], side.item) if dex else None
        if mega:
            mega_name = dex.display(mega)
            notes.append(f"{species} holding {side.item} is calculated as {mega_name} (Mega Evolved, its own ability).")
            species, ability = mega_name, None
    boosts = side.normalized_boosts()
    if "spe" in raw_boosts or "sp" in raw_boosts:
        boosts["spe"] = int(raw_boosts.get("spe", raw_boosts.get("sp", 0)))
    return {
        "species": species,
        "ability": ability,
        "item": side.item or None,
        "nature": side.nature,
        "evs": {_EV_KEYS[key]: value for key, value in side.normalized_evs().items()},
        "boosts": boosts,
        "status": (side.status or "Healthy").strip().lower().replace(" ", "_"),
        "current_hp_percent": side.current_hp_percent,
    }


def build_bridge_request(request: upstream.CalcRequest, raw: dict[str, Any], dex: Pokedex, notes: list[str]) -> dict[str, Any]:
    field = raw.get("field", {}) or {}
    return {
        "calc_type": request.calc_type,
        "move": request.move,
        "is_crit": bool(raw.get("is_crit", False)),
        "attacker": _side(request.attacker, (raw.get("attacker") or {}).get("boosts") or {}, dex, notes),
        "defender": _side(request.defender, (raw.get("defender") or {}).get("boosts") or {}, dex, notes),
        "field": {
            "format": request.field.format,
            "weather": request.field.weather,
            "terrain": request.field.terrain,
            "attacker_side": field.get("attacker_side") or {},
            "defender_side": field.get("defender_side") or {},
        },
    }


def run_bridge(bridge_request: dict[str, Any]) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        raise CalcBackendError("Node.js is not installed")
    if not CALC_PACKAGE.exists():
        raise CalcBackendError("@smogon/calc is not installed; run `npm ci` in tools/calc")
    try:
        completed = subprocess.run(
            [node, str(BRIDGE)],
            input=json.dumps(bridge_request),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=NODE_TIMEOUT_SECONDS,
            cwd=str(BRIDGE.parent),
        )
    except subprocess.TimeoutExpired as exc:
        raise CalcBackendError(f"calc bridge timed out after {NODE_TIMEOUT_SECONDS} s") from exc
    try:
        output = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise CalcBackendError(f"calc bridge returned invalid JSON: {completed.stderr.strip()[:300]}") from exc
    if not output.get("ok"):
        raise CalcBackendError(output.get("error") or completed.stderr.strip()[:300] or "calc bridge failed")
    return output


def execute(
    payload: dict[str, Any],
    *,
    backend: str = "auto",
    dex: Pokedex | None = None,
    bridge: Callable[[dict[str, Any]], dict[str, Any]] = run_bridge,
    fallback: Callable[[upstream.CalcRequest], upstream.CalcResult] | None = None,
) -> dict[str, Any]:
    request = parse_request(payload)
    errors = validation_errors(request)
    if errors:
        result = upstream.blocked_result(request, " ".join(errors))
        result.backend, result.site = "smogon-calc", None
        return result.to_dict()
    notes: list[str] = []
    dex = dex if dex is not None else Pokedex.load(POKEDEX_PATH)
    if backend in {"auto", "smogon"}:
        try:
            output = bridge(build_bridge_request(request, payload, dex, notes))
            assumptions = upstream.request_summary(request)
            assumptions["calc_type"] = request.calc_type
            assumptions["notes"] = notes
            return upstream.CalcResult(
                status="exact",
                backend="smogon-calc",
                site=None,
                numeric_result=output,
                assumptions_used=assumptions,
                retrieval_timestamp=upstream.timestamp_now(),
                failure_reason=None,
            ).to_dict()
        except CalcBackendError as exc:
            if backend == "smogon" or request.calc_type == "speed":
                result = upstream.fallback_result(request, f"smogon-calc unavailable: {exc}")
                result.backend, result.site = "smogon-calc", None
                return result.to_dict()
            notes.append(f"smogon-calc unavailable ({exc}); trying the Pikalytics browser backend")
    result = upstream.execute_exact_calc(request, runner=fallback)
    payload_out = result.to_dict()
    if notes:
        payload_out["assumptions_used"]["notes"] = notes
    return payload_out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request-file", help="Path to a JSON calc request; stdin is read when omitted.")
    parser.add_argument("--backend", choices=("auto", "smogon", "pikalytics"), default="auto")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    if args.request_file:
        payload = json.loads(Path(args.request_file).read_text(encoding="utf-8-sig"))
    else:
        payload = json.loads(sys.stdin.read().lstrip("﻿"))
    result = execute(payload, backend=args.backend)
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
