locals {
  headlamp = jsondecode(file("${path.module}/headlamp.json"))
}

resource "kubernetes_namespace_v1" "headlamp" {
  metadata {
    name = "headlamp"
  }
}

resource "helm_release" "headlamp" {
  name      = "headlamp"
  namespace = kubernetes_namespace_v1.headlamp.metadata[0].name
  chart     = "./headlamp-${local.headlamp.version}.tgz"
  values = [
    file("${path.module}/headlamp-values.yaml"),
    yamlencode({
      config = { inClusterContextName = "trust" }
      image  = { tag = "v${local.headlamp.version}@${local.headlamp.image_digest}" }
    }),
  ]
}
