group "default" {
  targets = ["helpers", "ups", "syntax"]
}

group "ci" {
  targets = ["helpers", "ups", "syntax"]
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
