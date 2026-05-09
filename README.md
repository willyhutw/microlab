# microlab

ArgoCD application manifests for a 4-node Raspberry Pi 5 Kubernetes cluster (micro cluster).

## Related Repositories

| Repo | Description |
|------|-------------|
| [argocd-bootstrap](https://github.com/willyhutw/argocd-bootstrap) | k3s + ArgoCD bootstrap for the management cluster |
| [microlab-bootstrap](https://github.com/willyhutw/microlab-bootstrap) | kubeadm bootstrap for the micro cluster (Cilium, cert-manager, ArgoCD registration) |
| [cloudflare-tofu](https://github.com/willyhutw/cloudflare-tofu) | DNS management via OpenTofu + Cloudflare |

## Cluster

- **4 nodes:** 1 control plane + 3 worker nodes (Raspberry Pi 5)
- **CNI:** Cilium 1.19.3 with L2 announcements and kube-proxy replacement
- **Service mesh:** Istio 1.28.4
- **Control plane:** `192.168.12.21:6443`
- **LB IP range:** `192.168.12.91–99`

| Node | Hostname | Label | Role |
|------|----------|-------|------|
| 1 | k8s-micro-node-1 | — | worker |
| 2 | k8s-micro-node-2 | — | worker |
| 3 | k8s-micro-node-3 | `micro/role=monitoring` | worker — monitoring stack (Prometheus, Grafana, Loki) |

## Apps

### Internal

| App | Chart | Version | Namespace | Description |
|-----|-------|---------|-----------|-------------|
| base | — | — | kube-system | `local-storage` StorageClass + Cilium LB IP pools |
| istio-base | istio/base | 1.28.4 | istio-system | Istio CRDs |
| istiod | istio/istiod | 1.28.4 | istio-system | Istio control plane (JSON access logging) |
| istio-igw-internal | istio/gateway | 1.28.4 | istio-system | Internal ingress gateway (`192.168.12.96`) |
| istio-igw-external | istio/gateway | 1.28.4 | istio-system | External ingress gateway (`192.168.12.91`) |
| data-pipeline/entry | — | — | monitoring | Syslog receiver from pfSense (`192.168.12.97:5140 UDP`) |
| hubble | cilium/cilium | 1.19.3 | kube-system | Cilium Hubble relay + UI |
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
│   │   └── prometheus-snmp-exporter/    # SNMP exporter Helm chart
│   │       └── tools/                   # generator.yaml for SNMP MIB generation (local tool)
│   └── external/
│       ├── apps/                        # ArgoCD Application manifests (external)
│       └── willyhutw/                   # Blog deployment manifests
```

## Node Labels

Apply these labels before running ArgoCD apps:

```bash
kubectl label node k8s-micro-node-3 micro/role=monitoring
```

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
| 1 | hubble, kiali-operator, kube-prometheus-stack, loki, prometheus-snmp-exporter |
| 2 | data-pipeline |

> Each app directory follows the Helm wrapper chart pattern: a local `Chart.yaml` declares a single upstream dependency, and values are nested under the dependency chart name.
