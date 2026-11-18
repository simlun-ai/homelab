terraform {
  required_version = "= 1.13.0"

  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "= 3.1.1"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.38.0"
    }
  }

  backend "local" {}

  encryption {
    key_provider "external" "trust" {
      command = var.state_key_command
    }

    method "aes_gcm" "trust" {
      keys = key_provider.external.trust
    }

    state {
      method   = method.aes_gcm.trust
      enforced = true
    }

    plan {
      method   = method.aes_gcm.trust
      enforced = true
    }
  }
}

variable "state_key_command" {
  type     = list(string)
  nullable = false
}

variable "kubeconfig_path" {
  type     = string
  nullable = false
}

provider "helm" {
  kubernetes = {
    config_path = var.kubeconfig_path
  }
}

provider "kubernetes" {
  config_path = var.kubeconfig_path
}
