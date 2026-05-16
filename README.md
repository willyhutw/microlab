# microlab

ArgoCD application manifests for the micro cluster — 4× Raspberry Pi 5 nodes + 1× G14 GPU VM (RTX 2060 Max-Q via VFIO passthrough).

## Related Repositories

| Repo | Description |
|------|-------------|
| [argocd-bootstrap](https://github.com/willyhutw/argocd-bootstrap) | k3s + ArgoCD bootstrap for the management cluster |
| [microlab-bootstrap](https://github.com/willyhutw/microlab-bootstrap) | kubeadm bootstrap for the micro cluster (Cilium, cert-manager, ArgoCD registration) |
| [cloudflare-tofu](https://github.com/willyhutw/cloudflare-tofu) | DNS management via OpenTofu + Cloudflare |

## Cluster

- **5 nodes:** 1 control plane + 3 workers (Raspberry Pi 5) + 1 GPU worker (G14 VM)
- **CNI:** Cilium 1.19.3 with L2 announcements and kube-proxy replacement
- **Service mesh:** Istio 1.28.4
- **Control plane:** `192.168.12.21:6443`
- **LB IP range:** `192.168.12.91–99`

| Node | Hostname | Label | Role |
|------|----------|-------|------|
| 1 | k8s-micro-node-1 | — | worker |
| 2 | k8s-micro-node-2 | — | worker |
| 3 | k8s-micro-node-3 | `micro/role=monitoring` | worker — monitoring stack (Prometheus, Grafana, Loki) |
| 4 | k8s-micro-gpu-1 | `nvidia.com/gpu.present=true` | worker — GPU node (RTX 2060 Max-Q, VFIO passthrough from G14 host) |

## Apps

### Internal

| App | Chart | Version | Namespace | Description |
|-----|-------|---------|-----------|-------------|
| base | — | — | kube-system | `local-storage` StorageClass + Cilium LB IP pools |
| istio-base | istio/base | 1.28.4 | istio-system | Istio CRDs |
| istiod | istio/istiod | 1.28.4 | istio-system | Istio control plane (JSON access logging) |
| istio-igw-internal | istio/gateway | 1.28.4 | istio-system | Internal ingress gateway (`192.168.12.96`) |
| istio-igw-external | istio/gateway | 1.28.4 | istio-system | External ingress gateway (`192.168.12.91`) |
| hubble | cilium/cilium | 1.19.3 | kube-system | Cilium Hubble relay + UI |
| kiali-operator | kiali/kiali-operator | 2.12.0 | istio-system | Service mesh observability |
| kube-prometheus-stack | prometheus-community/kube-prometheus-stack | 82.1.1 | monitoring | Prometheus + Grafana (PostgreSQL backend) + AlertManager |
| loki | grafana/loki | 6.29.0 | monitoring | Log aggregation (single binary) |
| prometheus-snmp-exporter | prometheus-community/prometheus-snmp-exporter | 9.3.0 | monitoring | SNMP metrics for pfSense |
| nvidia-device-plugin | — | v0.17.0 | kube-system | NVIDIA GPU device plugin DaemonSet for GPU node |
| data-pipeline | — | — | monitoring | Fluent Bit log pipeline: syslog entry → filter → Loki |
| postgresql | bitnami/postgresql | 18.6.6 | data | Shared PostgreSQL instance (Langfuse + Grafana) |
| qdrant | — | — | ai | Vector database for RAG pipeline |
| ollama | — | latest | ai | LLM inference server (GPU node, RTX 2060 Max-Q) |
| open-webui | — | latest | ai | Chat UI — [chat.willyhu.tw](https://chat.willyhu.tw) |
| pipelines | — | main | ai | Open WebUI Pipelines — custom RAG pipeline (rag_pipeline.py) |
| langfuse | langfuse/langfuse | 1.5.30 | ai | LLM observability — [langfuse.willyhu.tw](https://langfuse.willyhu.tw) |

### External

| App | Namespace | Description |
|-----|-----------|-------------|
| willyhutw | willyhutw | Personal blog ([willyhu.tw](https://willyhu.tw)) |

## Project Structure

```
.
├── argocd/
│   ├── internal-apps.yaml               # Parent app for all internal apps (App of Apps)
│   ├── external-apps.yaml               # Parent app for all external apps (App of Apps)
│   ├── internal/
│   │   ├── apps/                        # ArgoCD Application manifests (sync-wave ordered)
│   │   ├── base/                        # StorageClass + Cilium IP pool manifests
│   │   ├── data-pipeline/               # Fluent Bit pipeline stages
│   │   │   ├── entry/                   # Syslog receiver (UDP 5140)
│   │   │   ├── tail/                    # Container log tailer (DaemonSet)
│   │   │   ├── filter/
│   │   │   │   ├── pfsense-flb/         # pfSense log filter + GeoIP enrichment
│   │   │   │   └── willyhutw/           # Blog access log filter + GeoIP enrichment
│   │   │   └── output/loki/             # Loki output
│   │   ├── hubble/                      # Cilium Hubble Helm chart + resources
│   │   ├── istio-base/                  # Istio base Helm chart
│   │   ├── istiod/                      # Istiod Helm chart
│   │   ├── istio-igw-external/          # External gateway Helm chart
│   │   ├── istio-igw-internal/          # Internal gateway Helm chart
│   │   ├── kiali-operator/              # Kiali Helm chart + resources
│   │   ├── kube-prometheus-stack/       # Monitoring stack Helm chart + resources + dashboards
│   │   ├── loki/                        # Loki Helm chart + resources
│   │   ├── prometheus-snmp-exporter/    # SNMP exporter Helm chart
│   │   │   └── tools/                   # generator.yaml for SNMP MIB generation (local tool)
│   │   ├── nvidia-device-plugin/        # NVIDIA GPU device plugin DaemonSet
│   │   ├── postgresql/                  # Shared PostgreSQL (bitnami Helm chart + PV/PVC)
│   │   ├── qdrant/                      # Qdrant vector database (Deployment + PV/PVC)
│   │   ├── ollama/                      # Ollama LLM inference (Deployment + PV/PVC + model init job)
│   │   ├── open-webui/                  # Open WebUI chat frontend (Deployment + Istio resources)
│   │   ├── pipelines/                   # Open WebUI Pipelines (Deployment + PV + ConfigMap for rag_pipeline.py)
│   │   └── langfuse/                    # Langfuse LLM observability (multi-source: Helm + Git)
│   │       ├── values.yaml              # Helm values (ClickHouse/Redis/MinIO/PostgreSQL config)
│   │       └── resources/               # Certificate, Gateway, VirtualService
│   └── external/
│       ├── apps/                        # ArgoCD Application manifests (external)
│       └── willyhutw/                   # Blog deployment manifests
├── rag-pipeline/                        # RAG pipeline source
│   ├── ingest.py                        # Batch ingest: wiki → chunk → embed → Qdrant
│   ├── query.py                         # CLI query tool for local testing
│   └── rag_pipeline.py                  # Canonical source — mirrored to pipelines/pipeline-cm.yaml for GitOps deploy
└── scripts/
    └── create-secrets.sh                # Manual secret creation (not in ArgoCD)
```

## Node Labels

Apply these labels before running ArgoCD apps:

```bash
kubectl label node k8s-micro-node-3 micro/role=monitoring
```

The GPU node label (`nvidia.com/gpu.present=true`) is applied automatically by the NVIDIA device plugin once the DaemonSet is running.

## Usage

All apps are managed via the App of Apps pattern. Bootstrap once with:

```bash
# Internal apps (Istio, monitoring, data pipeline, etc.)
argocd app create -f argocd/internal-apps.yaml --grpc-web

# External apps (blog, etc.)
argocd app create -f argocd/external-apps.yaml --grpc-web
```

ArgoCD will sync all apps automatically in sync-wave order:

| Wave | Apps |
|------|------|
| -3 | base |
| -2 | istio-base |
| -1 | istiod |
| 0 | istio-igw-internal, istio-igw-external |
| 1 | hubble, kiali-operator, kube-prometheus-stack, loki, prometheus-snmp-exporter, nvidia-device-plugin |
| 2 | data-pipeline, postgresql, qdrant, ollama |
| 3 | open-webui, pipelines, langfuse |

> Most Helm-based apps follow the wrapper chart pattern: a local `Chart.yaml` declares a single upstream dependency with values nested under the dependency name. Langfuse uses ArgoCD multi-source (Helm repo + Git values + Git raw manifests). Raw-manifest apps (ollama, open-webui, qdrant, pipelines) use plain directory sync.

## Secrets

Secrets are created manually via `scripts/create-secrets.sh` and are not managed by ArgoCD. Required secrets per namespace:

| Namespace | Secret | Used by |
|-----------|--------|---------|
| `ai` | `langfuse-secrets` | Langfuse (salt, encryption-key, nextauth-secret, db-password) |
| `ai` | `langfuse-pipeline-credentials` | Pipelines → Langfuse SDK (public-key, secret-key) |
| `monitoring` | `grafana-db-credentials` | Grafana PostgreSQL password |
