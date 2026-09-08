import argparse
import json
from pathlib import Path

from .config import Settings
from .service import create_simulation, options, snapshot
from .scenarios import SCENARIOS


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronos multi-agent crisis simulator")
    parser.add_argument("--scenario", choices=SCENARIOS, default="spacecraft")
    parser.add_argument("--output", type=Path, help="Save the full event trace as JSON")
    parser.add_argument("--mode", choices=("baseline", "gemini"), default="baseline")
    parser.add_argument("--profile", choices=("standard", "fast", "reasoning"), default="standard")
    parser.add_argument("--difficulty", choices=("standard", "severe", "critical"), default="standard")
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--no-communication", action="store_true")
    args = parser.parse_args()
    try:
        config = options({**vars(args), "communication": not args.no_communication})
        sim = create_simulation(config, Settings.load())
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Chronos | {sim.scenario.name} | {args.mode}\n{sim.scenario.description}\n", flush=True)
    while not sim.finished:
        sim.step()
        status = " | ".join(f"{system}: {health}" for system, health in sim.health.items())
        print(f"Turn {sim.tick:02d} | {status} | budget: {sim.budget}", flush=True)
        if sim.metrics()["errors"]:
            print("Run stopped after an agent error. Inspect the exported trace.")
            break
    result = {**snapshot(sim), "config": config}
    print(f"\nOutcome: {result['outcome']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Trace saved to {args.output}")
    if sim.metrics()["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
