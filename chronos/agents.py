import re

from .models import Decision, Observation


class RuleAgent:
    """Offline baseline using only information available to its role."""
    def decide(self, observation: Observation) -> Decision:
        action, target = "wait", None
        rationale = "Preserve credits for later incidents."
        if observation.health < 45 and observation.budget >= 3:
            action, rationale = "surge", "Restore a critical subsystem before it triggers further failures."
        elif observation.health <= 75 and observation.budget >= 2:
            action, rationale = "repair", "Restore damaged capacity while repair credits are available."
        else:
            for message in observation.inbox:
                match = re.search(r"health=(\d+)", message.content)
                if match and int(match.group(1)) < 45 and observation.health > 70 and observation.budget >= 2:
                    action, target = "assist", message.sender
                    rationale = "A peer reports critical capacity; divert resources to stabilize it."
                    break
            if action == "wait" and observation.protection < 15 and observation.remaining_ticks > 2 and observation.budget > 5:
                action, rationale = "fortify", "Build a modest buffer without exhausting the shared reserve."
        status = "critical" if observation.health < 45 else "stable"
        return Decision(action, "all" if observation.communication else None,
                        f"{observation.subsystem}: {status}, health={observation.health}; plan={action}" if observation.communication else "",
                        target, rationale)
