# Bastion setup (Ubuntu)
```
sudo apt-get update -y && sudo apt-get install -y unzip curl apt-transport-https gnupg

# AWS CLI v2 (Linux x86_64)
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install
aws --version

# Configure your credentials (or use an instance profile/SSO)
aws configure   # or `aws configure sso`

# kubectl (latest stable)
curl -fsSLo kubectl "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
kubectl version --client --output=yaml

# (Optional) jq & helm for convenience
sudo apt-get install -y jq
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version

curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
sudo tee /etc/apt/sources.list.d/hashicorp.list

sudo apt-get update -y
sudo apt-get install -y terraform

terraform -version
```

# Apply & Connect
once you set up ssh keys in your github:
```
git clone git@github.com:bhajian/redhat.git
cd redhat/llm-d-EKS

terraform init
terraform plan
terraform apply -auto-approve

# Kubeconfig from your bastion (same region/name as tfvars)
aws eks update-kubeconfig --region us-east-1 --name eks-gpu-prod

kubectl get nodes -o wide
kubectl -n kube-system get deployment aws-load-balancer-controller

```
