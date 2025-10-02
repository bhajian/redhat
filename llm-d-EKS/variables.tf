variable "region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "cluster_name" {
  type        = string
  description = "EKS cluster name"
  default     = "eks-gpu-prod"
}

variable "cluster_version" {
  type        = string
  description = "Kubernetes version"
  default     = "1.33"
}

variable "vpc_id" {
  type        = string
  description = "Existing VPC ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs (worker nodes here)"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs (internet-facing LBs here)"
}

variable "admin_role_arn" {
  type        = string
  description = "IAM Role ARN that will be system:masters on the cluster"
}

# Node groups
variable "cpu_instance_type" {
  type        = string
  default     = "m6i.large"
}

variable "cpu_desired" {
  type    = number
  default = 2
}

variable "cpu_min" {
  type    = number
  default = 2
}

variable "cpu_max" {
  type    = number
  default = 5
}

variable "enable_gpu_node_group" {
  type        = bool
  description = "Create GPU node group now?"
  default     = false
}

variable "gpu_instance_type" {
  type    = string
  default = "g5.xlarge"
}

variable "gpu_desired" {
  type    = number
  default = 1
}

variable "gpu_min" {
  type    = number
  default = 0
}

variable "gpu_max" {
  type    = number
  default = 3
}
