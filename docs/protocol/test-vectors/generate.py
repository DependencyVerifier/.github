#!/usr/bin/env python3
"""Generates the test vectors of docs/protocol.md: request-signature.json and order-signature.json.

Deterministic: fixed RFC 8032 seeds, fixed messages. Ed25519 signatures are deterministic, so running it
again rewrites the same files. Requires `cryptography`:

    docker run --rm -v "$PWD":/w -w /w python:3.13-slim sh -c \
        'pip install -q cryptography && python docs/protocol/test-vectors/generate.py'
"""
import base64
import hashlib
import json
import pathlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

HERE = pathlib.Path(__file__).parent


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def keypair(seed_hex: str) -> tuple[Ed25519PrivateKey, bytes]:
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    return key, key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def fingerprint(public: bytes) -> str:
    """Key fingerprint and key id: SHA-256 of the raw 32-byte public key, standard base64, no padding (as SSH)."""
    return 'SHA256:' + b64(hashlib.sha256(public).digest()).rstrip('=')


def jcs(value) -> bytes:
    """RFC 8785 canonical JSON. Equivalent to sorted keys + no whitespace for the value types the protocol
    signs (strings, integers, booleans, arrays, objects; no floats)."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def write(name: str, vector: dict) -> None:
    (HERE / name).write_text(json.dumps(vector, indent=2, ensure_ascii=False) + '\n')
    print(f'wrote {name}')


# --------------------------------------------------------------------------- agent request signature
AGENT_SEED = '9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60'  # RFC 8032 §7.1, test 1
agent_key, agent_public = keypair(AGENT_SEED)
keyid = fingerprint(agent_public)

body = json.dumps({'protocol_version': 1, 'agent_version': '0.1.0', 'order_results': []}, separators=(',', ':')).encode()
content_digest = f'sha-256=:{b64(hashlib.sha256(body).digest())}:'
method, target = 'POST', 'https://console.example.com/agent/v1/poll'
date = 'Mon, 09 Nov 2026 08:00:00 GMT'
created = 1794211200  # 2026-11-09T08:00:00Z
expires = created + 300
nonce = b64url(bytes.fromhex('6b0f3d1c9a2e4b7f8c5d1e2f3a4b5c6d'))  # 16 random bytes in real requests

params = (
    '("@method" "@target-uri" "content-digest" "date")'
    f';created={created};expires={expires};keyid="{keyid}";alg="ed25519";nonce="{nonce}";tag="depverify-agent-v1"'
)
signature_base = '\n'.join([
    f'"@method": {method}',
    f'"@target-uri": {target}',
    f'"content-digest": {content_digest}',
    f'"date": {date}',
    f'"@signature-params": {params}',
])
request_signature = agent_key.sign(signature_base.encode())

write('request-signature.json', {
    'description': 'Signed POST /agent/v1/poll, signature profile depverify-agent-v1 (RFC 9421, ed25519).',
    'agent_private_key_seed_hex': AGENT_SEED,
    'agent_public_key': 'ed25519:' + b64(agent_public),
    'keyid': keyid,
    'request': {
        'method': method,
        'target_uri': target,
        'headers': {
            'Content-Type': 'application/json',
            'Date': date,
            'Content-Digest': content_digest,
            'Signature-Input': f'sig1={params}',
            'Signature': f'sig1=:{b64(request_signature)}:',
        },
        'body': body.decode(),
    },
    'signature_base': signature_base,
})

# --------------------------------------------------------------------------- console order signature
CONSOLE_SEED = '4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb'  # RFC 8032 §7.1, test 2
console_key, console_public = keypair(CONSOLE_SEED)

order = {
    'order_id': '019a6b2e-7c40-7d3e-9f1a-2b3c4d5e6f70',
    'type': 'SET_CONFIG',
    'agent_id': '019a6b2c-1f00-7a11-8b22-3c44d55e6f01',
    'issued_at': '2026-11-09T08:00:00Z',
    'not_before': '2026-11-09T08:00:00Z',
    'expires_at': '2026-11-09T08:15:00Z',
    'payload': {
        'config_version': 3,
        'scan_interval_minutes': 360,
        'discovery_roots': ['/var/www', '/srv'],
        'declared_paths': ['/opt/legacy-app'],
        'exclusions': ['/var/www/**/node_modules/.cache'],
    },
}
canonical = jcs(order)
order_signature = console_key.sign(canonical)

write('order-signature.json', {
    'description': 'SET_CONFIG order signed by the console: Ed25519 over the RFC 8785 canonical JSON of `order`.',
    'console_private_key_seed_hex': CONSOLE_SEED,
    'console_public_key': 'ed25519:' + b64(console_public),
    'signed_order': {
        'order': order,
        'signature': {'alg': 'ed25519', 'key_id': fingerprint(console_public), 'value': b64url(order_signature)},
    },
    'canonical_order': canonical.decode(),
})
