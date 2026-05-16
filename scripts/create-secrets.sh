#!/bin/bash
# One-time script to create all K8s secrets for PostgreSQL, Langfuse, and Grafana.
# Run ONCE before deploying. Save the printed values to your password manager.
set -euo pipefail

POSTGRES_ADMIN_PW=$(openssl rand -base64 16)
LANGFUSE_PW=$(openssl rand -base64 16)
GRAFANA_PW=$(openssl rand -base64 16)
NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_SALT=$(openssl rand -hex 16)
ENCRYPTION_KEY=$(openssl rand -hex 32)

echo "Creating namespaces..."
kubectl create namespace data --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ai --dry-run=client -o yaml | kubectl apply -f -

echo "Creating postgresql-credentials in data namespace..."
kubectl create secret generic postgresql-credentials -n data \
  --from-literal=postgres-password="${POSTGRES_ADMIN_PW}" \
  --from-literal=password="${LANGFUSE_PW}" \
  --from-literal=grafana-password="${GRAFANA_PW}"

echo "Creating langfuse-secrets in ai namespace..."
kubectl create secret generic langfuse-secrets -n ai \
  --from-literal=nextauth-secret="${NEXTAUTH_SECRET}" \
  --from-literal=salt="${LANGFUSE_SALT}" \
  --from-literal=encryption-key="${ENCRYPTION_KEY}" \
  --from-literal=database-url="postgresql://langfuse:${LANGFUSE_PW}@postgresql.data.svc.cluster.local:5432/langfuse"

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
echo "NEXTAUTH_SECRET   : ${NEXTAUTH_SECRET}"
echo "LANGFUSE_SALT     : ${LANGFUSE_SALT}"
echo "ENCRYPTION_KEY    : ${ENCRYPTION_KEY}"
echo "=========================================="
