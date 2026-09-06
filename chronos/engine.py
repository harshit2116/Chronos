import heapq
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from .actions import ACTIONS, catalog
from .models import Agent, Decision, Incident, Message, Observation, Scenario


class Simulation:
    """Deterministic world; simultaneous private decisions; authoritative validation."""
    ACTIONS = {key: value["cost"] for key, value in ACTIONS.items()}

    def __init__(self, scenario: Scenario, agents: dict[str, Agent], communication: bool = True):
        self.roles = dict(scenario.roles)
        if not self.roles or len(self.roles) != len(scenario.roles):
            raise ValueError("Scenario must have unique, nonempty roles")
        if len(set(self.roles.values())) != len(self.roles):
            raise ValueError("Each role must own a distinct subsystem")
        if set(agents) != set(self.roles):
            raise ValueError("Exactly one agent is required for every scenario role")
        if scenario.ticks < 1 or scenario.budget < 0:
            raise ValueError("Invalid tick count or budget")
        if any(a not in self.roles.values() or b not in self.roles.values() or a == b for a, b in scenario.dependencies):
            raise ValueError("Invalid subsystem dependency")
        self.scenario, self.agents, self.communication = scenario, agents, communication
        self.health = dict.fromkeys(self.roles.values(), 100)
        self.shields = dict.fromkeys(self.roles.values(), 0)
        self.isolated_until = dict.fromkeys(self.roles.values(), -1)
        self.budget, self.tick = scenario.budget, 0
        self.log: list[dict] = []
        self.inspections: dict[str, list[dict]] = {role: [] for role in self.roles}
        self.inbox: dict[str, list[Message]] = {role: [] for role in self.roles}
        self.last_result = dict.fromkeys(self.roles, "No previous action.")
        self._events: list[tuple[int, int, Incident, bool]] = []
        self._sequence = 0
        for incident in scenario.incidents:
            self.schedule(incident)

    def schedule(self, incident: Incident, wear: bool = False) -> None:
        if incident.tick < self.tick or incident.damage < 0 or incident.subsystem not in self.health:
            raise ValueError("Invalid incident time, damage, or subsystem")
        heapq.heappush(self._events, (incident.tick, self._sequence, incident, wear))
        self._sequence += 1

    @property
    def finished(self) -> bool:
        return self.tick >= self.scenario.ticks or min(self.health.values()) <= 0

    def isolated(self, system: str) -> bool:
        return self.tick <= self.isolated_until[system]

    def _record(self, kind: str, **details: object) -> None:
        self.log.append({"tick": self.tick, "kind": kind, **details})

    def _damage(self, system: str, damage: int, wear: bool = False) -> int:
        if not wear:
            damage = (damage + 1) // 2 if self.isolated(system) else damage
            absorbed = min(self.shields[system], damage)
            self.shields[system] -= absorbed
            damage -= absorbed
        actual = min(damage, self.health[system])
        self.health[system] -= actual
        return actual

    def _decide(self, role: str, observation: Observation):
        try:
            decision = self.agents[role].decide(observation)
            if not isinstance(decision, Decision) or not isinstance(decision.action, str) or decision.action not in self.ACTIONS:
                raise ValueError("Unknown action")
            if decision.recipient is not None and decision.recipient != "all" and decision.recipient not in observation.peers:
                raise ValueError("Invalid message recipient")
            if not isinstance(decision.message, str) or len(decision.message) > 500:
                raise ValueError("Message must be at most 500 characters")
            if not isinstance(decision.rationale, str) or len(decision.rationale) > 300:
                raise ValueError("Invalid decision justification")
            if decision.action == "assist":
                if decision.target not in observation.peers or observation.health <= 10:
                    raise ValueError("Assistance requires a peer target and own health above 10")
            elif decision.target is not None:
                raise ValueError("Only assist may target another role")
            return decision, None
        except Exception as exc:
            from .gemini import ProviderError
            error = str(exc) if isinstance(exc, ProviderError) else "Agent decision failed validation."
            return Decision(rationale="Hold because no valid decision was available."), error

    def step(self) -> None:
        if self.finished:
            raise RuntimeError("Simulation has finished")
        visible: dict[str, list[str]] = {system: [] for system in self.health}
        while self._events and self._events[0][0] <= self.tick:
            _, _, incident, wear = heapq.heappop(self._events)
            damage = self._damage(incident.subsystem, incident.damage, wear)
            visible[incident.subsystem].append(incident.description)
            self._record("incident", subsystem=incident.subsystem, description=incident.description, damage=damage)
        failing = {system for system, health in self.health.items() if health < 45 and not self.isolated(system)}
        for source, target in self.scenario.dependencies:
            if source in failing:
                damage = self._damage(target, 10)
                description = f"Degraded {source.replace('_', ' ')} disrupts {target.replace('_', ' ')}"
                visible[target].append(description)
                self._record("cascade", subsystem=target, source=source, description=description, damage=damage)
        if min(self.health.values()) > 0:
            observations = {}
            for role, system in self.roles.items():
                observations[role] = Observation(
                    self.tick, role, system, self.health[system], self.budget, tuple(visible[system]),
                    tuple(self.inbox[role]) if self.communication else (), tuple(peer for peer in self.roles if peer != role),
                    self.shields[system], self.isolated(system), self.scenario.ticks - self.tick,
                    self.scenario.description, catalog(self.scenario.name, role), self.scenario.dependencies,
                    self.communication, self.last_result[role])
            with ThreadPoolExecutor(max_workers=len(self.roles)) as pool:
                futures = {role: pool.submit(self._decide, role, obs) for role, obs in observations.items()}
                decisions = {}
                for role, future in futures.items():
                    decision, error = future.result()
                    decisions[role] = decision
                    if error:
                        self._record("agent_error", role=role, error=error)
                    self.inspections[role].append({"tick": self.tick, "observation": asdict(observations[role]),
                                                   "decision": asdict(decision), "error": error})
            next_inbox: dict[str, list[Message]] = {role: [] for role in self.roles}
            order = list(self.roles)
            offset = self.tick % len(order)
            for role in order[offset:] + order[:offset]:
                decision = decisions[role]
                system = self.roles[role]
                cost = self.ACTIONS[decision.action]
                accepted = cost <= self.budget
                reason = "" if accepted else "Insufficient shared credits"
                if decision.action == "assist" and self.health[system] <= 10:
                    accepted, reason = False, "Own subsystem too weak to assist"
                if accepted:
                    self.budget -= cost
                    if decision.action == "repair":
                        self.health[system] = min(100, self.health[system] + 25)
                    elif decision.action == "fortify":
                        self.shields[system] = min(30, self.shields[system] + 15)
                    elif decision.action == "isolate":
                        self.isolated_until[system] = self.tick + 2
                    elif decision.action == "surge":
                        self.health[system] = min(100, self.health[system] + 40)
                        self.schedule(Incident(self.tick + 1, system, 12, "Wear from emergency recovery"), wear=True)
                    elif decision.action == "assist":
                        target = self.roles[decision.target]
                        self.health[target] = min(100, self.health[target] + 20)
                        self.health[system] -= 5
                self.last_result[role] = f"{decision.action}: {'applied' if accepted else reason}"
                self.inspections[role][-1]["result"] = self.last_result[role]
                self._record("action", role=role, action=decision.action, target=decision.target,
                             accepted=accepted, reason=reason, cost=cost if accepted else 0, rationale=decision.rationale)
                if self.communication and decision.recipient and decision.message:
                    recipients = [peer for peer in self.roles if peer != role] if decision.recipient == "all" else [decision.recipient]
                    for recipient in recipients:
                        message = Message(role, recipient, decision.message)
                        next_inbox[recipient].append(message)
                        self._record("message", **asdict(message))
            self.inbox = next_inbox
        service = round(sum(health * (0.5 if self.isolated(system) else 1) for system, health in self.health.items()) / len(self.health), 1)
        usage = {key: sum(getattr(agent, "usage", {}).get(key, 0) for agent in self.agents.values())
                 for key in ("requests", "input_tokens", "output_tokens", "total_tokens")}
        self._record("snapshot", health=dict(self.health), shields=dict(self.shields), budget=self.budget,
                     service=service, usage=usage)
        self.tick += 1

    def metrics(self) -> dict:
        snapshots = [e for e in self.log if e["kind"] == "snapshot"]
        usage = {key: sum(getattr(agent, "usage", {}).get(key, 0) for agent in self.agents.values())
                 for key in ("requests", "input_tokens", "output_tokens", "total_tokens")}
        return {"mean_health": round(sum(self.health.values()) / len(self.health), 1),
                "service": round(sum(e["service"] for e in snapshots) / len(snapshots), 1) if snapshots else 100,
                "credits_spent": self.scenario.budget - self.budget,
                "messages": sum(e["kind"] == "message" for e in self.log),
                "cascades": sum(e["kind"] == "cascade" for e in self.log),
                "errors": sum(e["kind"] == "agent_error" for e in self.log), **usage}

    def result(self) -> dict:
        return {"scenario": self.scenario.name, "outcome": "failed" if min(self.health.values()) <= 0 else "survived" if self.finished else "active",
                "ticks": self.tick, "health": dict(self.health), "budget": self.budget,
                "events": list(self.log), "metrics": self.metrics(), "inspections": self.inspections}

    def run(self) -> dict:
        while not self.finished:
            self.step()
        return self.result()
