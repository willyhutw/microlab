# microlab

ArgoCD application manifests for a 4-node Raspberry Pi 5 Kubernetes cluster (micro cluster).

## Related Repositories

| Repo | Description |
|------|-------------|
| [argocd-bootstrap](https://github.com/willyhutw/argocd-bootstrap) | k3s + ArgoCD bootstrap for the local management cluster |
| [microlab-bootstrap](https://github.com/willyhutw/microlab-bootstrap) | k3s bootstrap for the micro cluster (Cilium, cert-manager, ArgoCD registration) |
| [cloudflare-tofu](https://github.com/willyhutw/cloudflare-tofu) | DNS management via OpenTofu + Cloudflare |

## Cluster

- **4 nodes:** 1 control plane + 3 worker nodes (Raspberry Pi 5)
- **CNI:** Cilium 1.17.4 with L2 announcements and kube-proxy replacement
- **Service mesh:** Istio 1.28.4
- **Control plane:** `192.168.12.21:6443`
- **LB IP range:** `192.168.12.91–99`

| Node | Hostname | Role |
|------|----------|------|
| 1 | k8s-micro-node-1 | worker — data pipeline, SNMP exporter |
| 2 | k8s-micro-node-2 | worker |
| 3 | k8s-micro-node-3 | worker — monitoring stack (Prometheus, Grafana, Loki) |

## Apps

### Internal

| App | Chart | Version | Namespace | Description |
|-----|-------|---------|-----------|-------------|
| base | — | — | kube-system | `local-storage` StorageClass + Cilium LB IP pools |
| hubble | cilium/cilium | 1.17.4 | kube-system | Cilium Hubble relay + UI |
| istio-base | istio/base | 1.28.4 | istio-system | Istio CRDs |
| istiod | istio/istiod | 1.28.4 | istio-system | Istio control plane (JSON access logging) |
| istio-igw-internal | istio/gateway | 1.28.4 | istio-system | Internal ingress gateway (`192.168.12.96`) |
| istio-igw-external | istio/gateway | 1.28.4 | istio-system | External ingress gateway (`192.168.12.91`) |
| kiali-operator | kiali/kiali-operator | 2.12.0 | istio-system | Service mesh observability |
| kube-prometheus-stack | prometheus-community/kube-prometheus-stack | 82.1.1 | monitoring | Prometheus + Grafana + AlertManager |
| loki | grafana/loki | 6.29.0 | monitoring | Log aggregation (single binary) |
| prometheus-snmp-exporter | prometheus-community/prometheus-snmp-exporter | 9.3.0 | monitoring | SNMP metrics for pfSense |
| data-pipeline | — | — | monitoring | Fluent Bit log pipeline (entry → filter → Loki) |

### External

| App | Namespace | Description |
|-----|-----------|-------------|
| willyhutw | willyhutw | Personal blog ([willyhu.tw](https://willyhu.tw)) |

## Project Structure

```
.
├── .ci/
│   └── create.sh                        # Upsert ArgoCD apps from a directory
├── argocd/
│   ├── internal/
│   │   ├── apps/                        # ArgoCD Application manifests (internal)
│   │   ├── base/                        # StorageClass + Cilium IP pool manifests
│   │   ├── data-pipeline/               # Fluent Bit pipeline stages
│   │   │   ├── entry/                   # Syslog receiver (UDP 5140)
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
│   │   └── prometheus-snmp-exporter/    # SNMP exporter Helm chart
│   └── external/
│       ├── apps/                        # ArgoCD Application manifests (external)
│       └── willyhutw/                   # Blog deployment manifests
```

## Usage

All apps are managed by ArgoCD with automated sync, self-heal, and prune enabled. To provision or update ArgoCD Application objects:

```bash
# Create/upsert all internal apps
.ci/create.sh argocd/internal/apps

# Create/upsert all external apps
.ci/create.sh argocd/external/apps
```

> Each app directory follows the Helm wrapper chart pattern: a local `Chart.yaml` declares a single upstream dependency, and values are nested under the dependency chart name.
