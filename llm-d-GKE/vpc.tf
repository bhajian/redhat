resource "google_compute_network" "main_vpc" {
  name                    = "vllm-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "gke_subnets" {
  count         = 3
  name          = "gke-subnet-${count.index}"
  ip_cidr_range = "10.10.${count.index + 1}.0/24"
  region        = var.region
  network       = google_compute_network.main_vpc.id
  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  name    = "gke-router"
  network = google_compute_network.main_vpc.id
  region  = var.region
}

resource "google_compute_router_nat" "nat" {
  name                               = "gke-nat-gateway"
  router                             = google_compute_router.router.name
  region                             = google_compute_router.router.region
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  nat_ip_allocate_option             = "AUTO_ONLY"
}
