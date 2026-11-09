# Parent helper dependencies

`make -C support/hsm tools` installs the HSM submodule's committed wheel bundle,
then the parent-owned YAML parser from `wheels/` with hashes enforced by
`requirements.txt`. Installation requires no network. Crypto/token pins remain
owned by homelab-hsm; the parent declares PyYAML in its `pyproject.toml`.

The pure-Python PyYAML 6.0.3 wheel supports both parent Python versions and
operator architectures without a native extension. It was built from the
[upstream PyPI source distribution](https://pypi.org/project/PyYAML/6.0.3/#files),
SHA-256 `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f`:

```sh
PYYAML_FORCE_LIBYAML=0 python3 -m pip wheel --no-deps --no-build-isolation \
  --no-cache-dir --no-binary=PyYAML --wheel-dir support/hsm/wheels PyYAML==6.0.3
```

Build preparation is online and needs setuptools and wheel. Wheel bytes can
vary with build timestamps/tool versions; a deliberate rebuild requires updating
the lock hash and testing offline installation on supported Python versions.
The wheel includes upstream MIT license metadata. No source build runs during
installation. PyYAML is used only through safe loading; native Talos tooling
continues to own generation, signing and machine validation.

## Trust KMS loopback rehearsal

After the offline helper environment is installed, fetch the pinned rehearsal
dependencies once, then run the test:

```sh
make -C support/hsm kms-rehearsal-tools
make -C support/hsm kms-tls-rehearse
```

The rehearsal creates its certificate and disposable key material in memory,
binds an ephemeral port on loopback, and exercises the Talos KMS wire contract.
It requires no token, wrapped records, coordinator, or internet access at run
time. See the [KMS contract](../../docs/security/trust-bootstrap-kms.md#disposable-loopback-transport).
