"""Validate an original offline export for deliberate administrator registration.

This is not an importer for arbitrary user-supplied baselines. The expected
manifest digest must come from the trusted exporter through a separate channel.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta

from .comparison import compare_rows
from .constants import EDITABLE, MAX_EXPANDED, MAX_ROWS, SCHEMA
from .workbook import parse_workbook


def validate_offline_batch(manifest_bytes, workbook_bytes, expected_sha256):
    if not isinstance(manifest_bytes, bytes) or len(manifest_bytes) > MAX_EXPANDED:
        raise ValueError('Invalid or oversized offline manifest.')
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('Supply the manifest SHA256 from the trusted exporter.')
    if not hmac.compare_digest(hashlib.sha256(manifest_bytes).hexdigest(), expected_sha256.lower()):
        raise ValueError('The offline manifest does not match the trusted digest.')
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get('format') != 'sample-excel-sync/offline-batch/1':
        raise ValueError('Unsupported offline manifest format.')
    for name in ('request_id', 'company_id', 'user_id'):
        if type(manifest.get(name)) is not int or manifest[name] <= 0:
            raise ValueError('Invalid offline owner/request identity.')
    for name in ('database', 'request_name', 'user_login'):
        if not isinstance(manifest.get(name), str) or not 1 <= len(manifest[name]) <= 256:
            raise ValueError('Missing offline database/request/owner identity.')
    if manifest.get('schema') != SCHEMA or not re.fullmatch(r'[A-Za-z0-9_-]{32,100}', manifest.get('token', '')):
        raise ValueError('Unsupported offline layout or export token.')
    issued = datetime.strptime(manifest['exported_at'], '%Y-%m-%d %H:%M:%S')
    expiry = datetime.strptime(manifest['expires_at'], '%Y-%m-%d %H:%M:%S')
    if not issued < expiry <= issued + timedelta(days=90):
        raise ValueError('Offline export validity must not exceed 90 days.')
    if hashlib.sha256(workbook_bytes).hexdigest() != manifest.get('workbook_sha256'):
        raise ValueError('Register only the original unedited export, not a factory-returned file.')
    token, submitted, schema = parse_workbook(workbook_bytes, include_schema=True)
    payload = manifest.get('payload')
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA or schema != SCHEMA or token != manifest['token']:
        raise ValueError('Workbook and offline batch metadata do not match.')
    rows = payload.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS or len(rows) != len(submitted):
        raise ValueError('Offline export row count does not match.')
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get('line_id')) is not int or row['line_id'] <= 0 or row['line_id'] in ids:
            raise ValueError('Duplicate or invalid original sample line identity.')
        ids.add(row['line_id'])
        identity = row.get('identity')
        if not isinstance(identity, dict) or identity.get('request_id') != manifest['request_id']:
            raise ValueError('An offline line belongs to a different request.')
        for name in ('supplier_id', 'product_tmpl_id'):
            value = identity.get(name)
            if value is not False and (type(value) is not int or value <= 0):
                raise ValueError('Invalid original product/factory identity.')
        if any(name not in row or not isinstance(row[name], str) for name in EDITABLE):
            raise ValueError('Missing original editable field values.')
    if compare_rows(rows, rows, submitted, schema=SCHEMA):
        raise ValueError('Original workbook values differ from the trusted offline baseline.')
    return manifest
