import random
from dataclasses import replace

from .models import Incident, Scenario


def _scenario(name: str, description: str, roles: tuple[tuple[str, str], ...], events: tuple[str, ...]) -> Scenario:
    systems = [system for _, system in roles]
    return Scenario(name, description, roles, (
        Incident(0, systems[0], 35, events[0]),
        Incident(1, systems[1], 45, events[1]),
        Incident(2, systems[2], 35, events[2]),
        Incident(3, systems[0], 50, events[3]),
        Incident(4, systems[1], 30, events[4]),
        Incident(6, systems[2], 42, events[2] + " — secondary failure"),
        Incident(8, systems[0], 38, events[0] + " — renewed pressure"),
        Incident(9, systems[1], 35, events[4] + " — reserve exhausted"),
        Incident(10, systems[2], 30, events[2] + " — final disruption"),
    ), ticks=12, budget=28,
        dependencies=((systems[0], systems[1]), (systems[0], systems[2]), (systems[1], systems[2])),
        setting={"spacecraft": "Orbital research vessel · Sector 07", "cyberattack": "Regional data center · Network perimeter",
                 "infrastructure": "Coastal district · Essential services", "supply-chain": "Pacific corridor · Distribution network"}[name],
        codename={"spacecraft": "Aster / 07", "cyberattack": "Blackout / 12", "infrastructure": "Highwater / 03", "supply-chain": "Bottleneck / 09"}[name])


SCENARIOS = {
    "cyberattack": _scenario(
        "cyberattack", "Contain an intrusion while preserving service availability.",
        (("security", "network"), ("operations", "services"), ("recovery", "backups")),
        ("Suspicious lateral movement", "Service overload", "Backup integrity loss", "Intrusion escalates", "Authentication outage"),
    ),
    "spacecraft": _scenario(
        "spacecraft", "Keep a damaged spacecraft operational through cascading faults.",
        (("engineering", "power"), ("medical", "life_support"), ("navigation", "guidance")),
        ("Solar array damage", "Oxygen leak", "Guidance sensor failure", "Battery thermal fault", "CO2 scrubber degradation"),
    ),
    "infrastructure": _scenario(
        "infrastructure", "Maintain essential city services during a severe storm.",
        (("grid", "electricity"), ("utilities", "water"), ("transport", "roads")),
        ("Substation flooding", "Pump station failure", "Bridge closure", "Transmission fault", "Water treatment disruption"),
    ),
    "supply-chain": _scenario(
        "supply-chain", "Keep goods moving through disruptions to supply and transport.",
        (("procurement", "supply"), ("logistics", "shipping"), ("warehouse", "inventory")),
        ("Supplier shutdown", "Port congestion", "Warehouse damage", "Component shortage", "Freight capacity loss"),
    ),
}


def build_scenario(name: str, seed: int = 23, difficulty: str = "standard") -> Scenario:
    if name not in SCENARIOS or difficulty not in ("standard", "severe", "critical"):
        raise ValueError("Unknown scenario or difficulty")
    if type(seed) is not int or not 0 <= seed <= 999999:
        raise ValueError("Seed must be an integer from 0 to 999999")
    rng = random.Random(seed)
    base = SCENARIOS[name]
    scale = {"standard": 1, "severe": 1.25, "critical": 1.5}[difficulty]
    return replace(base, incidents=tuple(replace(event, damage=round((event.damage + rng.randint(-6, 6)) * scale)) for event in base.incidents))
