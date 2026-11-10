# Cloudflare DNS-01 for Trust KMS

Certbot on `ups-aux` owns certificate issuance for
`kms.k8s-aux.simlun.se`. It works independently of Trust, OpenBao, and
cert-manager. Let’s Encrypt validates a TXT record in **public Cloudflare DNS**.
The [separate UniFi A record](../network.md#required-dns-entries) resolves the
service to `10.10.0.5` on the LAN. The DNS-01 challenge does not require a
public inbound listener.

## Cloudflare configuration

1. Use the authoritative `simlun.se` zone in Cloudflare.
2. Create a dedicated **API token** for the coordinator, using **Zone → DNS →
   Edit** and **Zone Resources → Include → Specific zone → simlun.se**. That
   grants DNS write access throughout this zone. Cloudflare's token scope is
   the zone. Use the dedicated token with Certbot's Cloudflare plugin.
3. [Wrap and store the coordinator token](#wrap-and-store-the-coordinator-token)
   before running the staging rehearsal.
4. Reserve `_acme-challenge.kms.k8s-aux.simlun.se` for Certbot. Certbot adds
   and removes the temporary TXT value during validation. Keep the owner
   available for that workflow.
5. When Trust cert-manager is set up, issue a separate API token scoped to
   `simlun.se` with **Zone → DNS → Edit** and **Zone → Zone → Read**. Give
   cert-manager its own ACME account and renewal state. It will issue for
   application names using distinct challenge records. Both tokens have
   zone-wide DNS write access. Let’s Encrypt registered-domain limits apply
   across both accounts.

[Cloudflare token setup](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) ·
[Certbot Cloudflare plugin](https://github.com/certbot/certbot/blob/v4.0.0/certbot-dns-cloudflare/certbot_dns_cloudflare/__init__.py) ·
[cert-manager Cloudflare solver](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/) ·
[Let’s Encrypt rate limits](https://letsencrypt.org/docs/rate-limits/)

### Coordinator token policy reference

The coordinator token is named `homelab-ups-aux-dns`. The following Terraform
example was supplied by Cloudflare's UI when the operator created it. It
records the account, zone and DNS Edit permission identifiers; it contains
no token value and is safe to keep in this public repository. This is a
reference example, not a managed Terraform deployment. Applying it would
create another token.

```hcl
resource "cloudflare_account_token" "example_account_token" {
  account_id = "e6d011dde11a8647d3d5566992b4663c"
  name       = "homelab-ups-aux-dns"

  policies = [{
    effect = "allow"
    permission_groups = [{
      id = "4755a26eedb94da69e1066d98aa820be"
    }]
    resources = jsonencode({
      "com.cloudflare.api.account.zone.a74ff6069ccd972dde8045f939b14427" = "*"
    })
  }]
}
```

The provider's generated [`value` attribute](https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/account_token)
is the secret. Do not publish that value or Terraform state/plan files.
[Marking a value sensitive](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
does not remove it from Terraform state. Any future Terraform implementation
must meet the existing secret-storage policy before managing tokens.

### Wrap and store the coordinator token

From the homelab repository root, install the [HSM tools](../../support/hsm/README.md)
and prepare the private `homelab-secrets` submodule at `secrets/wrapped`.
Use the YubiKey-backed hidden prompt to wrap and verify the real token.

```sh
git submodule update --init --recursive -- secrets/wrapped
git -C secrets/wrapped fetch origin
git -C secrets/wrapped switch main
git -C secrets/wrapped pull --ff-only origin main

"$HOME/.local/share/homelab/venvs/hsm/bin/homelab-wrap" \
  --key-id homelab/v1/support-aux/dns-api/cloudflare/r1 \
  --root-key golden-1 --output secrets/wrapped/ups-aux-cloudflare-dns-api.json
```

Review the new ciphertext record, then commit that file in the private
submodule and push its `main` branch before updating the parent pointer.

```sh
git -C secrets/wrapped add -- ups-aux-cloudflare-dns-api.json
git -C secrets/wrapped commit -m "Store wrapped ups-aux Cloudflare DNS token"
git -C secrets/wrapped push origin main
```

The public [manifest](../../secrets/manifest.json) reserves the filename.
Follow the [submodule update workflow](../security/encrypted-record-storage.md#checkout-and-updates)
to record the new pointer in the parent. Keep the plaintext token out of
the terminal transcript, shell history and both repositories.

### Verify public DNS

Record the current public DNS state before starting the rehearsal:

```sh
dig +short NS simlun.se
dig @1.1.1.1 _acme-challenge.kms.k8s-aux.simlun.se TXT +short
```

For a closer look during validation, query one of the authoritative
nameservers printed by the first command. Repeat the TXT query after the
rehearsal and confirm it has returned to the original state. Public resolver
caches can briefly retain the TXT value. If an interrupted run leaves a
record, remove only the confirmed rehearsal record in Cloudflare after
checking that no challenge is running.

## Run the staging rehearsal

This stage uses Let's Encrypt **staging** and discards the account and certificate
after the test. The systemd job creates a private, non-swappable tmpfs, checks
the effective mount and coordinator hardening before reading the token, and
routes Certbot's config, work and logs into the workspace. The job reports only
public progress and results. See the [approved coordinator exception](../security/coordinator-sessions.md#workstation-authorization).

1. Complete coordinator hardening and load the shared SSH key. Install the
   APT-packaged Certbot and Cloudflare plugin and the staging launcher:

   ```sh
   make -C support/ups kms-acme-tools HOST=ups-aux
   ```

2. Run the staging issue and renewal test with your ACME contact email.
   The command reads the wrapped token created above by default.

   ```sh
   make -C support/ups kms-acme-rehearse HOST=ups-aux ACME_EMAIL=you@example.org
   ```

The workstation unwraps after a YubiKey touch and streams the token over
host-verified SSH. Expect a fresh staging certificate after renewal with the
same TLS public key, followed by workspace removal. A cached ACME authorization
may allow renewal without a second TXT write. The existing locked KMS service
continues to expose its local status socket throughout this test. Production
certificates, restart recovery, the renewal timer and the TCP listener
remain pending after the verified staging rehearsal.

The manual rehearsal disables Certbot's randomized renewal delay, which can
otherwise last up to eight minutes. Each Certbot operation has a 150-second
deadline; the systemd job has a six-minute limit. A failure identifies issuance
or renewal and reports a timeout, an exit status, or a launch failure. Certbot's
stdout/stderr remain suppressed; its private logs are removed with the
disposable RAM workspace. After updating the helper, rerun `kms-acme-tools`
before retrying `kms-acme-rehearse`.

## Verified staging result (2026-11-10)

The operator completed the rehearsal on `ups-aux` using the wrapped
`homelab-ups-aux-dns` token and contact email `acme@simlun.se`. The helper
reported successful staging issuance and renewal with the same TLS key,
followed by removal of the disposable ACME workspace. The subsequent command
`dig @1.1.1.1 _acme-challenge.kms.k8s-aux.simlun.se TXT +short` returned no
records. The earlier renewal failure was followed by a successful rerun after
[PR #23](https://github.com/simlun-ai/homelab/pull/23).

This acceptance covers staging only. Durable wrapped ACME state recovery,
production issuance, scheduled renewal and the TLS listener remain pending.

## Wrapped staging state: initialize, recover and recreate

The coordinator is the sole durable home for ACME/TLS ciphertext and its
archives. The Cloudflare token remains in the private `homelab-secrets`
repository. Losing the Pi SD card means explicitly recreating the ACME/TLS
identity using that token and working DNS/ACME services; these records do not
need Git backups. Node KMS keys and Talos authority keep their existing custody.

The earlier checkout-based staging lifecycle was verified by the operator on
2026-11-11: initialization, recovery/renewal, explicit recreation and recovery
of the replacement all passed, with three previous ciphertexts archived. The
revised coordinator-local workflow is implemented but requires fresh operator
validation. Production issuance, a listener and a renewal timer remain pending.

Install the updated helpers:

```sh
make -C support/ups kms-acme-tools HOST=ups-aux
```

### Move the existing staging record to the Pi

From the homelab root, import the existing record after YubiKey verification.
This refuses an existing coordinator record, preserves the exact ciphertext,
and does not contact ACME, modify local files, or commit anything:

```sh
make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=acme@simlun.se \
  ACME_STATE_MODE=import \
  ACME_IMPORT_RECORD="$PWD/secrets/wrapped/ups-aux-acme-staging.json"
```

Only the current record is imported; old workstation archives remain unchanged.
Do not commit those obsolete ACME staging files to the private repository.
After coordinator recovery succeeds, review and remove the old local staging
copies deliberately. The helper never deletes local files or rewrites Git
history. If previously committed, removing current files does not erase history;
no history rewrite is needed for these already wrapped staging records.

### Validate coordinator-local recovery and recreation

If there is no existing record to import, initialize once instead:

```sh
make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=acme@simlun.se ACME_STATE_MODE=init
```

Then run default recovery, explicit recreation, and recovery of the replacement:

```sh
make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=acme@simlun.se
make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=acme@simlun.se ACME_STATE_MODE=recreate
make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=acme@simlun.se
```

Expect fresh YubiKey touches for state recovery, DNS token recovery, wrapping
and independent unwrap verification. Each operation fetches the Pi's ciphertext
over host-verified SSH. Unwrapped state travels back over SSH to protected Pi
RAM; newly wrapped state goes back to the Pi after verification. No ACME state
files are written in the workstation checkout and no submodule pointer update
is needed. The private checkout is still required for the separate DNS token.
Recovery verifies renewal retains both account and TLS keys. For this staging
acceptance, the recovered certificate must still be valid. Missing or corrupt
state never silently triggers recreation. Recreate explicitly replaces identity;
if no old record exists, it reports that there is nothing to archive.

### Storage and failure handling

The tools play provisions root-owned mode `0700`
`/var/lib/trust-kms/acme-staging/`. The current file is
`ups-aux-acme-staging.json`; previous ciphertexts are retained byte-for-byte in
`archive/ups-aux-acme-staging-<generation>.json`. The staging wrapping context
remains `homelab/v1/support-aux/acme/staging/r1`, root `golden-1`.

The workstation wraps and independently unwraps the replacement before sending
it to the Pi. The Pi locks its store and compares the current record with the
one fetched at the start, rejecting stale workstation updates. It validates
record structure/context, archives the previous ciphertext, fsyncs, and replaces
the current record atomically. It holds neither a wrapping key nor HMAC response.
Archive failure prevents replacement. Failed issuance or verification never
publishes. If publication acknowledgement is lost or storage fails after the
atomic replacement, inspect the coordinator before retrying; an extra archive
copy can remain. There is no automatic archive pruning.

Only Certbot's config tree is wrapped. The separate Cloudflare credential,
work files and logs are excluded. A fixed directory inside the private `noswap`
RAM mount preserves Certbot's absolute renewal paths. Snapshot size/format and
link/path checks still apply. The transient service removes plaintext state at
the end; the next invocation reconstructs it from coordinator-local ciphertext.
This model supports the future process-lifetime authorization flow, without
requiring GitHub or OpenBao for local ACME-state retrieval.
