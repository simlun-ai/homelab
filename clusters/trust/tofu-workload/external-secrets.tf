locals {
  external_secrets           = jsondecode(file("${path.module}/external-secrets.json"))
  external_secrets_image_tag = "v${local.external_secrets.version}@${local.external_secrets.image_digest}"
}

resource "kubernetes_namespace_v1" "external_secrets" {
  metadata {
    name = "external-secrets"
  }
}

resource "helm_release" "external_secrets" {
  name      = "external-secrets"
  namespace = kubernetes_namespace_v1.external_secrets.metadata[0].name
  chart     = "./external-secrets-${local.external_secrets.version}.tgz"
  values = [
    file("${path.module}/external-secrets-values.yaml"),
    yamlencode({
      image          = { tag = local.external_secrets_image_tag }
      webhook        = { image = { tag = local.external_secrets_image_tag } }
      certController = { image = { tag = local.external_secrets_image_tag } }
    }),
  ]
}
