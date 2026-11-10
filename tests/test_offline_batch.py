import hashlib
import json
import unittest

from test_core import sample, v2_file
from sync_core.workbook import build_workbook


class OfflineBatchTests(unittest.TestCase):
    def setUp(self):
        from sync_core.offline_batch import validate_offline_batch
        self.validate = validate_offline_batch
        self.token = 'export-token-' + 'x' * 32
        self.rows = [dict(sample(), line_id=10, identity={
            'request_id': 5, 'supplier_id': 6, 'product_tmpl_id': 7})]
        self.workbook = build_workbook('SMP-SYNTHETIC', self.token, self.rows)
        self.manifest = {'format': 'sample-excel-sync/offline-batch/1',
                         'schema': 'sample-excel-sync/3', 'token': self.token,
                         'database': 'synthetic_db', 'request_id': 5, 'request_name': 'SMP-SYNTHETIC',
                         'company_id': 1, 'user_id': 2, 'user_login': 'synthetic_exporter',
                         'exported_at': '2026-11-10 00:00:00', 'expires_at': '2027-02-08 00:00:00',
                         'workbook_sha256': hashlib.sha256(self.workbook).hexdigest(),
                         'payload': {'schema': 'sample-excel-sync/3', 'rows': self.rows}}

    def checked(self, manifest=None, workbook=None, expected=None):
        raw = json.dumps(manifest or self.manifest).encode()
        return self.validate(raw, workbook or self.workbook, expected or hashlib.sha256(raw).hexdigest())

    def test_original_export_and_trusted_hash_are_valid(self):
        self.assertEqual(self.checked()['request_id'], 5)

    def test_untrusted_manifest_hash_rejected(self):
        with self.assertRaises(ValueError):
            self.checked(expected='0' * 64)

    def test_original_v2_offline_package_remains_registerable(self):
        workbook = v2_file(self.rows, self.token)
        data = dict(self.manifest, schema='sample-excel-sync/2',
                    workbook_sha256=hashlib.sha256(workbook).hexdigest(),
                    payload={'schema': 'sample-excel-sync/2', 'rows': self.rows})
        self.assertEqual(self.checked(manifest=data, workbook=workbook)['schema'], 'sample-excel-sync/2')

    def test_factory_edited_workbook_is_not_a_baseline(self):
        other = build_workbook('SMP-SYNTHETIC', self.token, [dict(self.rows[0], remarks='Edited')])
        manifest = dict(self.manifest, workbook_sha256=hashlib.sha256(other).hexdigest())
        with self.assertRaises(ValueError):
            self.checked(manifest=manifest, workbook=other)

    def test_duplicate_line_identity_rejected(self):
        second = dict(self.rows[0], key='another-key')
        manifest = dict(self.manifest, payload={'schema': 'sample-excel-sync/3', 'rows': self.rows + [second]})
        with self.assertRaises(ValueError):
            self.checked(manifest=manifest)

    def test_wrong_request_identity_rejected(self):
        manifest = dict(self.manifest, request_id=99)
        with self.assertRaises(ValueError):
            self.checked(manifest=manifest)

    def test_manipulated_metadata_or_layout_rejected(self):
        for change in [{'token': 'different-token-' + 'z' * 32}, {'schema': 'sample-excel-sync/1'},
                       {'user_id': True}, {'expires_at': '2030-01-01 00:00:00'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.checked(manifest=dict(self.manifest, **change))
