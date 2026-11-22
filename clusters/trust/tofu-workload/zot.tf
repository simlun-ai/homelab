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

  # cert-manager and ESO reconcile their Secrets after Helm creates the objects.
  wait = false

  depends_on = [helm_release.external_secrets]
}
