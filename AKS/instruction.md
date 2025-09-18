# Install AKS


# Add A10 GPUs to the cluster

RG="ben-aks-rg-settled-treefrog"
CLUSTER="ben-aks-aks"

az aks nodepool add \
  --resource-group "$RG" \
  --cluster-name "$CLUSTER" \
  --name gpua10 \
  --node-vm-size Standard_NV6ads_A10_v5 \
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

