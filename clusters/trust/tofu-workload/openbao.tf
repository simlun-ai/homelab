locals {
  openbao = jsondecode(file("${path.module}/openbao.json"))
}

resource "kubernetes_namespace_v1" "openbao" {
  metadata {
    name = "openbao"
  }
}

resource "helm_release" "openbao" {
  name      = "openbao"
  namespace = kubernetes_namespace_v1.openbao.metadata[0].name
  chart     = "./openbao-${local.openbao.version}.tgz"
  values    = [file("${path.module}/openbao-values.yaml")]

  # The first deployment keeps the pod out of Service endpoints until the
  # separate initialization rollout brings up its network listener.
  wait = false
}
