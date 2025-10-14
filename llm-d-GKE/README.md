# Deploying a llm-d Model on GKE with Inference Gateway

This guide provides end-to-end instructions for provisioning a GPU-enabled GKE cluster using Terraform and deploying a large language model served by vLLM with the GKE Inference Gateway.

---

## 📁 Project Structure

    .
    ├── k8s/
    │   ├── gateway.yaml
    │   ├── httproute.yaml
    │   ├── inference-objectives.yaml
    │   └── vllm-deployment.yaml
    ├── terraform/
    │   ├── gke.tf
    │   ├── provider.tf
    │   └── vpc.tf
    └── README.md

---

## 1. Local Environment Setup

First, install the necessary command-line tools on your local machine (macOS).

    # Install Homebrew (if you don't have it)
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Install Google Cloud SDK, Terraform, and Helm
    brew install --cask google-cloud-sdk
    brew install terraform
    brew install helm

    # Initialize the gcloud CLI
    gcloud init

    # Set up credentials for Terraform and other applications
    gcloud auth application-default login

    # Enable the required APIs for your GCP project
    gcloud services enable container.googleapis.com \
      compute.googleapis.com \
      networkservices.googleapis.com

---

## 2. Deploy Infrastructure with Terraform

These steps will create the VPC, subnets, GKE cluster, and GPU node pool.

    # Navigate to the Terraform directory
    cd terraform

    # Initialize Terraform to download the necessary providers
    terraform init

    # Apply the configuration to build your infrastructure
    terraform apply

---

## 3. Configure Kubernetes (kubectl)

Connect your local `kubectl` to the newly created GKE cluster.

    # Get the credentials for your GKE cluster
    gcloud container clusters get-credentials vllm-cluster --region us-central1

    # Verify the connection
    kubectl get nodes

    # Enable the GKE Gateway Controller
    gcloud container clusters update vllm-cluster \
      --region=us-central1 \
      --gateway-api=standard

---

## 4. Deploy the GKE Inference Gateway and VLLM

Deploy the application components in the correct order to ensure all dependencies are met.

    # Navigate to the Kubernetes manifests directory
    cd ../k8s

    # 1. Create the namespace
    kubectl create namespace vllm

    # 2. Create the Hugging Face secret
    kubectl create secret generic hf-secret \
      --namespace vllm \
      --from-literal=HUGGING_FACE_HUB_TOKEN=hf_YOUR_TOKEN_HERE

    # 3. Deploy the VLLM model server
    kubectl apply -f vllm-deployment.yaml

    # Wait for pod readiness
    kubectl get pods -n vllm -w

    # 4. Install the InferencePool using Helm
    helm install vllm-llama3 \
      --namespace vllm \
      --set inferencePool.modelServers.matchLabels.app=vllm-llama3 \
      --set provider.name=gke \
      --version v1.0.1 \
      oci://registry.k8s.io/gateway-api-inference-extension/charts/inferencepool

    # 5. Apply the InferenceObjective
    kubectl apply -f inference-objectives.yaml

    # 6. Create the Gateway and HTTPRoute
    kubectl apply -f gateway.yaml
    kubectl apply -f httproute.yaml

---

## 5. Test the Endpoint

After a few minutes, GKE will assign an external IP to your Gateway. Use the following commands to test your model.

    # Get the Gateway IP Address
    echo "Waiting for the Gateway IP address..."
    IP=""
    while [ -z "$IP" ]; do
      IP=$(kubectl get gateway inference-gateway -n vllm -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)
      if [ -z "$IP" ]; then
        echo "Gateway IP not found, waiting 10 seconds..."
        sleep 10
      fi
    done
    echo "Gateway IP address is: $IP"
    export GATEWAY_IP=$IP

    # Send a test request
    curl http://${GATEWAY_IP}/v1/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "llama3-8b",
        "prompt": "The capital of Canada is",
        "max_tokens": 50,
        "temperature": 0
    }'

---

## 6. Cleanup

To avoid ongoing costs, destroy all the resources when you're finished.

    # Delete Kubernetes resources
    cd ../k8s
    kubectl delete -f httproute.yaml
    kubectl delete -f gateway.yaml
    kubectl delete -f inference-objectives.yaml
    helm uninstall vllm-llama3 -n vllm
    kubectl delete -f vllm-deployment.yaml
    kubectl delete namespace vllm

    # Destroy the cloud infrastructure
    cd ../terraform
    terraform destroy

---

**Done!**  
You’ve deployed a scalable vLLM model on Google Kubernetes Engine with the Inference Gateway.
