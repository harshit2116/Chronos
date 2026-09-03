"""The engine, prompts and UI consume the same action definitions."""
ACTIONS = {
    "wait": {"cost": 0, "label": "Hold", "effect": "Preserve response credits. No health change."},
    "repair": {"cost": 2, "label": "Repair", "effect": "Restore 25 health to your subsystem, capped at 100."},
    "fortify": {"cost": 1, "label": "Reinforce", "effect": "Add 15 damage protection, capped at 30."},
    "assist": {"cost": 2, "label": "Divert resources", "effect": "Restore 20 health to a target peer; your subsystem loses 5 health. Requires own health above 10."},
    "isolate": {"cost": 1, "label": "Isolate", "effect": "For the next 2 ticks, halve incoming incident damage and block outgoing cascades; service delivery is halved."},
    "surge": {"cost": 3, "label": "Emergency recovery", "effect": "Restore 40 health now. Suffer 12 wear damage next tick, bypassing protection."},
}

SPECIAL = {
    "spacecraft": {"engineering": "Overdrive reactor", "medical": "Emergency scrub cycle", "navigation": "Recalibrate guidance"},
    "cyberattack": {"security": "Rotate access keys", "operations": "Fail over services", "recovery": "Restore snapshot"},
    "infrastructure": {"grid": "Start reserve turbine", "utilities": "Flush treatment line", "transport": "Open relief route"},
    "supply-chain": {"procurement": "Emergency procurement", "logistics": "Charter freight", "warehouse": "Release reserve stock"},
}


def catalog(scenario: str, role: str) -> tuple[dict, ...]:
    return tuple({"id": key, **value, "label": SPECIAL.get(scenario, {}).get(role, value["label"]) if key == "surge" else value["label"]}
                 for key, value in ACTIONS.items())
