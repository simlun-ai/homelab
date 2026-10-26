group "default" {
  targets = ["lint", "typecheck", "ansible-lint", "helpers", "ups", "syntax"]
}

group "ci" {
  targets = ["lint", "typecheck", "ansible-lint", "helpers", "ups", "syntax"]
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
