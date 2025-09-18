variable "location" {
  type        = string
  default     = "eastus"
  description = "Azure region"
}

variable "name_prefix" {
  type        = string
  default     = "ben-aks"
  description = "Prefix for resource names"
}

variable "address_space" {
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "aks_subnet_cidr" {
  type        = string
  default     = "10.0.0.0/22"
}

variable "bastion_subnet_cidr" {
  type        = string
  # Azure Bastion requires /26 or larger
  default     = "10.0.4.0/26"
}

# Azure CNI Overlay pod CIDR (separate from VNet)
variable "pod_cidr" {
  type        = string
  default     = "10.244.0.0/16"
}

# Cluster service CIDR & CoreDNS IP (must not overlap with VNet/pod CIDR)
variable "service_cidr" {
  type        = string
  default     = "10.2.0.0/16"
}

variable "dns_service_ip" {
  type        = string
  default     = "10.2.0.10"
}

variable "kubernetes_version" {
  type    = string
  default = null # let AKS choose if not set
}

variable "node_count" {
  type    = number
  default = 3
}

variable "node_size" {
  type    = string
  default = "Standard_D4s_v5"
}
