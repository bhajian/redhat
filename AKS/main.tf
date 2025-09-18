resource "random_pet" "suffix" {}

resource "azurerm_resource_group" "rg" {
  name     = "${var.name_prefix}-rg-${random_pet.suffix.id}"
  location = var.location

  tags = {
    project = var.name_prefix
  }
}
