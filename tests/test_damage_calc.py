"""Tests for tools/damage_calc.py and the @smogon/calc bridge (tools/calc/calc.mjs).

The "known calc" tests recompute results by hand with the Champions stat
formula (HP = base + SP + 75; other stats = floor((base + SP + 20) * nature))
and the standard damage formula, then compare them with the bridge output.
They are skipped when Node.js or the pinned calc package is not installed.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import damage_calc  # noqa: E402
from vgc_data.pokedex import Pokedex  # noqa: E402


BASE_STATS = {  # hp, atk, def, spa, spd, spe
    "Kingambit": (100, 135, 120, 60, 85, 50),
    "Incineroar": (95, 115, 90, 80, 90, 60),
    "Garchomp": (108, 130, 95, 80, 85, 102),
    "Whimsicott": (60, 67, 85, 77, 75, 116),
    "Charizard-Mega-Y": (78, 104, 78, 159, 115, 100),
}
STAT_NAMES = ("hp", "atk", "def", "spa", "spd", "spe")


def champions_stats(species: str, sp: dict[str, int], plus: str | None = None, minus: str | None = None) -> dict[str, int]:
    stats = {}
    for name, base in zip(STAT_NAMES, BASE_STATS[species]):
        points = sp.get(name, 0)
        if name == "hp":
            stats[name] = base + points + 75
            continue
        factor = 1.1 if name == plus else 0.9 if name == minus else 1.0
        stats[name] = math.floor((base + points + 20) * factor)
    return stats


def poke_round(value: float) -> int:
    return math.ceil(value) if value % 1 > 0.5 else math.floor(value)


def reference_rolls(attack: int, defense: int, power: int, *, spread=False, weather=1.0, stab=False, effectiveness=1.0) -> list[int]:
    base = math.floor(math.floor(22 * power * attack / defense) / 50) + 2
    if spread:
        base = poke_round(base * 3072 / 4096)
    if weather != 1.0:
        base = poke_round(base * weather)
    rolls = []
    for roll in range(85, 101):
        damage = math.floor(base * roll / 100)
        if stab:
            damage = poke_round(damage * 1.5)
        rolls.append(math.floor(damage * effectiveness))
    return rolls


def request(**overrides):
    payload = {
        "calc_type": "damage",
        "move": "Iron Head",
        "attacker": {"species": "Kingambit", "nature": "Adamant", "evs": {"at": 32}},
        "defender": {"species": "Incineroar", "nature": "Careful", "evs": {"hp": 32}},
        "field": {"format": "Doubles"},
    }
    payload.update(overrides)
    return payload


@unittest.skipUnless(damage_calc.smogon_available(), "Node.js or @smogon/calc is not installed (run npm ci in tools/calc)")
class KnownCalcTests(unittest.TestCase):
    def numeric(self, payload: dict) -> dict:
        result = damage_calc.execute(payload, backend="smogon", dex=Pokedex())
        self.assertEqual(result["status"], "exact", result["failure_reason"])
        self.assertEqual(result["backend"], "smogon-calc")
        return result["numeric_result"]

    def test_champions_stat_formula(self) -> None:
        output = self.numeric(request())
        self.assertEqual(output["attacker"]["stats"], champions_stats("Kingambit", {"atk": 32}, plus="atk", minus="spa"))
        self.assertEqual(output["defender"]["stats"], champions_stats("Incineroar", {"hp": 32}, plus="spd", minus="spa"))

    def test_single_target_resisted_stab_hit(self) -> None:
        output = self.numeric(request())
        expected = reference_rolls(205, 110, 80, stab=True, effectiveness=0.5)
        self.assertEqual(output["damage"]["rolls"], expected)
        self.assertEqual((output["damage"]["min"], output["damage"]["max"]), (42, 50))
        self.assertEqual(output["ko"]["text"], "guaranteed 5HKO")

    def test_spread_move_in_sun_on_mega_with_super_effective_hit(self) -> None:
        output = self.numeric(
            request(
                calc_type="ko",
                move="Heat Wave",
                attacker={"species": "Charizard", "item": "Charizardite Y", "ability": "Blaze", "nature": "Modest", "evs": {"sa": 32}},
                defender={"species": "Kingambit", "nature": "Adamant", "evs": {"hp": 32}},
                field={"format": "Doubles", "weather": "Sun"},
            )
        )
        self.assertEqual(output["attacker"]["species"], "Charizard-Mega-Y")
        self.assertEqual(output["attacker"]["stats"]["spa"], 232)
        expected = reference_rolls(232, 105, 95, spread=True, weather=1.5, stab=True, effectiveness=2.0)
        self.assertEqual(output["damage"]["rolls"], expected)
        self.assertEqual((output["damage"]["min"], output["damage"]["max"]), (266, 314))
        self.assertEqual(output["ko"]["text"], "guaranteed OHKO")

    def test_singles_has_no_spread_reduction(self) -> None:
        doubles = self.numeric(request(move="Earthquake", attacker={"species": "Garchomp", "nature": "Jolly", "evs": {"at": 32}}))
        singles = self.numeric(
            request(move="Earthquake", attacker={"species": "Garchomp", "nature": "Jolly", "evs": {"at": 32}}, field={"format": "Singles"})
        )
        self.assertGreater(singles["damage"]["max"], doubles["damage"]["max"])

    def test_speed_with_tailwind_and_boosts(self) -> None:
        output = self.numeric(
            {
                "calc_type": "speed",
                "attacker": {"species": "Whimsicott", "nature": "Timid", "evs": {"sp": 32}},
                "defender": {"species": "Garchomp", "nature": "Jolly", "evs": {"sp": 32}, "boosts": {"spe": 1}},
                "field": {"attacker_side": {"tailwind": True}},
            }
        )
        whimsicott = champions_stats("Whimsicott", {"spe": 32}, plus="spe", minus="atk")["spe"]
        garchomp = champions_stats("Garchomp", {"spe": 32}, plus="spe", minus="spa")["spe"]
        self.assertEqual(output["speed"], {"attacker": whimsicott * 2, "defender": math.floor(garchomp * 1.5), "faster": "attacker"})

    def test_unknown_species_is_reported(self) -> None:
        result = damage_calc.execute(request(attacker={"species": "Notamon", "evs": {}}), backend="smogon", dex=Pokedex())
        self.assertEqual(result["status"], "fallback")
        self.assertIn("unknown species", result["failure_reason"])


class WrapperTests(unittest.TestCase):
    def test_stat_point_limits_block_the_request(self) -> None:
        over_one = damage_calc.execute(request(attacker={"species": "Kingambit", "evs": {"at": 33}}), bridge=self.fail_bridge)
        over_total = damage_calc.execute(
            request(attacker={"species": "Kingambit", "evs": {"hp": 32, "at": 32, "sp": 3}}), bridge=self.fail_bridge
        )
        no_move = damage_calc.execute(request(move=""), bridge=self.fail_bridge)
        self.assertEqual(over_one["status"], "blocked")
        self.assertIn("above 32", over_one["failure_reason"])
        self.assertIn("cap of 66", over_total["failure_reason"])
        self.assertIn("A move is required", no_move["failure_reason"])

    @staticmethod
    def fail_bridge(_payload):
        raise AssertionError("the bridge must not run for invalid requests")

    def test_mega_stone_maps_to_mega_form_and_drops_base_ability(self) -> None:
        dex = Pokedex.from_vgchistory(
            {"charizard-mega-y": {"base": "charizard", "tfrom": "charizard", "ps": "Charizard-Mega-Y"}}
        )
        captured = {}

        def bridge(payload):
            captured.update(payload)
            return {"ok": True}

        result = damage_calc.execute(
            request(attacker={"species": "Charizard", "item": "Charizardite Y", "ability": "Blaze"}), dex=dex, bridge=bridge
        )
        self.assertEqual(captured["attacker"]["species"], "Charizard-Mega-Y")
        self.assertIsNone(captured["attacker"]["ability"])
        self.assertEqual(captured["attacker"]["evs"], {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0})
        self.assertTrue(any("Mega Evolved" in note for note in result["assumptions_used"]["notes"]))

    def test_auto_backend_falls_back_to_the_browser_calc(self) -> None:
        def broken(_payload):
            raise damage_calc.CalcBackendError("Node.js is not installed")

        def browser(req):
            return damage_calc.upstream.CalcResult("exact", "agent-browser", "pikalytics", {"damage": "x"}, {}, "t", None)

        result = damage_calc.execute(request(), bridge=broken, fallback=browser, dex=Pokedex())
        self.assertEqual(result["backend"], "agent-browser")
        self.assertTrue(any("smogon-calc unavailable" in note for note in result["assumptions_used"]["notes"]))

        forced = damage_calc.execute(request(), backend="smogon", bridge=broken, dex=Pokedex())
        self.assertEqual(forced["status"], "fallback")
        self.assertIn("Node.js is not installed", forced["failure_reason"])

    def test_speed_never_falls_back_to_the_browser_calc(self) -> None:
        def broken(_payload):
            raise damage_calc.CalcBackendError("boom")

        result = damage_calc.execute(
            {"calc_type": "speed", "attacker": {"species": "Garchomp"}, "defender": {"species": "Kingambit"}},
            bridge=broken,
            fallback=self.fail_bridge,
            dex=Pokedex(),
        )
        self.assertEqual(result["status"], "fallback")


if __name__ == "__main__":
    unittest.main()
