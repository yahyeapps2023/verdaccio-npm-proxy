#!/usr/bin/env bash

set -euo pipefail

USERNAME=""
NAMESPACE=""
SUDO_PASSWORD=""
R2_ACCOUNT_ID=""
S3_ACCESS_KEY_ID=""
S3_SECRET_ACCESS_KEY=""
DOCKERHUB_SERVER=""
DOCKERHUB_USERNAME=""
DOCKERHUB_TOKEN=""
R2_BUCKET=""
SECRET_TOKEN=""
PORT=""

for arg in "$@"; do
    case "$arg" in
        --username=*)
            USERNAME="${arg#*=}"
            ;;
        --namespace=*)
            NAMESPACE="${arg#*=}"
            ;;
        --sudo-password=*)
            SUDO_PASSWORD="${arg#*=}"
            ;;
        --r2-account-id=*)
            R2_ACCOUNT_ID="${arg#*=}"
            ;;
        --s3-access-key-id=*)
            S3_ACCESS_KEY_ID="${arg#*=}"
            ;;
        --s3-secret-access-key=*)
            S3_SECRET_ACCESS_KEY="${arg#*=}"
            ;;
        --dockerhub-server=*)
            DOCKERHUB_SERVER="${arg#*=}"
            ;;
        --dockerhub-username=*)
            DOCKERHUB_USERNAME="${arg#*=}"
            ;;
        --dockerhub-token=*)
            DOCKERHUB_TOKEN="${arg#*=}"
            ;;
        --r2-bucket=*)
            R2_BUCKET="${arg#*=}"
            ;;
        --secret-token=*)
            SECRET_TOKEN="${arg#*=}"
            ;;
        --port=*)
            PORT="${arg#*=}"
            ;;
    esac
done

mkdir -p ~/.config/rclone

cat > ~/.config/rclone/verdaccio.env <<EOF
R2_ACCOUNT_ID=$R2_ACCOUNT_ID
S3_ACCESS_KEY_ID=$S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY=$S3_SECRET_ACCESS_KEY
EOF

chmod 600 ~/.config/rclone/verdaccio.env

cat > ~/.config/rclone/rclone.conf <<'EOF'
[r2]
type = s3
provider = Cloudflare
endpoint = https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com
access_key_id = ${S3_ACCESS_KEY_ID}
secret_access_key = ${S3_SECRET_ACCESS_KEY}
acl = private
no_check_bucket = true
EOF

chmod 600 ~/.config/rclone/rclone.conf

chmod +x /tmp/setup_Rclone.sh

echo "$SUDO_PASSWORD" | sudo -S bash \
    /tmp/setup_Rclone.sh \
    --username="$USERNAME"

kubectl create namespace "$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry dockerhub-secret \
    --namespace="$NAMESPACE" \
    --docker-server="$DOCKERHUB_SERVER" \
    --docker-username="$DOCKERHUB_USERNAME" \
    --docker-password="$DOCKERHUB_TOKEN" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic verdaccio-secrets \
    --namespace="$NAMESPACE" \
    --from-literal=R2_BUCKET="$R2_BUCKET" \
    --from-literal=SECRET_TOKEN="$SECRET_TOKEN" \
    --from-literal=S3_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY" \
    --from-literal=S3_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID" \
    --from-literal=R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com" \
    --from-literal=PORT="$PORT" \
    --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f /tmp/deployment.yml
