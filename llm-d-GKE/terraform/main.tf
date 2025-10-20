########################
# Networking
########################

resource "google_compute_network" "vpc" {
  name                    = var.vpc_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "gke" {
  name          = "gke-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.gke_subnet_cidr

  # Required for VPC-native (IP alias) GKE
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_secondary_cidr
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_secondary_cidr
  }

  purpose = "PRIVATE"
  role    = "ACTIVE"
}

# Required for External Managed regional L7 Gateway
resource "google_compute_subnetwork" "proxy_only" {
  name          = "proxy-only-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.proxy_only_subnet_cidr
  purpose       = "REGIONAL_MANAGED_PROXY"
  role          = "ACTIVE"
}

# Optional PSC subnet (kept for future)
resource "google_compute_subnetwork" "psc" {
  name          = "psc-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.psc_subnet_cidr
  purpose       = "PRIVATE_SERVICE_CONNECT"
}

# Router + NAT for egress to the internet (image pulls, etc.)
resource "google_compute_router" "router" {
  name    = "vllm-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "vllm-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Firewall for GFE health checks hitting NodePorts and intra-VPC traffic
resource "google_compute_firewall" "gfe_health" {
  name    = "allow-gfe-healthchecks"
  network = google_compute_network.vpc.name

  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"] # Google L7 health checks

  allow {
    protocol = "tcp"
    ports    = ["30000-32767"] # NodePort range
  }
}

resource "google_compute_firewall" "intra_vpc" {
  name    = "allow-intra-vpc"
  network = google_compute_network.vpc.name

  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["10.0.0.0/8"]

  allow {
    protocol = "all"
  }
}

########################
# GKE
########################

resource "google_container_cluster" "primary" {
  name     = var.gke_name
  location = var.region

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.gke.id

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  # VPC-native IPs
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Managed Gateway API (External Managed L7)
  gateway_api_config {
    channel = "CHANNEL_STANDARD"
  }

  depends_on = [google_project_service.services]
}

# CPU node pool (1 node)
resource "google_container_node_pool" "cpu_pool" {
  name       = "cpu-workloads-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  node_count = 1

  node_config {
    machine_type = "e2-standard-4"
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}

# GPU node pool (0 by default; scale up later when needed)
resource "google_container_node_pool" "gpu_pool" {
  name       = "l4-gpu-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  node_count = 1

  # REMOVE THIS LINE:
  # node_locations = ["${var.region}-a"] # pick a zone that supports L4

  node_config {
    machine_type = "g2-standard-8"

    guest_accelerator {
      type  = "nvidia-l4"
      count = 1
    }

    metadata = {
      "install-nvidia-driver" = "true"
    }

    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}

########################
# Outputs
########################

output "cluster_name" {
  value = google_container_cluster.primary.name
}

output "region" {
  value = var.region
}

output "get_credentials" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${var.region} --project ${var.project_id}"
}

output "vpc_name" {
  value = google_compute_network.vpc.name
}
