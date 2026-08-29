#!/usr/bin/env bash
# One-shot deploy: Firestore + Cloud Run + Cloud Scheduler.
# Prereqs: gcloud CLI authenticated, project selected, billing enabled.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE=atlas
REPO=atlas
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:latest"
SCHED="${SCHED:-*/2 * * * *}"   # every 2 minutes

echo "==> Enabling APIs"
gcloud services enable run.googleapis.com firestore.googleapis.com \
  artifactregistry.googleapis.com cloudscheduler.googleapis.com

echo "==> Creating Firestore database (first run only)"
gcloud firestore databases create --location="${REGION}" 2>/dev/null || true

echo "==> Artifact Registry repo"
gcloud artifacts repositories create "${REPO}" --repository-format=docker \
  --location="${REGION}" 2>/dev/null || true

echo "==> Building & deploying ${SERVICE}"
gcloud builds submit --config cloudbuild.yaml \
  --substitutions "_REGION=${REGION},_REPO=${REPO}" --project="${PROJECT_ID}"

echo "==> Scheduler: wake Atlas every 2 minutes to drain the task queue"
gcloud scheduler jobs create http atlas-cron \
  --schedule="${SCHED}" \
  --uri="https://${SERVICE}-${PROJECT_ID}.${REGION}.run.app/cron/run" \
  --http-method=POST \
  --oidc-service-account-email="${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com" \
  2>/dev/null || true

echo "==> Done. Dashboard: https://${SERVICE}-${PROJECT_ID}.${REGION}.run.app"
