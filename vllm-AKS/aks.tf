resource "azurerm_kubernetes_cluster" "aks" {
  name                = "${var.name_prefix}-aks"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "${var.name_prefix}-dns"

  kubernetes_version  = var.kubernetes_version

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks_uami.id]
  }

  default_node_pool {
    name                = "nodepool1"
    vm_size             = var.node_size
    node_count          = var.node_count
    vnet_subnet_id      = azurerm_subnet.aks.id
    type                = "VirtualMachineScaleSets"
    orchestrator_version = var.kubernetes_version
  }

  network_profile {
    network_plugin       = "azure"
    network_plugin_mode  = "overlay"
    pod_cidr             = var.pod_cidr
    service_cidr         = var.service_cidr
    dns_service_ip       = var.dns_service_ip
    load_balancer_sku    = "standard"
    outbound_type        = "userAssignedNATGateway"
    network_data_plane    = "cilium"
  }

  role_based_access_control_enabled = true

  tags = {
    project = var.name_prefix
  }

  depends_on = [
    azurerm_role_assignment.aks_vnet_nc,
    azurerm_subnet_nat_gateway_association.aks_nat
  ]
}
