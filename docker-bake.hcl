group "default" {
  targets = ["lint", "typecheck", "ansible-lint", "helpers", "ups", "syntax", "trust-render", "trust-validate", "trust-config-rehearsal", "trust-credentials-rehearsal", "trust-recovery-rehearsal"]
}

group "ci" {
  targets = ["lint", "typecheck", "ansible-lint", "helpers", "ups", "syntax", "trust-render", "trust-validate", "trust-config-rehearsal", "trust-credentials-rehearsal", "trust-recovery-rehearsal"]
}

target "_common" {
  context = "."
  dockerfile = "ci/Dockerfile"
  platforms = ["linux/amd64"]
  output = ["type=cacheonly"]
}

target "helpers" {
  inherits = ["_common"]
  target = "helpers"
  no-cache-filter = ["helpers"]
}

target "ups" {
  inherits = ["_common"]
  target = "ups"
  no-cache-filter = ["ups"]
}

target "syntax" {
  inherits = ["_common"]
  target = "syntax"
  no-cache-filter = ["syntax"]
}

target "lint" {
  inherits = ["_common"]
  target = "lint"
  no-cache-filter = ["lint"]
}

target "lint-tool" {
  inherits = ["_common"]
  target = "lint-tools"
  tags = ["homelab-ruff:local"]
  output = ["type=docker"]
}

target "typecheck" {
  inherits = ["_common"]
  target = "typecheck"
  no-cache-filter = ["typecheck"]
}

target "ansible-lint" {
  inherits = ["_common"]
  target = "ansible-lint"
  no-cache-filter = ["ansible-lint"]
}

target "trust-render" {
  inherits = ["_common"]
  target = "trust-render"
  no-cache-filter = ["trust-render"]
}

target "trust-validate" {
  inherits = ["_common"]
  target = "trust-validate"
  no-cache-filter = ["trust-validate", "trust-config-rehearsal", "trust-credentials-rehearsal", "trust-recovery-rehearsal"]
}

target "trust-config-rehearsal" {
  inherits = ["_common"]
  target = "trust-config-rehearsal"
  no-cache-filter = ["trust-config-rehearsal", "trust-credentials-rehearsal", "trust-recovery-rehearsal"]
}

target "trust-credentials-rehearsal" {
  inherits = ["_common"]
  target = "trust-credentials-rehearsal"
  no-cache-filter = ["trust-credentials-rehearsal", "trust-recovery-rehearsal"]
}

target "trust-recovery-rehearsal" {
  inherits = ["_common"]
  target = "trust-recovery-rehearsal"
  no-cache-filter = ["trust-recovery-rehearsal"]
}
