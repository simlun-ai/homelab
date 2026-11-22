locals {
  talos_kms = jsondecode(file("${path.module}/talos-kms.json"))
  talos_kms_chart_digest = sha256(join("", [
    for name in sort(tolist(fileset("${path.module}/talos-kms", "**"))) :
    filesha256("${path.module}/talos-kms/${name}")
  ]))
}

resource "helm_release" "talos_kms" {
  for_each = {
    for name, config in local.talos_kms.clusters : name => config
    if length(config.nodes) > 0
  }

  name             = "talos-${each.key}"
  namespace        = "talos-kms"
  create_namespace = true
  chart            = "./talos-kms"
  wait             = false
  values = [yamlencode(merge(each.value, {
    cluster     = each.key
    image       = local.talos_kms.image
    chartDigest = local.talos_kms_chart_digest
  }))]

  lifecycle {
    precondition {
      condition     = can(regex("@sha256:[a-f0-9]{64}$", local.talos_kms.image))
      error_message = "Pin the Talos KMS adapter image by digest before registering nodes."
    }
  }

  depends_on = [helm_release.openbao_jobs]
}
