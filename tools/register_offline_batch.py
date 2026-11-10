"""Run explicitly from an administrator's Odoo shell after installing the add-on.

Use the original unedited workbook plus the baseline retained by its trusted
exporter. Never register a baseline obtained from a factory-returned workbook.
This helper creates only internal export metadata and does not commit for you.
"""
from pathlib import Path


def register_batch(env, manifest_path, original_workbook_path, expected_manifest_sha256, *, allow_production=False):
    manifest = Path(manifest_path).read_bytes()
    workbook = Path(original_workbook_path).read_bytes()
    with env.cr.savepoint():
        snapshot = env['sample.excel.snapshot']._register_offline(
            manifest, workbook, expected_manifest_sha256, allow_production=allow_production)
    return {'snapshot_id': snapshot.id, 'request': snapshot.request_id.name,
            'exporter': snapshot.user_id.login, 'expires_at': str(snapshot.expires_at)}
