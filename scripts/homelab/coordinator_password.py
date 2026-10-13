"""Per-host console passwords; only authenticated ciphertext is written locally."""
import argparse
import hmac
import os
from pathlib import Path
import re
import secrets
import subprocess

from . import wrapping

HOSTS = ('ups-aux', 'ups-pi', 'ups-metal')
ROOT_KEY = 'golden-1'
REPO = Path(__file__).resolve().parents[2]


def context(host):
    if host not in HOSTS:
        raise ValueError('Unknown coordinator')
    return f'homelab/v1/{host}/local-password/administrator/r1'


def record_path(host, repo=REPO):
    context(host)
    return repo / 'secrets/wrapped' / f'{host}-administrator.json'


def create(host, respond, repo=REPO):
    path = record_path(host, repo)
    if path.exists():
        raise FileExistsError('Record already exists; reuse it')
    password = secrets.token_urlsafe(32).encode('ascii')
    encoded = wrapping.wrap(password, context(host), ROOT_KEY, 1, respond)
    recovered = wrapping.unwrap(encoded, context(host), ROOT_KEY, respond)
    if not hmac.compare_digest(password, recovered):
        raise ValueError('Verification failed')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents a concurrent run from overwriting a record.
    with path.open('xb') as target:
        target.write(encoded + b'\n')
        target.flush()
        os.fsync(target.fileno())


def recover(host, respond, repo=REPO):
    with record_path(host, repo).open('rb') as source:
        encoded = source.read(wrapping.MAX_RECORD + 1)
    password = wrapping.unwrap(encoded, context(host), ROOT_KEY, respond)
    if not re.fullmatch(rb'[A-Za-z0-9_-]{43}', password):
        raise ValueError('Invalid password payload')
    return password


def apply(host, password):
    context(host)
    if not re.fullmatch(rb'[A-Za-z0-9_-]{43}', password):
        raise ValueError('Invalid password payload')
    subprocess.run(
        ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
         '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
         f'administrator@{host}', 'sudo -n /usr/sbin/chpasswd'],
        input=b'administrator:' + password + b'\n',
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        timeout=60,
    )


def main():
    from .yubikey_setup import harden, token, respond, require_no_response_without_touch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'reveal', 'apply'))
    parser.add_argument('--host', required=True, choices=HOSTS)
    args = parser.parse_args()
    harden()
    if args.action == 'create' and record_path(args.host).exists():
        print('Record already exists; use reveal or apply. Creation never overwrites it.')
        return
    if args.action == 'reveal':
        if input('Display password in this unrecorded terminal? Type reveal: ') != 'reveal':
            return
    with token() as session:
        require_no_response_without_touch(session)
        response = lambda challenge: respond(session, challenge)
        if args.action == 'create':
            create(args.host, response)
            print('Verified wrapped record created. Commit it and refresh recovery USB clones.')
        else:
            password = recover(args.host, response)
            if args.action == 'reveal':
                print(password.decode('ascii'))
            else:
                apply(args.host, password)
                print('Administrator password applied. Verify local console login.')
