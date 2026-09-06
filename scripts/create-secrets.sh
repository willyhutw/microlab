#!/bin/bash
# One-time script to create K8s secrets for PostgreSQL and Grafana.
# Run ONCE before deploying. Save the printed values to your password manager.
#
# NOTE: the langfuse/ai secrets are omitted for now (those apps are parked in
# argocd/internal/apps/disabled/). PostgreSQL still provisions the `langfuse`
# user/database so it's ready when langfuse comes back.
set -euo pipefail

POSTGRES_ADMIN_PW=$(openssl rand -base64 16)
LANGFUSE_PW=$(openssl rand -base64 16)
GRAFANA_PW=$(openssl rand -base64 16)

echo "Creating namespaces..."
kubectl create namespace data --dry-run=client -o yaml | kubectl apply -f -

echo "Creating postgresql-credentials in data namespace..."
kubectl create secret generic postgresql-credentials -n data \
  --from-literal=postgres-password="${POSTGRES_ADMIN_PW}" \
  --from-literal=password="${LANGFUSE_PW}" \
  --from-literal=grafana-password="${GRAFANA_PW}"

echo "Creating grafana-db-credentials in monitoring namespace..."
kubectl create secret generic grafana-db-credentials -n monitoring \
  --from-literal=GF_DATABASE_PASSWORD="${GRAFANA_PW}"

echo ""
echo "=========================================="
echo "  SAVE THESE TO YOUR PASSWORD MANAGER"
echo "=========================================="
echo "POSTGRES_ADMIN_PW : ${POSTGRES_ADMIN_PW}"
echo "LANGFUSE_PW       : ${LANGFUSE_PW}"
echo "GRAFANA_PW        : ${GRAFANA_PW}"
echo "=========================================="
