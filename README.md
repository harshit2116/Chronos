# Chronos

A Python crisis simulator where specialized agents manage subsystems, exchange messages, and respond to evolving incidents.

- Four scenarios: spacecraft, cyberattack, infrastructure, and supply chain.
- Gemini agents or an offline rule baseline.
- Dashboard with telemetry, agent inspection, saved replays, and policy comparisons.
- Docker, GitHub Actions, and Kubernetes deployment configuration.

## Run

Requires Python 3.11+. No third-party runtime dependencies.

```sh
python -m chronos.web
```

Open http://127.0.0.1:8000. For Gemini, copy `.env.example` to `.env`, add your API key, and restart. Without a key, the app uses offline agents.

```sh
python -m chronos --scenario spacecraft --mode baseline
```

See [deployment](docs/deployment.md) for Docker, CI/CD, and Kubernetes setup, and [architecture](docs/architecture.md) for implementation details.

Designed for a single local user. Kubernetes configuration is included; cluster deployment is not yet verified. Gemini requests may time out, which pauses the run. Secrets and generated traces are excluded from Git.
