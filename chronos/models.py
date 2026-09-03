from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Incident:
    tick: int
    subsystem: str
    damage: int
    description: str


@dataclass(frozen=True)
class Message:
    sender: str
    recipient: str
    content: str


@dataclass(frozen=True)
class Observation:
    tick: int
    role: str
    subsystem: str
    health: int
    budget: int
    incidents: tuple[str, ...]
    inbox: tuple[Message, ...]
    peers: tuple[str, ...]
    protection: int = 0
    isolated: bool = False
    remaining_ticks: int = 0
    brief: str = ""
    actions: tuple[dict, ...] = ()
    dependencies: tuple[tuple[str, str], ...] = ()
    communication: bool = True
    last_result: str = "No previous action."


@dataclass(frozen=True)
class Decision:
    action: str = "wait"
    recipient: str | None = None
    message: str = ""
    target: str | None = None
    rationale: str = ""


class Agent(Protocol):
    def decide(self, observation: Observation) -> Decision: ...


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    roles: tuple[tuple[str, str], ...]
    incidents: tuple[Incident, ...]
    ticks: int = 8
    budget: int = 18
    dependencies: tuple[tuple[str, str], ...] = ()
    setting: str = ""
    codename: str = ""
