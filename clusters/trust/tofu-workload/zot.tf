locals {
  zot = jsondecode(file("${path.module}/zot.json"))
}

resource "kubernetes_namespace_v1" "zot" {
  metadata {
    name = "zot"
  }
}

resource "helm_release" "zot" {
  name      = "zot"
  namespace = kubernetes_namespace_v1.zot.metadata[0].name
  chart     = "./zot-${local.zot.version}.tgz"
  values = [
    file("${path.module}/zot-values.yaml"),
    yamlencode({ image = { tag = "${local.zot.app_version}@${local.zot.image_digest}" } }),
  ]

  # TLS and the independently provisioned publisher Secret may arrive later.
  wait = false
}
