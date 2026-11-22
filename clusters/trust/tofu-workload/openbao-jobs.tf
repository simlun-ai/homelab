locals {
  restore_pin = jsondecode(file("${path.module}/openbao-restore.json"))
  job_tools   = jsondecode(file("${path.module}/openbao-jobs-tools.json"))
}

resource "kubernetes_namespace_v1" "openbao_restore" {
  metadata {
    name = "openbao-restore"
  }
}

resource "helm_release" "openbao_restore" {
  name      = "openbao-restore"
  namespace = kubernetes_namespace_v1.openbao_restore.metadata[0].name
  chart     = "./openbao-restore-${local.restore_pin.version}.tgz"
  values    = [file("${path.module}/openbao-restore-values.yaml")]
  wait      = false
}

resource "helm_release" "openbao_jobs" {
  name      = "openbao-jobs"
  namespace = kubernetes_namespace_v1.openbao.metadata[0].name
  chart     = "./openbao-jobs"
  values = [yamlencode({
    restoreNamespace    = kubernetes_namespace_v1.openbao_restore.metadata[0].name
    backupScriptSha256  = filesha256("${path.module}/openbao-jobs/scripts/backup.sh")
    restoreScriptSha256 = filesha256("${path.module}/openbao-jobs/scripts/restore.sh")
    backupSuspend       = false
    restoreSuspend      = false
    sourceVersion       = local.openbao.app_version
    restoreVersion      = local.restore_pin.app_version
    baoImage            = local.openbao.cli_image
    resticImage         = local.job_tools.restic.image
    jq                  = local.job_tools.jq
    s5cmd               = local.job_tools.s5cmd
    kubectl             = jsondecode(file("${path.module}/backup-kubectl.json"))
  })]

  depends_on = [helm_release.openbao, helm_release.openbao_restore]
}
