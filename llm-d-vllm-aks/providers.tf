terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = ">= 3.114.0" }
    random  = { source = "hashicorp/random",  version = "~> 3.6" }
  }
}

provider "azurerm" {
  features {}
  use_cli = true
  # Optional: allow RG deletion even if unmanaged resources remain
  # features {
  #   resource_group { prevent_deletion_if_contains_resources = false }
  # }
}
