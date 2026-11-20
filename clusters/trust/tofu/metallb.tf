locals {
  metallb = jsondecode(file("${path.module}/metallb.json"))
}

resource "kubernetes_namespace_v1" "metallb" {
  metadata {
    name = "metallb-system"
    labels = {
      "pod-security.kubernetes.io/enforce" = "privileged"
      "pod-security.kubernetes.io/warn"    = "privileged"
    }
  }
}

resource "helm_release" "metallb" {
  name      = "metallb"
  namespace = kubernetes_namespace_v1.metallb.metadata[0].name
  chart     = "./metallb-${local.metallb.version}.tgz"
  values    = [file("${path.module}/metallb-values.yaml")]
  atomic    = true
  timeout   = 300
}

# Install the pool and advertisement after the controller and its CRDs are ready.
resource "helm_release" "trust_metallb_config" {
  name      = "trust-metallb-config"
  namespace = kubernetes_namespace_v1.metallb.metadata[0].name
  chart     = "./trust-metallb-config"
  atomic    = true
  timeout   = 300

  depends_on = [helm_release.metallb]
}
