# Install AKS


# Add A10 GPUs to the cluster

RG="ben-aks-rg-settled-treefrog"
CLUSTER="ben-aks-aks"

az aks nodepool add \
  --resource-group "$RG" \
  --cluster-name "$CLUSTER" \
  --name gpua10 \
  --node-vm-size Standard_NV24ads_A10_v5 \
  --node-count 1 \
  --labels gpu=true \
  --node-taints sku=gpu:NoSchedule


# Install Nvidia Driver on the Cluster

helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update
helm upgrade --install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator --create-namespace

## wait until all pods are Running
kubectl -n gpu-operator get pods -o wide

# setup huggingface token
kubectl -n vllm create secret generic hf \
  --from-literal=HUGGING_FACE_HUB_TOKEN=<HF> \
  --dry-run=client -o yaml | kubectl apply -f -




# Try the model
curl http://57.152.10.249:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "RedHatAI/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "Write a short poem about Kubernetes and GPUs."}
    ],
    "max_tokens": 100,
    "stream": true
  }'