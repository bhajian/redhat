
# 🚀 Deploy Red Hat vLLM on AKS with A10 GPU (Terraform + Helm)

This guide walks you through provisioning an **AKS cluster** using **Terraform** on a fresh VM, configuring **A10 GPU nodes**, installing **Red Hat’s vLLM**, and exposing it via an **OpenAI-compatible API**.

---

## 0) Prerequisites

### Total Regional vCPUs required

Quota Name: Total Regional vCPUs
Region: e.g. eastus
👉 Request at least 100–150 vCPUs to allow for future scale.

| Purpose                                                | Estimate       |
| ------------------------------------------------------ | -------------- |
| 1x system node (Standard\_DS2\_v2)                     | 2 vCPUs        |
| 3x AKS Worker node (Standard\_DS2\_v2)                 | 48 vCPUs       |
| 1x GPU node (Standard\_NV24ads\_A10\_v5)               | 24 vCPUs       |
| **Buffer (Terraform preview/init, autoscaling, etc.)** | 20–50 vCPUs    |
| **Total Recommended**                                  | **≥100 vCPUs** |



From a fresh Linux VM (Ubuntu/RHEL):

```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install kubectl
az aks install-cli

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install Terraform
sudo apt-get update && sudo apt-get install -y gnupg curl software-properties-common
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform -y
```

Login to Azure:

```bash
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"
```

---

## 1) Run Terraform to Create AKS

Assuming you have the following files from this repo:

- `providers.tf`, `main.tf`, `aks.tf`, `identity.tf`, `networking.tf`, `bastion.tf`, `variables.tf`, `outputs.tf`

```bash
# Initialize and apply Terraform
terraform init
terraform apply
```

When prompted, type `yes`.

---

## 2) Connect kubectl to the AKS Cluster

```bash
RG="ben-aks-rg-settled-treefrog"
CLUSTER="ben-aks-aks"

az aks get-credentials -g "$RG" -n "$CLUSTER"
kubectl get nodes -o wide
```

---

## 3) Add an A10 GPU Node Pool

```bash
az aks nodepool add   --resource-group "$RG"   --cluster-name "$CLUSTER"   --name gpua10   --node-vm-size Standard_NV24ads_A10_v5   --node-count 1   --labels gpu=true   --node-taints sku=gpu:NoSchedule
```

Verify:

```bash
kubectl get nodes -L agentpool,gpu -o wide
```

---

## 4) Install the NVIDIA GPU Operator

```bash
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update

helm upgrade --install gpu-operator nvidia/gpu-operator   --namespace gpu-operator --create-namespace

kubectl -n gpu-operator get pods -o wide

kubectl describe node -l gpu=true | grep -i "nvidia.com/gpu" -n || echo "GPU resource not visible yet"
```

---

## 5) Create vLLM Namespace and Hugging Face Secret

```bash
kubectl create namespace vllm

kubectl -n vllm create secret generic hf   --from-literal=HUGGING_FACE_HUB_TOKEN=<YOUR_HF_TOKEN>   --dry-run=client -o yaml | kubectl apply -f -
```

---

## 6) (Optional) Red Hat Registry Pull Secret using Podman

### a. Install podman (if not already installed)

```bash
sudo apt install -y podman
```

### b. Login to Red Hat registry

```bash
podman login registry.redhat.io
```

### c. Create pull secret from podman auth

```bash
kubectl -n vllm create secret generic rh-pull   --from-file=.dockerconfigjson="$XDG_RUNTIME_DIR/containers/auth.json"   --type=kubernetes.io/dockerconfigjson
```

---

## 7) Deploy Red Hat vLLM with Llama-3.1-8B-Instruct

```bash
kubectl apply -f vllm-redhat-llama8b.yaml

kubectl -n vllm get pods -o wide
kubectl -n vllm logs -f deploy/vllm-llama8b -c vllm
kubectl -n vllm get svc vllm-llama8b
```

---

## 7.1) What's in `vllm-redhat-llama8b.yaml`

This file includes:

- ✅ Namespace: `vllm`
- ✅ PVC: `vllm-cache` (50Gi) for persistent model storage
- ✅ Deployment: Runs vLLM container with GPU scheduling
- ✅ Node selector & tolerations to bind to GPU node pool
- ✅ Environment:
  - `VLLM_WORKER_GPU_MEMORY_UTILIZATION=0.85`
  - Hugging Face token pulled from `hf` secret
- ✅ Container image: `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.2.1`
- ✅ LoadBalancer Service: Exposes OpenAI-compatible endpoint at `/v1/...` on port 8000

---

## 8) Test the Endpoint

```bash
curl http://<LOADBALANCER_IP>:8000/v1/models
```

### Streaming example:

```bash
curl -N http://<LOADBALANCER_IP>:8000/v1/chat/completions   -H "Content-Type: application/json"   -d '{
    "model": "RedHatAI/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "Write a short poem about Kubernetes and GPUs."}
    ],
    "max_tokens": 100,
    "stream": true
  }'
```

### Non-streaming example:

```bash
curl http://<LOADBALANCER_IP>:8000/v1/chat/completions   -H "Content-Type: application/json"   -d '{
    "model": "RedHatAI/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "Give me three bullet points about AKS GPU scheduling."}
    ],
    "max_tokens": 150
  }'
```

---

## 9) Tuning & Notes

- **Memory errors?** Lower:
  - `VLLM_WORKER_GPU_MEMORY_UTILIZATION` (e.g. `0.82`)
  - `--max-model-len` (e.g. `4096`)

- **Persistence**: `vllm-cache` PVC avoids re-downloads  
- **Scaling**: Use `--tensor-parallel-size`, add HPA, Ingress, PDB, TLS  
- **Security**: Store secrets in Kubernetes, not in Git

---

## 🔥 Cleanup

```bash
kubectl delete -f vllm-redhat-llama8b.yaml
kubectl delete ns vllm
helm uninstall gpu-operator -n gpu-operator
az aks nodepool delete -g "$RG" --cluster-name "$CLUSTER" -n gpua10
```

---

## 📁 Files in This Repo

- `vllm-redhat-llama8b.yaml` – Namespace, PVC, Deployment, LoadBalancer  
- Terraform files:
  - `main.tf`, `aks.tf`, `identity.tf`, `networking.tf`, `bastion.tf`, `outputs.tf`, `providers.tf`, `variables.tf`

---

✅ You're now running **Llama 3.1-8B Instruct** on Azure AKS with A10 GPU using Red Hat’s vLLM, exposed via a secure OpenAI-compatible API.
