locals {
  zfs_localpv = jsondecode(file("${path.module}/zfs-localpv.json"))
}

resource "kubernetes_namespace_v1" "zfs_localpv" {
  metadata {
    name = "openebs-zfs"
    labels = {
      "pod-security.kubernetes.io/enforce" = "privileged"
      "pod-security.kubernetes.io/warn"    = "privileged"
    }
  }
}

resource "helm_release" "zfs_localpv" {
  name      = "zfs-localpv"
  namespace = kubernetes_namespace_v1.zfs_localpv.metadata[0].name
  chart     = "./zfs-localpv-${local.zfs_localpv.version}.tgz"
  values    = [file("${path.module}/zfs-localpv-values.yaml")]
  atomic    = true
  timeout   = 300
}

resource "kubernetes_storage_class_v1" "zfs_rehearsal" {
  metadata {
    name = "trust-zfs-rehearsal"
  }

  storage_provisioner = "zfs.csi.openebs.io"
  volume_binding_mode = "WaitForFirstConsumer"
  reclaim_policy      = "Delete"

  parameters = {
    fstype   = "zfs"
    poolname = "trust-data"
  }

  depends_on = [helm_release.zfs_localpv]
}
