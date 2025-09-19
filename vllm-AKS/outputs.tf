output "resource_group" {
  value = azurerm_resource_group.rg.name
}

output "aks_name" {
  value = azurerm_kubernetes_cluster.aks.name
}

output "region" {
  value = azurerm_resource_group.rg.location
}

output "nat_public_ip" {
  value = azurerm_public_ip.nat_pip.ip_address
}

output "bastion_url_hint" {
  value = "Use Azure Portal > ${azurerm_resource_group.rg.name} > Bastion > ${azurerm_bastion_host.bastion.name}"
}
