locals {
  cert_manager = jsondecode(file("${path.module}/cert-manager.json"))
}

variable "cert_manager_cloudflare_token" {
  type      = string
  sensitive = true
  nullable  = false
}

resource "kubernetes_namespace_v1" "cert_manager" {
  metadata {
    name = "cert-manager"
  }
}

resource "helm_release" "cert_manager" {
  name          = "cert-manager"
  namespace     = kubernetes_namespace_v1.cert_manager.metadata[0].name
  chart         = "./cert-manager-${local.cert_manager.version}.tgz"
  values        = [file("${path.module}/cert-manager-values.yaml")]
  atomic        = true
  wait_for_jobs = true
  timeout       = 300
}

resource "kubernetes_secret_v1" "cert_manager_cloudflare" {
  metadata {
    name      = "trust-cert-manager-cloudflare"
    namespace = kubernetes_namespace_v1.cert_manager.metadata[0].name
  }

  type = "Opaque"
  data = {
    api-token = var.cert_manager_cloudflare_token
  }
}

# The separate Helm release lets the webhook and CRDs become ready before
# Helm submits ClusterIssuers, including on an empty cluster.
resource "helm_release" "trust_acme_issuers" {
  name      = "trust-acme-issuers"
  namespace = kubernetes_namespace_v1.cert_manager.metadata[0].name
  chart     = "./trust-acme-issuers"
  values = [yamlencode({
    cloudflareTokenSecret = kubernetes_secret_v1.cert_manager_cloudflare.metadata[0].name
  })]
  atomic  = true
  timeout = 300

  depends_on = [helm_release.cert_manager]
}
