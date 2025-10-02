locals {
  gpu_enabled = var.enable_gpu_node_group
}

# --- EKS Cluster + Node Groups ---
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = ">= 21.3.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  enable_irsa = true

  # Public API for simplicity with a bastion (flip later if you want)
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = false

  manage_aws_auth = true
  aws_auth_roles = [
    {
      rolearn  = var.admin_role_arn
      username = "admin"
      groups   = ["system:masters"]
    }
  ]

  eks_managed_node_groups = {
    cpu = {
      name           = "cpu-ng"
      instance_types = [var.cpu_instance_type]
      # For K8s 1.33 you must use AL2023 or Bottlerocket (AL2 is not provided)
      ami_type       = "AL2023_x86_64"
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
      # AL2023 accelerated NVIDIA AMI variant for 1.33
      ami_type       = "AL2023_x86_64_NVIDIA"
      min_size       = var.gpu_min
      max_size       = var.gpu_max
      desired_size   = var.gpu_desired
      subnet_ids     = var.private_subnet_ids
      capacity_type  = "ON_DEMAND"
      disk_size      = 100
      labels         = { workload = "gpu" }
      # Optional taint to keep non-GPU pods away:
      # taints = [{ key = "nvidia.com/gpu", value = "present", effect = "NO_SCHEDULE" }]
    } : null
  }
}

# --- Tag your existing subnets so LBs land correctly ---
# Public subnets: internet-facing LBs
resource "aws_ec2_tag" "public_cluster_shared" {
  for_each   = toset(var.public_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/cluster/${var.cluster_name}"
  value       = "shared"
}

resource "aws_ec2_tag" "public_role_elb" {
  for_each   = toset(var.public_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/role/elb"
  value       = "1"
}

# Private subnets: internal LBs
resource "aws_ec2_tag" "private_cluster_shared" {
  for_each   = toset(var.private_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/cluster/${var.cluster_name}"
  value       = "shared"
}

resource "aws_ec2_tag" "private_role_internal_elb" {
  for_each   = toset(var.private_subnet_ids)
  resource_id = each.value
  key         = "kubernetes.io/role/internal-elb"
  value       = "1"
}

# --- IRSA role for AWS Load Balancer Controller ---
# NOTE: In v6.x of the IAM module, the submodule path changed (no "-eks" suffix).
module "alb_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts"
  version = "~> 6.0"

  name_prefix = "${var.cluster_name}-alb-"

  attach_load_balancer_controller_policy = true

  oidc_providers = {
    eks = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

# --- AWS Load Balancer Controller (ALB/NLB integration) ---
resource "helm_release" "aws_load_balancer_controller" {
  name            = "aws-load-balancer-controller"
  repository      = "https://aws.github.io/eks-charts"
  chart           = "aws-load-balancer-controller"
  namespace       = "kube-system"
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

# --- NVIDIA Device Plugin (only if GPU NG is enabled) ---
resource "helm_release" "nvidia_device_plugin" {
  count           = local.gpu_enabled ? 1 : 0
  name            = "nvidia-device-plugin"
  repository      = "https://nvidia.github.io/k8s-device-plugin"
  chart           = "nvidia-device-plugin"
  namespace       = "kube-system"
  create_namespace = false
  depends_on      = [module.eks]
}
