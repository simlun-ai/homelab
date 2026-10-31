# Continuous integration

From the repository root:

```sh
git submodule update --init --recursive -- tools/homelab-hsm
make ci
```

Prerequisites: GNU Make and Docker with Buildx/BuildKit. Checks run in Ubuntu
26.04 `linux/amd64` containers with its default Python; ARM hosts need amd64
emulation configured in the builder. No host Python environment is required.
Docker needs network access for base images, the Dockerfile frontend, OS packages,
and Python dependencies during preparation.

`docker-bake.hcl` runs six targets in parallel:

| Target | Checks |
| --- | --- |
| `lint` | Pinned Ruff lint and formatting checks across parent Python in `scripts/`, `tests/`, `support/`, and `ci/`. |
| `typecheck` | Pinned strict Pyright across all parent Python, targeting Python 3.13 on Linux and resolving the pinned HSM library source. |
| `ansible-lint` | Pinned Ansible lint with the `safety` profile across UPS playbooks, tasks, role, and inventory. |
| `helpers` | Offline hashed-wheel installation into `/opt/homelab-hsm`; `pip check`; parent unit/integration tests and component unit tests through `make -C support/hsm test`. |
| `ups` | Pinned Ansible environment, exact tool-version checks, inventory parsing, and all playbook syntax checks through the UPS Makefile. |
| `syntax` | Parent Python compilation and `bash -n`, including standalone support scripts. Checked scripts are not executed. |

Run one target with `docker buildx bake --file docker-bake.hcl --progress=plain helpers`
(substitute `ups` or `syntax`). OS/dependency preparation is cached; Bake always
executes check stages. Checks run with networking disabled. Images remain in the
build cache; nothing is loaded or published.

Only the public code submodule is required. `.dockerignore` allowlists validation
inputs and excludes private records, Git metadata, local environments, and offline
wheelhouses. The helper stage asserts that `secrets/wrapped` is absent. Tests use
public disposable key material and temporary Git fixtures, without a YubiKey,
SSH agent, or coordinator connections. Ansible is parsed and syntax checked;
provisioning, hardware behavior, and deployment verification remain manual.

GitHub Actions initializes only the pinned code submodule, configures Buildx,
and runs exactly `make ci`. No additional credentials or repository secrets are
needed.

## Python linting and formatting

Run `make lint` for the same Ruff checks used by `make ci`. Run `make format`
to apply safe fixes and formatting in the same pinned tool image, writing as
your host UID/GID. These targets do not require the code or records submodules.
They check parent Python only; `homelab-hsm` keeps its own configuration and CI.

`pyproject.toml` configures Python 3.13 compatibility, 88-character formatting,
and basic errors, unused code, import ordering, modernization, and common-bug
rules (`E4`, `E7`, `E9`, `F`, `I`, `UP`, `B`), matching the HSM project's policy.
Ruff is pinned to 0.17.2 in its tool stage and enforced by `required-version`.
It is not installed into either operational environment.

## Python type checking

Run `make typecheck` for the same strict Pyright check used by `make ci`.
Like the helper tests, this needs the public code submodule initialized, but
no private records or hardware. `pyproject.toml` covers `scripts/`, `tests/`,
`support/`, and `ci/`, targeting the minimum Python 3.13 on Linux even though
the check runs in Ubuntu 26.04's Python environment. Extra import paths expose
the pinned HSM source's annotations to check the parent/library boundary;
the component retains its own checking policy and CI.

The build pins Pyright 1.1.414 and Node 24.19.0, matching the HSM pipeline.
It reuses the helper dependency environment; neither tool is installed into
an operational environment. Dependency preparation has network access;
the check itself runs with networking disabled.

## Ansible linting

Run `make ansible-lint` for the same check used by `make ci`. It needs Docker
and Make, without either submodule, SSH credentials, or coordinator access.
The Ubuntu 26.04 tool stage installs `ci/ansible-lint-requirements.txt` alongside
the exact `support/ups/requirements.txt` pins in a separate virtual environment.
Operational environments are unchanged.

The check runs from `support/ups/`, using its `ansible.cfg` and `.ansible-lint`.
It covers `ansible/` and `inventory.yaml` with the `safety` profile; warnings
also fail the build. There is no baseline ignore file or blanket rule skip.
Network access is disabled during linting, and offline mode prevents dependency
installation and schema refreshes. The existing UPS inventory and four playbook
syntax checks remain independent checks; linting does not execute playbooks.
