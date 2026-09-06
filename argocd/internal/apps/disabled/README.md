# Disabled apps

Application manifests parked here are **temporarily excluded** from the `internal`
app-of-apps.

The `internal` Application (`argocd/internal-apps.yaml`) syncs `argocd/internal/apps`
with a non-recursive directory source, so this subdirectory is not read and ArgoCD
prunes any child Application that was previously created from these files.

## Currently disabled

| App | Reason |
|-----|--------|
| `langfuse`, `ollama`, `open-webui`, `pipelines`, `qdrant` | `ai` namespace stack — not ready to deploy yet |
| `nvidia-device-plugin` | GPU node `k8s-micro-gpu-1` has not joined the cluster |

## Re-enable

```bash
git mv argocd/internal/apps/disabled/<app>.yaml argocd/internal/apps/
```

Commit, push, and the `internal` app picks it back up on the next sync.
