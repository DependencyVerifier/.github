#!/usr/bin/env python3
"""Checks the machine-readable parts of docs/protocol.md.

1. Every schema is a valid JSON Schema 2020-12.
2. Every example validates against its schema (examples/<name>.json -> schemas/<name>.schema.json;
   examples/problem-*.json -> problem).
3. A few invalid messages are rejected, so that a schema cannot silently accept everything.
4. The test vectors verify with the public key only: signature base, Content-Digest, key id, and the
   Ed25519 signatures of the request and of the order (over its RFC 8785 canonical form).

Requires `jsonschema` and `cryptography`:

    docker run --rm -v "$PWD":/w -w /w python:3.13-slim sh -c \
        'pip install -q jsonschema cryptography && python docs/protocol/validate.py'
"""
import base64
import copy
import hashlib
import json
import pathlib
import re
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

HERE = pathlib.Path(__file__).parent
URN = 'urn:depverify:protocol:v1:'
failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(('ok    ' if ok else 'FAIL  ') + label)
    if not ok:
        failures.append(label)


def load(path: pathlib.Path):
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- schemas
schemas = {}
for path in sorted((HERE / 'schemas').glob('*.schema.json')):
    schema = load(path)
    name = path.name.removesuffix('.schema.json')
    check(schema.get('$id') == URN + name, f'schemas/{path.name}: $id is {URN}{name}')
    try:
        Draft202012Validator.check_schema(schema)
        check(True, f'schemas/{path.name}: valid JSON Schema 2020-12')
    except Exception as error:  # noqa: BLE001 - report every schema error
        check(False, f'schemas/{path.name}: {error}')
    schemas[name] = schema

registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas.values())


def errors(name: str, instance) -> list[str]:
    validator = Draft202012Validator(schemas[name], registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)
    return [f'{"/".join(map(str, e.absolute_path)) or "<root>"}: {e.message}' for e in validator.iter_errors(instance)]


# --------------------------------------------------------------------------- examples
examples = {}
for path in sorted((HERE / 'examples').glob('*.json')):
    stem = path.stem
    name = 'problem' if stem.startswith('problem-') else stem
    if name not in schemas:
        check(False, f'examples/{path.name}: no schema named {name}')
        continue
    instance = load(path)
    examples[stem] = instance
    found = errors(name, instance)
    check(not found, f'examples/{path.name} validates against {name}' + ''.join(f'\n        {e}' for e in found))

used = {'problem' if s.startswith('problem-') else s for s in examples} | {'common', 'signed-order'}
for name in sorted(set(schemas) - used):
    check(False, f'schemas/{name}.schema.json has no example')


# --------------------------------------------------------------------------- invalid messages
def mutated(stem: str, change):
    instance = copy.deepcopy(examples[stem])
    change(instance)
    return instance


negatives = [
    ('enrollment-request', 'container mode without scope', mutated('enrollment-request', lambda m: m.pop('scope'))),
    ('enrollment-request', 'compose scope without compose_project', mutated('enrollment-request', lambda m: m.pop('compose_project'))),
    ('enrollment-request', 'public key that is not ed25519', mutated('enrollment-request', lambda m: m.update(public_key='rsa:AAAA'))),
    ('poll-request', 'rejected order result without reason', mutated('poll-request', lambda m: m['order_results'][1].pop('reason'))),
    ('poll-response', 'orders while pending', mutated('poll-response', lambda m: m.update(status='pending'))),
    ('poll-response', 'unknown order type', mutated('poll-response', lambda m: m['orders'][0]['order'].update(type='RUN_SHELL'))),
    ('poll-response', 'SET_CONFIG with an extra payload field', mutated('poll-response', lambda m: m['orders'][0]['order']['payload'].update(command='id'))),
    ('poll-response', 'next_poll_in below 30', mutated('poll-response', lambda m: m.update(next_poll_in=5))),
    ('inventory-manifest', 'subject with fields of another kind', mutated('inventory-manifest', lambda m: m['subjects'][3].update(kind='container'))),
    ('inventory-manifest', 'host subject with a path', mutated('inventory-manifest', lambda m: m['subjects'][0].update(path='/'))),
    ('inventory-manifest', 'host subject under another key', mutated('inventory-manifest', lambda m: m['subjects'][0].update(subject_key='host:web-01'))),
    ('inventory-manifest', 'host_facts referencing an SBOM media type', mutated('inventory-manifest', lambda m: m['host_facts'].update(media_type='application/vnd.cyclonedx+json;version=1.6'))),
    ('inventory-manifest', 'relative declared path', mutated('inventory-manifest', lambda m: m['subjects'][3].update(path='opt/legacy-app'))),
    ('host-facts', 'timestamp in host facts', mutated('host-facts', lambda m: m.update(collected_at='2026-11-09T08:01:10Z'))),
    ('problem', 'clock_skew without server_time', mutated('problem-clock-skew', lambda m: m.pop('server_time'))),
    ('problem', 'missing_snapshots without missing', mutated('problem-missing-snapshots', lambda m: m.pop('missing'))),
    ('problem', 'type outside the urn:depverify:problem namespace', mutated('problem-clock-skew', lambda m: m.update(type='about:blank'))),
]
for name, label, instance in negatives:
    check(bool(errors(name, instance)), f'{name} rejects: {label}')


# --------------------------------------------------------------------------- spec ↔ schema consistency
spec = (HERE.parent / 'protocol.md').read_text()
errors_section = spec.split('\n## 9.', 1)[1].split('\n## 10.', 1)[0]
documented = {
    code
    for line in errors_section.splitlines() if line.startswith('| `')
    for code in re.findall(r'`([a-z_]+)`', line.split('|')[1])
}
schema_codes = {t.removeprefix('urn:depverify:problem:') for t in schemas['problem']['properties']['type']['enum']}
check(documented == schema_codes, 'problem codes of protocol.md §9 match problem.schema.json'
      + (f' (only in spec: {sorted(documented - schema_codes)}, only in schema: {sorted(schema_codes - documented)})'
         if documented != schema_codes else ''))


# --------------------------------------------------------------------------- test vectors
def public_key(encoded: str) -> tuple[Ed25519PublicKey, bytes]:
    assert encoded.startswith('ed25519:')
    raw = base64.b64decode(encoded.removeprefix('ed25519:'))
    return Ed25519PublicKey.from_public_bytes(raw), raw


def fingerprint(raw: bytes) -> str:
    return 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')


def verifies(key: Ed25519PublicKey, signature: bytes, message: bytes) -> bool:
    try:
        key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


# Request signature (RFC 9421 profile depverify-agent-v1), rebuilt from the headers as the console would.
vector = load(HERE / 'test-vectors' / 'request-signature.json')
request, headers = vector['request'], vector['request']['headers']
key, raw = public_key(vector['agent_public_key'])
check(fingerprint(raw) == vector['keyid'], 'request vector: keyid is the fingerprint of the agent key')

body = request['body'].encode()
digest = 'sha-256=:' + base64.b64encode(hashlib.sha256(body).digest()).decode() + ':'
check(headers['Content-Digest'] == digest, 'request vector: Content-Digest matches the body')
check(errors('poll-request', json.loads(body)) == [], 'request vector: body is a valid poll request')

label, params = headers['Signature-Input'].split('=', 1)
check(label == 'sig1' and params.startswith('("@method" "@target-uri" "content-digest" "date");'),
      'request vector: covered components are the fixed profile')
check(';tag="depverify-agent-v1"' in params and ';alg="ed25519"' in params and f';keyid="{vector["keyid"]}"' in params,
      'request vector: tag, alg and keyid parameters')
base = '\n'.join([
    f'"@method": {request["method"]}',
    f'"@target-uri": {request["target_uri"]}',
    f'"content-digest": {headers["Content-Digest"]}',
    f'"date": {headers["Date"]}',
    f'"@signature-params": {params}',
])
check(base == vector['signature_base'], 'request vector: signature base rebuilt from the headers')
sig_label, sig_value = headers['Signature'].split('=', 1)
signature = base64.b64decode(sig_value.strip(':'))
check(sig_label == 'sig1' and verifies(key, signature, base.encode()), 'request vector: Ed25519 signature verifies')
check(not verifies(key, signature, base.replace('/poll', '/enrollments').encode()), 'request vector: signature fails on another target')

# Order signature (Ed25519 over the RFC 8785 canonical form of `order`).
vector = load(HERE / 'test-vectors' / 'order-signature.json')
signed = vector['signed_order']
key, raw = public_key(vector['console_public_key'])
check(fingerprint(raw) == signed['signature']['key_id'], 'order vector: key_id is the fingerprint of the console key')
canonical = json.dumps(signed['order'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
check(canonical == vector['canonical_order'], 'order vector: canonical form (RFC 8785)')
signature = b64url_decode(signed['signature']['value'])
check(verifies(key, signature, canonical.encode()), 'order vector: Ed25519 signature verifies')
tampered = dict(signed['order'], agent_id='019a6b2c-1f00-7a11-8b22-3c44d55e6f02')
check(not verifies(key, signature, json.dumps(tampered, sort_keys=True, separators=(',', ':')).encode()),
      'order vector: signature fails for another agent_id')
check(examples['poll-response']['orders'][0] == signed, 'examples/poll-response.json carries the signed order of the vector')

print()
if failures:
    print(f'{len(failures)} check(s) failed')
    sys.exit(1)
print('all checks passed')
