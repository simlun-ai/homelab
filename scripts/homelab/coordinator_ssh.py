"""One repository-owned Ed25519 identity, wrapped at rest and loaded via stdin."""
import argparse
import hmac
import os
from pathlib import Path
import subprocess

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
    load_ssh_private_key, load_ssh_public_key,
)
from . import wrapping

REPO = Path(__file__).resolve().parents[2]
KEY_ID = 'homelab/v1/ups-coordinators/ssh-private-key/administrator/r1'
ROOT_KEY = 'golden-1'
RECORD = Path('secrets/wrapped/coordinators-ssh-ed25519.json')
PUBLIC = Path('support/ups/coordinator_ed25519.pub')


def public_bytes(key):
    return key.public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)


def read_public(repo=REPO):
    data = (repo / PUBLIC).read_bytes()
    if len(data) > 1024 or len(data.splitlines()) != 1:
        raise ValueError('Expected a single public key')
    key = load_ssh_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('Expected Ed25519')
    return public_bytes(key)


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())


def recover(respond, repo=REPO):
    with (repo / RECORD).open('rb') as source:
        encoded = source.read(wrapping.MAX_RECORD + 1)
    private = wrapping.unwrap(encoded, KEY_ID, ROOT_KEY, respond)
    key = load_ssh_private_key(private, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Expected an unencrypted Ed25519 private key')
    return private, public_bytes(key.public_key())


def create(respond, repo=REPO):
    if (repo / RECORD).exists() or (repo / PUBLIC).exists():
        raise FileExistsError('Reuse existing key; creation never overwrites')
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
    public = public_bytes(key.public_key())
    encoded = wrapping.wrap(private, KEY_ID, ROOT_KEY, 1, respond)
    verified = wrapping.unwrap(encoded, KEY_ID, ROOT_KEY, respond)
    if not hmac.compare_digest(private, verified):
        raise ValueError('Wrapping verification failed')
    # Persist verified ciphertext first; public can be recovered if interrupted.
    write_new(repo / RECORD, encoded + b'\n')
    write_new(repo / PUBLIC, public + b' homelab-coordinators\n')


def restore_public(respond, repo=REPO):
    _, public = recover(respond, repo)
    write_new(repo / PUBLIC, public + b' homelab-coordinators\n')


def agent(*args, **kwargs):
    if not os.environ.get('SSH_AUTH_SOCK'):
        raise RuntimeError('Start a local ssh-agent first')
    subprocess.run(['ssh-add', *args], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=15, **kwargs)


def check(repo=REPO):
    read_public(repo)
    agent('-T', str(repo / PUBLIC))


def load(respond, repo=REPO):
    expected = read_public(repo)
    private, public = recover(respond, repo)
    if not hmac.compare_digest(expected, public):
        raise ValueError('Private/public key mismatch')
    # No private-key file, argv, environment value, or captured output.
    agent('-t', '1h', '-', input=private)
    check(repo)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'load', 'check', 'unload', 'public'))
    args = parser.parse_args()
    if args.action == 'check':
        check()
    elif args.action == 'unload':
        read_public()
        agent('-d', str(REPO / PUBLIC))
        print('Coordinator key removed from this agent.')
    else:
        from .yubikey_setup import harden, token, respond, require_no_response_without_touch
        harden()
        with token() as session:
            require_no_response_without_touch(session)
            response = lambda challenge: respond(session, challenge)
            {'create': create, 'load': load, 'public': restore_public}[args.action](response)
        print({'create': 'Key created and verified. Commit ciphertext and public key; refresh recovery clones.',
               'load': 'Coordinator key loaded into this agent for one hour.',
               'public': 'Public key restored from the wrapped private key.'}[args.action])
