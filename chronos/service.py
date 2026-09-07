"""Run lifecycle, background execution, persistence and controlled experiments."""
import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .actions import catalog
from .agents import RuleAgent
from .config import ROOT, Settings
from .engine import Simulation
from .gemini import GeminiAgent
from .scenarios import SCENARIOS, build_scenario


def options(payload: dict) -> dict:
    result = {"scenario": payload.get("scenario", "spacecraft"), "mode": payload.get("mode", "baseline"),
              "profile": payload.get("profile", "standard"), "seed": payload.get("seed", 23),
              "difficulty": payload.get("difficulty", "standard"), "communication": payload.get("communication", True)}
    for key, allowed in (("scenario", SCENARIOS), ("mode", ("baseline", "gemini")),
                         ("profile", ("standard", "fast", "reasoning")), ("difficulty", ("standard", "severe", "critical"))):
        if not isinstance(result[key], str) or result[key] not in allowed:
            raise ValueError(f"Invalid {key}")
    if type(result["communication"]) is not bool:
        raise ValueError("Communication must be true or false")
    build_scenario(result["scenario"], result["seed"], result["difficulty"])
    return result


def create_simulation(config: dict, settings: Settings) -> Simulation:
    scenario = build_scenario(config["scenario"], config["seed"], config["difficulty"])
    agents = {role: GeminiAgent(settings, config["profile"]) if config["mode"] == "gemini" else RuleAgent() for role, _ in scenario.roles}
    return Simulation(scenario, agents, config["communication"])


def snapshot(sim: Simulation) -> dict:
    return {**sim.result(), "description": sim.scenario.description, "setting": sim.scenario.setting,
            "codename": sim.scenario.codename, "tick": sim.tick, "max_ticks": sim.scenario.ticks,
            "initial_budget": sim.scenario.budget, "shields": dict(sim.shields), "roles": dict(sim.roles),
            "isolated": {system: sim.isolated(system) for system in sim.health},
            "dependencies": sim.scenario.dependencies, "finished": sim.finished,
            "policy_models": {role: getattr(agent, "model", "rule-baseline") for role, agent in sim.agents.items()},
            "actions": {role: catalog(sim.scenario.name, role) for role in sim.roles}, "scenarios": list(SCENARIOS)}


class BusyError(RuntimeError):
    pass


class RunStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def save(self, record: dict):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{record['id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def load(self, identifier: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{12}", identifier):
            raise ValueError("Invalid run identifier")
        try:
            return json.loads((self.directory / f"{identifier}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError("Saved run is unavailable") from None

    def list(self) -> list[dict]:
        rows = []
        if self.directory.exists():
            for path in sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    rows.append({key: data[key] for key in ("id", "created_at", "scenario", "outcome", "tick", "config", "metrics")})
                except (OSError, ValueError, KeyError):
                    continue
        return rows


class Controller:
    def __init__(self, settings: Settings | None = None, directory: Path | None = None):
        self.settings = settings or Settings.load()
        self.store = RunStore(directory or Path(os.environ.get("CHRONOS_RUNS_DIR", str(ROOT / "runs"))))
        self.lock = threading.RLock()
        self.running = self.busy = False
        self.error = ""
        self.evaluation = {"status": "idle", "rows": [], "progress": ""}
        self.reset({"mode": "gemini" if self.settings.api_key else "baseline"})

    def reset(self, payload: dict):
        with self.lock:
            if self.busy:
                raise BusyError("Pause and wait for the current turn to finish before creating a new run.")
            config = options(payload)
            sim = create_simulation(config, self.settings)
            self.running = False
            self.simulation, self.config = sim, config
            self.identifier = uuid.uuid4().hex[:12]
            self.created_at = datetime.now(timezone.utc).isoformat()
            self.error = ""
            self._publish()
            return self.state()

    def _publish(self):
        self.cached = copy.deepcopy({**snapshot(self.simulation), "id": self.identifier,
                                     "created_at": self.created_at, "config": self.config})
        if self.simulation.tick:
            try:
                self.store.save(self.cached)
            except OSError:
                self.error = "Run could not be saved to disk. Export the current trace before closing."

    def state(self):
        with self.lock:
            return {**copy.deepcopy(self.cached), "busy": self.busy, "running": self.running, "error": self.error,
                    "provider": {"configured": bool(self.settings.api_key), "model": self.settings.model,
                                 "profiles": {"standard": self.settings.model, "fast": self.settings.fast_model, "reasoning": self.settings.reasoning_model}},
                    "evaluation": copy.deepcopy(self.evaluation)}

    def start(self, continuous: bool = False):
        with self.lock:
            if self.busy:
                raise BusyError("A turn is already in progress.")
            if self.simulation.finished:
                return self.state()
            if self.evaluation["status"] == "running":
                raise BusyError("Wait for the comparison to finish or cancel it first.")
            self.running, self.busy, self.error = continuous, True, ""
            threading.Thread(target=self._work, daemon=True).start()
            return self.state()

    def pause(self):
        with self.lock:
            self.running = False
            return self.state()

    def _work(self):
        while True:
            try:
                before = len(self.simulation.log)
                self.simulation.step()
                failures = [event for event in self.simulation.log[before:] if event["kind"] == "agent_error"]
                with self.lock:
                    if failures:
                        self.error = failures[0]["error"] + " Run paused; failed decisions were recorded as holds."
                        self.running = False
                    self._publish()
                    if self.simulation.finished or not self.running:
                        self.running = self.busy = False
                        return
            except Exception:
                with self.lock:
                    self.error = "The turn failed. Create a new run to recover."
                    self.running = self.busy = False
                return
            threading.Event().wait(0.7)
            with self.lock:
                if not self.running:
                    self.busy = False
                    return

    def evaluate(self, payload: dict):
        config = options(payload)
        repeats = payload.get("repeats", 1)
        if type(repeats) is not int or not 1 <= repeats <= 3 or config["seed"] + repeats - 1 > 999999:
            raise ValueError("Choose 1–3 repetitions with valid consecutive seeds")
        if not self.settings.api_key:
            raise ValueError("Configure GEMINI_API_KEY before comparing model policies")
        with self.lock:
            if self.busy or self.evaluation["status"] == "running":
                raise BusyError("Pause the current run or wait for the active comparison.")
            self.cancel_evaluation = threading.Event()
            self.evaluation = {"status": "running", "rows": [], "progress": "Preparing comparison", "config": config, "repeats": repeats}
            threading.Thread(target=self._evaluate, args=(config, repeats), daemon=True).start()
            return self.state()

    def _evaluate(self, config: dict, repeats: int):
        try:
            for repetition in range(repeats):
                for label, mode, communication in (("Rule baseline", "baseline", True), ("Independent", "gemini", False), ("Communicating", "gemini", True)):
                    if self.cancel_evaluation.is_set():
                        break
                    case = {**config, "mode": mode, "communication": communication, "seed": config["seed"] + repetition}
                    sim = create_simulation(case, self.settings)
                    while not sim.finished and not self.cancel_evaluation.is_set():
                        with self.lock:
                            self.evaluation["progress"] = f"{label} · seed {case['seed']} · turn {sim.tick + 1}/{sim.scenario.ticks}"
                        sim.step()
                        if sim.metrics()["errors"]:
                            break
                    record = {**snapshot(sim), "config": case, "id": uuid.uuid4().hex[:12], "created_at": datetime.now(timezone.utc).isoformat()}
                    self.store.save(record)
                    row = {"id": record["id"], "policy": label, "seed": case["seed"], "outcome": record["outcome"],
                           "tick": sim.tick, "valid": sim.finished and sim.metrics()["errors"] == 0, **sim.metrics()}
                    with self.lock:
                        self.evaluation["rows"].append(row)
                    if sim.metrics()["errors"]:
                        raise ValueError("Comparison stopped after a provider failure. Partial results are marked invalid; check the run trace.")
            with self.lock:
                self.evaluation.update(status="cancelled" if self.cancel_evaluation.is_set() else "complete", progress="")
        except Exception as exc:
            with self.lock:
                self.evaluation.update(status="error", progress=str(exc) if isinstance(exc, ValueError) else "Comparison failed; check configuration and storage.")

    def cancel_comparison(self):
        with self.lock:
            if self.evaluation["status"] == "running":
                self.cancel_evaluation.set()
                self.evaluation["progress"] = "Cancelling after the current turn…"
            return self.state()
