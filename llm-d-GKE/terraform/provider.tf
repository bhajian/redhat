terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.10"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  description = "The GCP project ID."
  default     = "openenv-qnc79" // Your Project ID is automatically filled in
}

variable "region" {
  description = "The GCP region for resources."
  default     = "us-central1"
}
