resource "google_container_cluster" "primary" {
  name     = "vllm-cluster"
  location = var.region

  network    = google_compute_network.main_vpc.id
  subnetwork = google_compute_subnetwork.gke_subnets[0].id

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection = false
}

# Standard CPU node pool
resource "google_container_node_pool" "cpu_pool" {
  name       = "cpu-workloads-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  node_count = 1

  node_config {
    machine_type = "e2-standard-4"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}

# GPU node pool with an L4 GPU
resource "google_container_node_pool" "gpu_pool" {
  name       = "l4-gpu-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  node_count = 0

  node_locations = [
    "us-central1-a"
  ]

  node_config {
    machine_type = "g2-standard-8"

    guest_accelerator {
      type  = "nvidia-l4"
      count = 1
    }

    # FIX: The manual taint block has been removed from here.
    # GKE will add it automatically because of the metadata below.

    metadata = {
      "install-nvidia-driver" = "true"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
