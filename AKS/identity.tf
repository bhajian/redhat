# User-assigned identity for AKS
resource "azurerm_user_assigned_identity" "aks_uami" {
  name                = "${var.name_prefix}-uami-aks"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

# Give Network Contributor on the VNet
data "azurerm_role_definition" "network_contributor" {
  name = "Network Contributor"
}

resource "azurerm_role_assignment" "aks_vnet_nc" {
  scope              = azurerm_virtual_network.vnet.id
  role_definition_id = data.azurerm_role_definition.network_contributor.id
  principal_id       = azurerm_user_assigned_identity.aks_uami.principal_id
}
