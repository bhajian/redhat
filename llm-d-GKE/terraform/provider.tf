terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable needed APIs (idempotent)
resource "google_project_service" "services" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "networkservices.googleapis.com", # Gateway API LB control plane
    "networksecurity.googleapis.com", # Gateway API policies
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}
