# CI/CD and Kubernetes

The checked-in pipeline uses GitHub Actions, GHCR, and Kubernetes. It is ready to configure; it has not been connected to a repository or deployed to a cluster.

## Pipeline

1. Pull requests and pushes to `main` check Python syntax and run an offline simulation on 3.11, 3.12 and 3.13, then validate JavaScript syntax. No Gemini credentials are needed. The local unit-test suite is excluded from this repository.
2. Build a non-root container and smoke-test its HTTP endpoints. Render the Kubernetes manifests with Kustomize.
3. On `main`, publish the tested image to `ghcr.io/<owner>/<repository>:<commit>` using `GITHUB_TOKEN`.
4. If repository variable `ENABLE_K8S_DEPLOY` is `true`, deploy the published digest to the `staging` environment, then wait for rollout completion. Deployment jobs are serialized.

Configure the GitHub `staging` environment and its protection rules. Set environment secret `KUBE_CONFIG` to a kubeconfig whose API endpoint is reachable by the runner. Grant only the permissions needed for these manifests; do not use a personal cluster-admin credential. The manifests include namespace creation, so either provision that namespace separately and adapt the pipeline, or give the deployment identity that specific capability. Use a self-hosted runner if the cluster API is private. Match the workflow's kubectl version to your cluster's supported version skew.

GHCR packages may be private. Grant your cluster pull access using a registry Secret and add `imagePullSecrets` to the Deployment, or explicitly configure package visibility as appropriate. The Gemini key is a cluster Secret, not a build argument, image layer, or workflow variable.

## Local container

```powershell
docker build -t chronos:local .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v chronos-data:/data chronos:local
```

Omit `--env-file .env` for offline mode. Docker's named volume preserves traces. The Docker build context allowlist excludes `.env`, runs, Git history, and tests.

## Local Kubernetes

Select the intended context first. These commands change that cluster. A default StorageClass must be available for the 1 GiB PVC.

```powershell
kubectl config current-context
docker build -t chronos:local .
kubectl apply -k deploy/k8s
kubectl -n chronos rollout status deployment/chronos --timeout=180s
kubectl -n chronos port-forward service/chronos 8000:8000
```

Docker Desktop Kubernetes can use the local Docker image. With kind, run `kind load docker-image chronos:local`; other clusters need a reachable registry and an image override in `kustomization.yaml`. Open http://127.0.0.1:8000 after port-forwarding. Stop any existing local server occupying port 8000 first.

The Secret is optional: without it the app starts offline. To enable Gemini, create it from your local ignored configuration file, then restart the Deployment:

```powershell
kubectl -n chronos create secret generic chronos-gemini --from-env-file=.env
kubectl -n chronos rollout restart deployment/chronos
```

Do not commit a populated Secret YAML. Existing Secrets should be updated through your cluster's secret-management process. Environment changes take effect on pod restart.

## Runtime and storage constraints

- One replica and `Recreate` deployment strategy: active runs and comparison state live in process memory. Multiple replicas would expose inconsistent sessions. Updates cause downtime and interrupt active runs.
- The PVC preserves completed-turn traces, not resumable live simulations. Finish or pause experiments before rollout; incomplete runs remain available as historical traces.
- The container uses UID/GID 10001, a read-only root filesystem, dropped capabilities, resource limits, and no service-account token mount.
- `/healthz` reports HTTP process availability without calling Gemini or disclosing simulation data. It does not assert provider connectivity or storage health.
- The Service is ClusterIP, with no Ingress or public load balancer. Application Host/Origin checks remain limited to localhost port 8000, matching port-forward access. The app does not provide user authentication.
- Public deployment requires authentication, explicit trusted host/origin configuration, a production HTTP server, and a decision about multi-user state isolation. Horizontal scaling additionally requires moving active state and job ownership out of process memory.

## Rollback

```powershell
kubectl -n chronos rollout history deployment/chronos
kubectl -n chronos rollout undo deployment/chronos
kubectl -n chronos rollout status deployment/chronos --timeout=180s
```

Rollback changes the image/configuration; it does not restore an interrupted live run. The pipeline reports failed rollouts instead of silently hiding them with automatic rollback.

References: [GitHub image publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images) and [Kubernetes deployment strategies](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
