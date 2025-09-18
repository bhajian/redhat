#!/bin/bash
set -euo pipefail

# === REQUIRED ENV VARIABLES ===
: "${AWS_ACCESS_KEY_ID:?Must set AWS_ACCESS_KEY_ID}"
: "${AWS_SECRET_ACCESS_KEY:?Must set AWS_SECRET_ACCESS_KEY}"
: "${BASE_DOMAIN:?Must set BASE_DOMAIN (e.g. dev.example.com)}"
: "${CLUSTER_NAME:?Must set CLUSTER_NAME (e.g. ocp-demo)}"
: "${AWS_REGION:?Must set AWS_REGION (e.g. us-east-1)}"
: "${PULL_SECRET_FILE:=./pull-secret.json}"

# === FIXED VALUES ===
VPC_ID="vpc-0753350314810c569"
PUBLIC_SUBNETS=("subnet-0327dd8f1756fab0e" "subnet-04ca3d42999121ed3")
PRIVATE_SUBNETS=("subnet-082e6fad07a024693" "subnet-09ee1c8d07c05cec7")
INSTALL_DIR="${HOME}/openshift-install-${CLUSTER_NAME}"

# === VALIDATE PULL SECRET ===
if [ ! -s "$PULL_SECRET_FILE" ]; then
  echo "❌ ERROR: $PULL_SECRET_FILE does not exist or is empty."
  exit 1
fi

if ! jq . "$PULL_SECRET_FILE" >/dev/null 2>&1; then
  echo "❌ ERROR: $PULL_SECRET_FILE contains invalid JSON."
  exit 1
fi

ESCAPED_PULL_SECRET=$(jq -c . "$PULL_SECRET_FILE")

# === SETUP INSTALL DIR ===
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# === DOWNLOAD INSTALLER ===
echo "📥 Downloading OpenShift Installer..."
curl -sSL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-install-linux.tar.gz | tar -xz
chmod +x openshift-install
sudo mv openshift-install /usr/local/bin/

# === DOWNLOAD OC CLI ===
echo "📥 Downloading OC CLI..."
curl -sSL https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/stable/openshift-client-linux.tar.gz | tar -xz
chmod +x oc kubectl
sudo mv oc kubectl /usr/local/bin/

# === GENERATE SSH KEY IF MISSING ===
if [ ! -f ~/.ssh/id_rsa ]; then
  echo "🔐 Generating SSH key..."
  ssh-keygen -q -t rsa -N "" -f ~/.ssh/id_rsa
fi
SSH_PUB_KEY=$(<~/.ssh/id_rsa.pub)

# === GENERATE install-config.yaml ===
echo "📝 Generating install-config.yaml..."

cat > install-config.yaml <<EOF
apiVersion: v1
baseDomain: ${BASE_DOMAIN}
metadata:
  name: ${CLUSTER_NAME}
compute:
- name: worker
  replicas: 3
  platform:
    aws:
      type: m5.xlarge
controlPlane:
  name: master
  replicas: 3
  platform:
    aws:
      type: m5.xlarge
platform:
  aws:
    region: ${AWS_REGION}
    vpc: ${VPC_ID}
    subnets:
$(for subnet in "${PUBLIC_SUBNETS[@]}" "${PRIVATE_SUBNETS[@]}"; do echo "      - $subnet"; done)
pullSecret: '${ESCAPED_PULL_SECRET}'
sshKey: |
  ${SSH_PUB_KEY}
EOF

# === START INSTALL ===
echo "🚀 Starting OpenShift cluster installation..."
openshift-install create cluster --dir "$INSTALL_DIR" --log-level=info


