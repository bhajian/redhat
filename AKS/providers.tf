required_providers {
  azurerm = {
    source  = "hashicorp/azurerm"
    version = ">= 3.114.0"
  }
  random = {
    source  = "hashicorp/random"
    version = "~> 3.6"
  }
}

provider "azurerm" {
  features {}
  use_cli = true
}
