variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "gke_name" {
  description = "GKE cluster name"
  type        = string
  default     = "vllm-cluster"
}

variable "vpc_name" {
  description = "VPC name"
  type        = string
  default     = "vllm-vpc"
}

variable "gke_subnet_cidr" {
  description = "Primary CIDR for the GKE subnet"
  type        = string
  default     = "10.10.0.0/20"
}

variable "pods_secondary_cidr" {
  description = "Pods secondary range CIDR"
  type        = string
  default     = "10.20.0.0/14"
}

variable "services_secondary_cidr" {
  description = "Services secondary range CIDR"
  type        = string
  default     = "10.40.0.0/20"
}

variable "proxy_only_subnet_cidr" {
  description = "Proxy-only subnet for External Managed L7"
  type        = string
  default     = "10.129.0.0/23"
}

variable "psc_subnet_cidr" {
  description = "Private Service Connect subnet (optional)"
  type        = string
  default     = "10.130.0.0/23"
}
