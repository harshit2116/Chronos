# Architecture

Chronos separates the world, policy, and observer interface. Only the engine mutates simulation state.

```text
Browser console -> local HTTP routes -> Controller -> Simulation
                                          |             |
                                          |             +-> private Observation -> Agent.decide()
                                          |                                       |
                                          |                 validated Decision <--+
                                          +-> RunStore -> runs/<id>.json
```

## World state and timing

`Simulation` maintains subsystem health, damage buffers, isolation duration, a shared response budget, and a priority queue of incidents. Each queue item has a turn and insertion sequence for deterministic ordering. A seed perturbs scenario damage by -6 to +6; difficulty applies a multiplier of 1, 1.25, or 1.5.

One turn consists of:

1. Apply scheduled incidents. Isolation halves incident damage, then protection absorbs damage. Emergency recovery wear bypasses both.
2. Compute all failing dependency sources from one snapshot. Each nonisolated source below 45 integrity inflicts 10 damage on each downstream subsystem. Newly damaged systems propagate on a later turn, preventing ordering-dependent cascades.
3. End immediately if any subsystem is at zero.
4. Construct each role's private observation. All observations see the same pre-action budget and world state.
5. Execute policy calls concurrently. Collect responses in role order for deterministic logging. Built-in HTTP policies have bounded timeouts and retries; arbitrary custom Python policies are trusted and must implement their own time limits.
6. Validate actions and apply them in rotating role order. Later agents can be denied if earlier actions exhaust the budget. Invalid decisions become recorded holds; there is no model-to-rule fallback.
7. Deliver outgoing messages into the next turn's inbox. Record state, service availability, observations, proposed decisions, and action outcomes.

Isolation applies immediately to service scoring and remains active through two subsequent incident phases. Service is mean subsystem integrity with a 50% penalty for isolated systems. Aggregate service averages completed turns; always compare it together with survival and turns completed.

## Policy boundary

An agent sees its own health, protection, isolation status, local incident descriptions, public static dependencies, peer role names, shared budget, the response playbook, received messages, and previous action feedback. It never receives the future event queue or direct peer health. Messages can report peer health, but are not independently verified by the policy.

Gemini policies keep four preceding decisions in memory and request structured JSON. The engine validates the result independently. The provider exposes a short operational justification; this is not hidden model reasoning. Configuration selects standard, fast, or reasoning models explicitly. The grounded-model setting is reserved and is not used: fictional closed-world simulations do not need web grounding.

The current role-specific emergency actions use distinct labels with shared recovery and wear rules. The presets differ in incidents, subsystem names, and roles, but are deliberately simplified rather than physically calibrated simulators.

## Application lifecycle

`Controller` owns one active run. A background worker advances turns while HTTP handlers serve a detached snapshot of the last committed turn. Pause stops before the next turn; an in-flight turn finishes. New runs and overlapping steps are rejected while a turn is active. Provider errors pause automatic execution and remain visible in the log.

Completed turns are written atomically to `runs/`. The archive opens them as read-only replay data. Creating a new run never erases an old saved trace. Restarting the server creates a new current run; previous traces remain replayable rather than resumable.

Experiments run the baseline, independent model policy, and communicating model policy against identical seeds and difficulty. There are one to three repetitions. Each trace is saved independently. Provider failures stop the comparison and mark incomplete results invalid. Cancellation takes effect after the in-flight turn. Results can be exported from the console; comparison summaries are held in memory, while constituent run files persist.

## Local security and deployment scope

The HTTP server binds to 127.0.0.1 and validates Host and Origin. Mutations require a custom same-origin request header; no CORS access is enabled. Only three explicit static files are served. Run identifiers are restricted to 12 hexadecimal characters. Dynamic content is escaped before rendering. A Content Security Policy disallows external scripts, embedding, and external network connections from the UI.

Credentials load only on the server from environment variables or the ignored `.env` file. Environment values take precedence. Requests send keys in the `x-goog-api-key` header, not URL parameters. Provider response bodies and arbitrary exception strings are not exposed as errors. Configurations, exports, and server snapshots exclude API keys.

This is a single-user local app, not an authenticated multi-tenant deployment. Do not expose the standard-library server publicly. To deploy, add authentication, per-user run isolation, a production application server, request limits, and managed secret storage.

## Modules

| Module | Responsibility |
| --- | --- |
| `models.py` | Observation, decision, incident and scenario contracts |
| `engine.py` | Scheduling, information boundaries, validation and state transitions |
| `actions.py` | Shared playbook and role-specific action labels |
| `scenarios.py` | Scenario presets and seeded damage variation |
| `agents.py` | Offline rule baseline |
| `gemini.py` | Gemini requests, structured decisions, usage and bounded memory |
| `service.py` | Run lifecycle, detached snapshots, archive and experiments |
| `web.py` | Local HTTP routing and static asset allowlist |
| `dashboard.html`, `style.css`, `app.js` | Operations console and replay |

Gemini REST implementation follows the [official structured-output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
