# 🚀 Deploy Red Hat vLLM on AKS with A10 GPU

This guide walks you through deploying **Llama-3.1-8B-Instruct** with **Red Hat’s vLLM** on an **AKS cluster** using **A10 GPU** nodes.

---

## 0) Prereqs

**CLI:** Azure CLI (`az`), `kubectl`, `helm`  
**Azure:** Owner/Contributor on the target subscription  
**Hugging Face token:** read access token in hand  
**(Optional)** Podman login to `registry.redhat.io` if your environment requires authenticated pulls

```bash
# Login
az login
az account set --subscription "<SUBSCRIPTION_ID>"
```

---

## 1) Create the AKS Cluster

Create a resource group and a basic AKS cluster with a system node pool (CPU).

```bash
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
```

---

## 2) Add an A10 GPU Node Pool

Pick a GPU size that your region/subscription supports (A10 family recommended). Example:

```bash
# Add GPU pool (A10)
az aks nodepool add \
  --resource-group "$RG" \
  --cluster-name "$CLUSTER" \
  --name gpua10 \
  --node-vm-size Standard_NV24ads_A10_v5 \
  --node-count 1 \
  --labels gpu=true \
  --node-taints sku=gpu:NoSchedule
```

If you get a “VMSizeNotSupported” error, choose a size from the available list or pick a different region.

```bash
kubectl get nodes -L agentpool,gpu -o wide
```

---

## 3) Install the NVIDIA GPU Operator

This installs the NVIDIA driver, device plugin, container toolkit, DCGM exporter, etc., on the GPU node(s).

```bash
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update

helm upgrade --install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator --create-namespace
```

Watch for ready pods:

```bash
kubectl -n gpu-operator get pods -o wide
```

Confirm the GPU resource is visible on the GPU node:

```bash
kubectl describe node -l gpu=true | grep -i "nvidia.com/gpu" -n || echo "GPU resource not visible yet"
```

You should eventually see `Allocatable: nvidia.com/gpu: 1`.

---

## 4) Create the vLLM Namespace & Secrets

```bash
kubectl create namespace vllm

kubectl -n vllm create secret generic hf \
  --from-literal=HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -
```

(Optional) Red Hat registry pull secret (if required in your environment)

```bash
# Ensure you're logged in with podman first:
# podman login registry.redhat.io

kubectl -n vllm create secret generic rh-pull \
  --from-file=.dockerconfigjson="$XDG_RUNTIME_DIR/containers/auth.json" \
  --type=kubernetes.io/dockerconfigjson
```

The deployment manifest below has `imagePullSecrets` commented out. Uncomment it if you created `rh-pull`.

---

## 5) Deploy Red Hat vLLM with Llama-3.1-8B-Instruct

Apply the manifest that includes Namespace, PVC, Deployment, and Service:

```bash
kubectl apply -f vllm-redhat-llama8b.yaml
```

Check status and logs:

```bash
kubectl -n vllm get pods -o wide
kubectl -n vllm logs -f deploy/vllm-llama8b -c vllm
kubectl -n vllm get svc vllm-llama8b
```

Grab the `EXTERNAL-IP` of the Service.

---

## 6) Test the Endpoint

List models:

```bash
curl http://<LOADBALANCER_IP>:8000/v1/models
```

Stream a chat completion:

```bash
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
```

Non-streaming example:

```bash
curl http://<LOADBALANCER_IP>:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "RedHatAI/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "Give me three bullet points about AKS GPU scheduling."}
    ],
    "max_tokens": 150
  }'
```

---

## 7) Tuning & Notes

- **GPU fit on A10**:
  - If you see memory errors, reduce:
    - `VLLM_WORKER_GPU_MEMORY_UTILIZATION` (e.g., 0.82)
    - `--max-model-len` (e.g., 4096)

- **Persistence**:
  - The `vllm-cache` PVC helps speed up model loading

- **Scaling**:
  - Use `--tensor-parallel-size` for multi-GPU
  - Add HPA, PDB, Ingress, TLS for production

- **Security**:
  - Use Kubernetes Secrets for tokens
  - Never commit secrets to git

---

## 8) Clean Up

```bash
kubectl delete -f vllm-redhat-llama8b.yaml
kubectl delete ns vllm
helm uninstall gpu-operator -n gpu-operator
az aks nodepool delete -g "$RG" --cluster-name "$CLUSTER" -n gpua10
```

---

## Files in This Repo

- `vllm-redhat-llama8b.yaml` — Namespace, PVC, Deployment, Service (LoadBalancer)  
- `*.tf` — Optional Terraform files for AKS creation

---

✅ You now have a fully functioning Llama-3.1-8B inference server on AKS, powered by NVIDIA A10 GPUs and exposed via an OpenAI-compatible API.
