0) Prereqs

CLI: Azure CLI (az), kubectl, helm

Azure: Owner/Contributor on the target subscription

Hugging Face token: read access token in hand

(Optional) Podman login to registry.redhat.io if your environment requires authenticated pulls

Login:

az login
az account set --subscription "<SUBSCRIPTION_ID>"

1) Create the AKS Cluster

Create a resource group and a basic AKS cluster with a system node pool (CPU). You can use your Terraform, but here’s the Azure CLI equivalent.

# Variables
LOCATION="eastus"
RG="ben-aks-rg-settled-treefrog"
CLUSTER="ben-aks-aks"

# Resource group
az group create -n "$RG" -l "$LOCATION"

# AKS (system pool: default size)
az aks create \
  -g "$RG" -n "$CLUSTER" \
  --location "$LOCATION" \
  --node-count 1 \
  --enable-managed-identity \
  --network-plugin azure \
  --generate-ssh-keys

# Kubeconfig
az aks get-credentials -g "$RG" -n "$CLUSTER"
kubectl get nodes -o wide

2) Add an A10 GPU Node Pool

Pick a GPU size that your region/subscription supports (A10 family recommended). Example:

# Add GPU pool (A10)
az aks nodepool add \
  --resource-group "$RG" \
  --cluster-name "$CLUSTER" \
  --name gpua10 \
  --node-vm-size Standard_NV24ads_A10_v5 \
  --node-count 1 \
  --labels gpu=true \
  --node-taints sku=gpu:NoSchedule


If you get a “VMSizeNotSupported” error, choose a size from the “available sizes” list in the error message (or pick a different region).

Verify the new GPU node shows up and is Ready:

kubectl get nodes -L agentpool,gpu -o wide

3) Install the NVIDIA GPU Operator

This installs the NVIDIA driver, device plugin, container toolkit, DCGM exporter, etc., on the GPU node(s).

helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update

helm upgrade --install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator --create-namespace


Watch for ready pods:

kubectl -n gpu-operator get pods -o wide


Confirm the GPU resource is visible on the GPU node:

kubectl describe node -l gpu=true | grep -i "nvidia.com/gpu" -n || echo "GPU resource not visible yet"


You should eventually see Allocatable like nvidia.com/gpu: 1.

4) Create the vLLM Namespace & Secrets

Create the app namespace and your Hugging Face token secret:

kubectl create namespace vllm

kubectl -n vllm create secret generic hf \
  --from-literal=HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -

(Optional) Red Hat registry pull secret (if required in your environment)

If your nodes need auth for registry.redhat.io, create a pull secret from your Podman auth:

# Ensure you're logged in with podman first:
# podman login registry.redhat.io

kubectl -n vllm create secret generic rh-pull \
  --from-file=.dockerconfigjson="$XDG_RUNTIME_DIR/containers/auth.json" \
  --type=kubernetes.io/dockerconfigjson


The deployment manifest below has imagePullSecrets commented out. Uncomment it if you created rh-pull.

5) Deploy Red Hat vLLM with Llama-3.1-8B-Instruct

Apply the manifest that includes Namespace, PVC, Deployment, Service (yours is named vllm-redhat-llama8b.yaml). It:

Uses image registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.2.1

Mounts a 50Gi PVC for cache (vllm-cache) so the model isn’t re-downloaded

Sets VLLM_WORKER_GPU_MEMORY_UTILIZATION=0.85 to fit on a single A10

Schedules on the GPU node pool (nodeSelector + taint tolerance)

Exposes an OpenAI-compatible endpoint on port 8000 via a LoadBalancer Service

kubectl apply -f vllm-redhat-llama8b.yaml


Check status and logs:

kubectl -n vllm get pods -o wide
kubectl -n vllm logs -f deploy/vllm-llama8b -c vllm
kubectl -n vllm get svc vllm-llama8b


Grab the EXTERNAL-IP of the Service (e.g., 57.152.10.249).

6) Test the Endpoint

List models:

curl http://<LOADBALANCER_IP>:8000/v1/models


Stream a chat completion:

curl -N http://<LOADBALANCER_IP>:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "RedHatAI/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "Write a short poem about Kubernetes and GPUs."}
    ],
    "max_tokens": 100,
    "stream": true
  }'


Non-streaming example:

curl http://<LOADBALANCER_IP>:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "RedHatAI/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "Give me three bullet points about AKS GPU scheduling."}
    ],
    "max_tokens": 150
  }'

7) Tuning & Notes

GPU fit on A10: If you see “Free memory on device … less than desired GPU memory utilization” errors, you can:

lower VLLM_WORKER_GPU_MEMORY_UTILIZATION (e.g., 0.82)

reduce --max-model-len (e.g., 4096)

Persistence: The vllm-cache PVC speeds up restarts by caching model files.

Scaling: For multi-GPU nodes, bump --tensor-parallel-size. For production, add HPA, PDBs, and an Ingress + TLS.

Security: Store tokens in secrets (as shown). Don’t commit tokens to git.

8) Clean Up
kubectl delete -f vllm-redhat-llama8b.yaml
kubectl delete ns vllm
helm uninstall gpu-operator -n gpu-operator
az aks nodepool delete -g "$RG" --cluster-name "$CLUSTER" -n gpua10

Files in this repo

vllm-redhat-llama8b.yaml — Namespace, PVC, Deployment (vLLM), Service (LoadBalancer)

Terraform (*.tf) — if you prefer IaC for AKS creation

That’s it! You now have a fully functioning Llama-3.1-8B inference server on AKS, powered by NVIDIA A10 GPUs and exposed via an OpenAI-compatible API.
