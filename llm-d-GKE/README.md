0) Set variables (edit as needed)
export PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
export REGION="us-central1"
export ZONES="us-central1-a,us-central1-b,us-central1-c"
export CLUSTER_NAME="vllm-cluster"
export HF_TOKEN="<YOUR_HF_TOKEN>"     # must have access to the Llama repo

1) Authenticate & enable APIs
gcloud auth login
gcloud config set project "$PROJECT_ID"
gcloud services enable compute.googleapis.com container.googleapis.com artifactregistry.googleapis.com iam.googleapis.com serviceusage.googleapis.com

2) (Optional but easy) Terraform service account
gcloud iam service-accounts create tf-admin --display-name="Terraform Admin"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:tf-admin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/owner"

gcloud iam service-accounts keys create ./tf-admin-key.json \
  --iam-account="tf-admin@${PROJECT_ID}.iam.gserviceaccount.com"
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/tf-admin-key.json"

3) Terraform: VPC, NAT, GKE (Standard), node pools (incl. L4), bastion
cd infra
# make sure terraform.tfvars has project/region/zones/cluster_name matching your vars
terraform init
terraform apply -auto-approve

4) Kube context to the new cluster
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION" --project "$PROJECT_ID"
kubectl get nodes -L cloud.google.com/gke-accelerator

5) Install NVIDIA GPU Operator (driver + toolkit + device plugin)
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update
kubectl create ns gpu-operator
helm upgrade --install gpu-operator nvidia/gpu-operator -n gpu-operator \
  --set driver.enabled=true --set toolkit.enabled=true --set devicePlugin.enabled=true

# wait until Ready
kubectl -n gpu-operator get pods -w
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" => "}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'

6) Deploy vLLM (namespace, secrets, manifests)
kubectl create ns vllm

# HF token (needed for Llama; skip if you’re using a permissive model)
kubectl -n vllm create secret generic hf-secret \
  --from-literal=HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

# (Optional) Red Hat registry pull secret if your Deployment uses registry.redhat.io
# kubectl -n vllm create secret docker-registry rh-pull \
#   --docker-server=registry.redhat.io \
#   --docker-username="<your_rh_username>" \
#   --docker-password="<your_rh_pull_token>" \
#   --docker-email="you@example.com"

# Apply your manifests (PVC, Deployment, Service)
cd ../k8s
kubectl apply -f .

7) Watch rollout & verify GPU is attached
kubectl -n vllm get pods -w
POD=$(kubectl -n vllm get pod -l app=vllm-llama3 -o jsonpath='{.items[0].metadata.name}')
kubectl -n vllm describe pod "$POD" | sed -n '/Allocated resources:/,/Events:/p'   # look for nvidia.com/gpu: 1

8) Get the external IP and test the API
kubectl -n vllm get svc
IP=$(kubectl -n vllm get svc vllm-llama3-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

curl "http://$IP/v1/models"
curl -s "http://$IP/v1/chat/completions" \
  -H "Content-Type: application/json" -H "Authorization: Bearer dummy" \
  -d '{"model":"llama3-8b","messages":[{"role":"user","content":"Hello from L4 on GKE"}]}'

9) (If downloads are blocked) Preload or enable egress

To allow online download: ensure NAT/egress is open and set:

kubectl -n vllm set env deploy vllm-llama3 TRANSFORMERS_OFFLINE=0 HF_HUB_OFFLINE=0 HF_HOME=/home/vllm/.cache HF_HUB_ENABLE_HF_TRANSFER=1


To run offline: use the initContainer preload method we used earlier, then set TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1.

10) Teardown (when done)
cd ../infra
terraform destroy

Quick “it’s broken” checklist
# GPU visible?
kubectl get nodes -L cloud.google.com/gke-accelerator
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{" => "}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}'

# GPU operator healthy?
kubectl -n gpu-operator get pods
kubectl -n vllm describe pod -l app=vllm-llama3 | sed -n '/Allocated resources:/,/Events:/p'

# Hugging Face egress?
kubectl -n vllm exec -it "$POD" -- bash -lc 'curl -sI https://huggingface.co | head -n1'


That’s it—run straight through and you’re online. If you want me to collapse this into a one-click Makefile (make bootstrap, make deploy), say the word and I’ll draft it.

