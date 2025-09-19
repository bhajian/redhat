# 🚀 Deploy Red Hat vLLM on AKS with A10 GPU

This guide walks you through deploying **Llama-3.1-8B-Instruct** with **Red Hat’s vLLM** on an **AKS cluster** using **A10 GPU** nodes.

---

## 0️⃣ Prerequisites

- **CLI Tools**:  
  - `az` (Azure CLI)  
  - `kubectl`  
  - `helm`  
  - (Optional) `podman` for Red Hat registry auth  

- **Azure**: Owner/Contributor access to the subscription  
- **Hugging Face Token**: Must have `read` access  
- (Optional) Red Hat registry access via `podman login registry.redhat.io`  

```bash
# Login to Azure
az login
az account set --subscription "<SUBSCRIPTION_ID>"


1️⃣ Create the AKS Cluster
# Variables
LOCATION="eastus"
RG="ben-aks-rg-settled-treefrog"
CLUSTER="ben-aks-aks"

# Resource group
az group create -n "$RG" -l "$LOCATION"

# AKS Cluster
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

2️⃣ Add an A10 GPU Node Pool
az aks nodepool add \
  --resource-group "$RG" \
  --cluster-name "$CLUSTER" \
  --name gpua10 \
  --node-vm-size Standard_NV24ads_A10_v5 \
  --node-count 1 \
  --labels gpu=true \
  --node-taints sku=gpu:NoSchedule


⚠️ If you get VMSizeNotSupported, switch to a supported size or region.

kubectl get nodes -L agentpool,gpu -o wide

3️⃣ Install the NVIDIA GPU Operator
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update

helm upgrade --install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator --create-namespace

# Check pod readiness
kubectl -n gpu-operator get pods -o wide

# Confirm GPU visibility
kubectl describe node -l gpu=true | grep -i "nvidia.com/gpu" -n || echo "GPU resource not visible yet"

4️⃣ Create Namespace & Hugging Face Secret
kubectl create namespace vllm

kubectl -n vllm create secret generic hf \
  --from-literal=HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -


(Optional) If required, add pull secret for registry.redhat.io:

# Ensure you're logged in with podman
# podman login registry.redhat.io

kubectl -n vllm create secret generic rh-pull \
  --from-file=.dockerconfigjson="$XDG_RUNTIME_DIR/containers/auth.json" \
  --type=kubernetes.io/dockerconfigjson

5️⃣ Deploy vLLM with Llama-3.1-8B-Instruct
kubectl apply -f vllm-redhat-llama8b.yaml


Includes:

Namespace, PVC (50Gi), Deployment

GPU scheduling (nodeSelector + tolerations)

LoadBalancer exposing OpenAI-compatible API

Check logs and service:

kubectl -n vllm get pods -o wide
kubectl -n vllm logs -f deploy/vllm-llama8b -c vllm
kubectl -n vllm get svc vllm-llama8b

6️⃣ Test the Inference API

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

7️⃣ Tuning & Notes

🔧 GPU Fit on A10:

Lower VLLM_WORKER_GPU_MEMORY_UTILIZATION (e.g. 0.82)

Reduce --max-model-len (e.g. 4096)

💾 Persistence:
Uses vllm-cache PVC to avoid model re-downloads

📈 Scaling:
Use --tensor-parallel-size for multi-GPU
Add HPA, PDBs, Ingress + TLS for production

🔐 Security:
Store secrets in Secrets, never commit tokens

8️⃣ Clean Up
kubectl delete -f vllm-redhat-llama8b.yaml
kubectl delete ns vllm
helm uninstall gpu-operator -n gpu-operator
az aks nodepool delete -g "$RG" --cluster-name "$CLUSTER" -n gpua10

📂 Files in This Repo

vllm-redhat-llama8b.yaml — Namespace, PVC, Deployment, LoadBalancer Service

*.tf — Terraform configs for AKS (optional)

✅ You now have a fully working Llama-3.1-8B inference server on AKS using A10 GPUs with an OpenAI-compatible API powered by Red Hat’s vLLM.


Let me know if you'd like this saved as a downloadable `.md` file or converted into a shareable README layout!
