terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws         = { source = "hashicorp/aws",        version = ">= 5.40" }
    kubernetes  = { source = "hashicorp/kubernetes", version = ">= 2.29" }
    helm        = { source = "hashicorp/helm",       version = ">= 2.13" }
  }
}

# -------------------------
# Variables
# -------------------------
variable "region"          { type = string, default = "us-east-1" }
variable "cluster_name"    { type = string, default = "eks-gpu-prod" }
variable "cluster_version" { type = string, default = "1.33" }

variable "vpc_id"             { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids"  { type = list(string) }

# IAM role you use to admin the cluster
variable "admin_role_arn" { type = string }

# Node groups
variable "cpu_instance_type" { type = string, default = "m6i.large" }
variable "cpu_desired"       { type = number, default = 2 }
variable "cpu_min"           { type = number, default = 2 }
variable "cpu_max"           { type = number, default = 5 }

variable "enable_gpu_node_group" { type = bool,   default = false }
variable "gpu_instance_type"     { type = string, default = "g5.xlarge" }
variable "gpu_desired"           { type = number, default = 1 }
variable "gpu_min"               { type = number, default = 0 }
variable "gpu_max"               { type = number, default = 3 }

locals { gpu_enabled = var.enable_gpu_node_group }

# -------------------------
# Providers
# -------------------------
provider "aws" { region = var.region }

# Create cluster first, then wire k8s/helm providers dynamically
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.31.4"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  enable_irsa = true

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = false

  eks_managed_node_groups = {
    cpu = {
      name           = "cpu-ng"
      instance_types = [var.cpu_instance_type]
      # For K8s >=1.30 use AL2023 variants
      ami_type       = "AL2023_x86_64_STANDARD"
      min_size       = var.cpu_min
      max_size       = var.cpu_max
      desired_size   = var.cpu_desired
      subnet_ids     = var.private_subnet_ids
      capacity_type  = "ON_DEMAND"
      disk_size      = 100
      labels         = { workload = "cpu" }
    }

    gpu = local.gpu_enabled ? {
      name           = "gpu-ng"
      instance_types = [var.gpu_instance_type]
      ami_type       = "AL2023_x86_64_NVIDIA"
      min_size       = var.gpu_min
      max_size       = var.gpu_max
      desired_size   = var.gpu_desired
      subnet_ids     = var.private_subnet_ids
      capacity_type  = "ON_DEMAND"
      disk_size      = 100
      labels         = { workload = "gpu" }
      # taints = [{ key = "nvidia.com/gpu", value = "present", effect = "NO_SCHEDULE" }]
    } : null
  }
}

# Data for k8s/helm provider auth
data "aws_eks_cluster" "this" {
  depends_on = [module.eks]
  name       = module.eks.cluster_name
}

data "aws_eks_cluster_auth" "this" {
  depends_on = [module.eks]
  name       = module.eks.cluster_name
}

provider "kubernetes" {
  host                   = try(data.aws_eks_cluster.this.endpoint, null)
  cluster_ca_certificate = try(base64decode(data.aws_eks_cluster.this.certificate_authority[0].data), null)
  token                  = try(data.aws_eks_cluster_auth.this.token, null)
}

provider "helm" {
  kubernetes {
    host                   = try(data.aws_eks_cluster.this.endpoint, null)
    cluster_ca_certificate = try(base64decode(data.aws_eks_cluster.this.certificate_authority[0].data), null)
    token                  = try(data.aws_eks_cluster_auth.this.token, null)
  }
}

# -------------------------
# aws-auth ConfigMap (v20.x uses submodule)
# -------------------------
module "aws_auth" {
  source  = "terraform-aws-modules/eks/aws//modules/aws-auth"
  version = "~> 20.0"

  depends_on = [module.eks]
  create_aws_auth_configmap = true

  aws_auth_roles = [{
    rolearn  = var.admin_role_arn
    username = "admin"
    groups   = ["system:masters"]
  }]
}

# -------------------------
# Subnet tags for LBs
# -------------------------
resource "aws_ec2_tag" "public_cluster_shared" {
  for_each    = toset(var.public_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/cluster/${var.cluster_name}"
  value       = "shared"
}

resource "aws_ec2_tag" "public_role_elb" {
  for_each    = toset(var.public_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/role/elb"
  value       = "1"
}

resource "aws_ec2_tag" "private_cluster_shared" {
  for_each    = toset(var.private_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/cluster/${var.cluster_name}"
  value       = "shared"
}

resource "aws_ec2_tag" "private_role_internal_elb" {
  for_each    = toset(var.private_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/role/internal-elb"
  value       = "1"
}

# -------------------------
# ALB Controller IRSA (pin v5.x to use role_name_prefix)
# -------------------------
module "alb_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"

  role_name_prefix = "${var.cluster_name}-alb-"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    eks = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

# -------------------------
# Helm: AWS Load Balancer Controller
# -------------------------
resource "helm_release" "aws_load_balancer_controller" {
  name             = "aws-load-balancer-controller"
  repository       = "https://aws.github.io/eks-charts"
  chart            = "aws-load-balancer-controller"
  namespace        = "kube-system"
  create_namespace = false

  depends_on = [
    module.eks,
    module.alb_irsa,
    aws_ec2_tag.public_cluster_shared,
    aws_ec2_tag.public_role_elb,
    aws_ec2_tag.private_cluster_shared,
    aws_ec2_tag.private_role_internal_elb
  ]

  values = [yamlencode({
    clusterName = var.cluster_name
    region      = var.region
    vpcId       = var.vpc_id
    serviceAccount = {
      create = true
      name   = "aws-load-balancer-controller"
      annotations = {
        "eks.amazonaws.com/role-arn" = module.alb_irsa.iam_role_arn
      }
    }
  })]
}

# -------------------------
# Helm: NVIDIA Device Plugin (only if GPU NG is enabled)
# -------------------------
resource "helm_release" "nvidia_device_plugin" {
  count            = local.gpu_enabled ? 1 : 0
  name             = "nvidia-device-plugin"
  repository       = "https://nvidia.github.io/k8s-device-plugin"
  chart            = "nvidia-device-plugin"
  namespace        = "kube-system"
  create_namespace = false
  depends_on       = [module.eks]
}

# -------------------------
# Outputs
# -------------------------
output "cluster_name"              { value = module.eks.cluster_name }
output "cluster_endpoint"          { value = module.eks.cluster_endpoint }
output "oidc_provider_arn"         { value = module.eks.oidc_provider_arn }
output "node_group_names"          { value = [for ng in module.eks.eks_managed_node_groups : ng.node_group_name] }
output "public_subnet_tags_applied"  { value = var.public_subnet_ids }
output "private_subnet_tags_applied" { value = var.private_subnet_ids }
