import base64
import io
import hashlib
import json
import secrets
from datetime import timedelta
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..core.constants import SCHEMA
from ..core.workbook import build_workbook


@tagged('post_install', '-at_install')
class TestSampleExcelSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        users_env = cls.env['res.users'].with_context(no_reset_password=True).env
        cls.editor = new_test_user(users_env, login='sample_excel_editor', groups='base.group_user,project.group_project_user')
        cls.other = new_test_user(users_env, login='sample_excel_other', groups='base.group_user,project.group_project_user')
        cls.factory = cls.env['res.partner'].create({'name': 'Synthetic Factory A'})
        cls.factory_b = cls.env['res.partner'].create({'name': 'Synthetic Factory B'})
        cls.product = cls.env['product.template'].create({'name': 'Synthetic Item'})
        cls.request = cls.env['mlx.sample.request'].create({
            'partner_id': cls.factory.id, 'company_id': cls.env.company.id,
        })
        cls.line = cls.env['mlx.sample.request.line'].create({
            'request_id': cls.request.id, 'product_tmpl_id': cls.product.id,
            'supplier_id': cls.factory.id, 'quantity': 2, 'sample_color': 'Silver',
            'remarks': 'Chrome handle', 'factory_ready_date': '2026-11-14',
        })
        cls.line_b = cls.env['mlx.sample.request.line'].create({
            'request_id': cls.request.id, 'product_tmpl_id': cls.product.id,
            'supplier_id': cls.factory_b.id, 'quantity': 1,
        })

    def _export(self, factory=False):
        wizard = self.env['sample.excel.export'].with_user(self.editor).create({
            'request_id': self.request.id, 'scope': 'factory' if factory else 'all',
            'supplier_id': factory.id if factory else False,
        })
        wizard.action_export()
        return base64.b64decode(wizard.file_data)

    def _edit(self, raw, **cells):
        book = load_workbook(io.BytesIO(raw))
        for cell, value in cells.items():
            book['Samples'][cell] = value
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()

    def _preview(self, raw, user=None):
        wizard = self.env['sample.excel.import'].with_user(user or self.editor).create({
            'request_id': self.request.id, 'file_name': 'sample.xlsx',
            'file_data': base64.b64encode(raw),
        })
        wizard.action_preview()
        return wizard

    def _legacy_file(self, raw):
        original = load_workbook(io.BytesIO(raw))
        book = Workbook()
        sheet = book.active
        sheet.title = 'Samples'
        headers = ['Factory', 'Malex Model', 'Factory Model', 'Photo', 'Sample Qty',
                   'Color & Finish', 'Other Sample Requirements', 'Sample Ready Date',
                   'Factory Feedback', 'Plug / Logo (Reference)', 'Line Status', 'Record Key']
        for col, label in enumerate(headers, 1):
            sheet.cell(4, col, label)
        for row in range(5, original['Samples'].max_row + 1):
            source = original['Samples']
            values = [source[f'E{row}'].value, source[f'A{row}'].value, source[f'D{row}'].value,
                      None, source[f'F{row}'].value, source[f'G{row}'].value, source[f'H{row}'].value,
                      source[f'I{row}'].value, source[f'J{row}'].value, '', 'Draft', source[f'K{row}'].value]
            for col, value in enumerate(values, 1):
                sheet.cell(row, col, value)
        meta = book.create_sheet('_sync')
        meta['A1'] = 'sample-excel-sync/1'
        meta['A2'] = original['_sync']['A2'].value
        meta.sheet_state = 'veryHidden'
        out = io.BytesIO()
        book.save(out)
        return out.getvalue()

    def test_description_mapping_and_readonly_import(self):
        self.product.description_sale = 'Master features'
        self.line.product_description = 'Sample line-specific features'
        raw = self._export(self.factory)
        sheet = load_workbook(io.BytesIO(raw))['Samples']
        self.assertEqual(sheet['C5'].value, 'Sample line-specific features')
        with self.assertRaises(UserError):
            self._preview(self._edit(raw, C5='Changed by factory'))

    def test_duplicate_product_rows_sort_and_update_original_line(self):
        self.line_b.write({'supplier_id': self.factory.id, 'quantity': 2, 'sample_color': 'White'})
        raw = self._export(self.factory)
        book = load_workbook(io.BytesIO(raw))
        sheet = book['Samples']
        first, second = [c.value for c in sheet[5]], [c.value for c in sheet[6]]
        for col, value in enumerate(second, 1):
            sheet.cell(5, col, value)
        for col, value in enumerate(first, 1):
            sheet.cell(6, col, value)
        sheet['G5'] = 'Pantone 4222C'
        out = io.BytesIO()
        book.save(out)
        self._preview(out.getvalue()).action_confirm()
        self.assertEqual(self.line.sample_color, 'Silver')
        self.assertEqual(self.line_b.sample_color, 'Pantone 4222C')

    def test_layout_downgrade_rejected(self):
        legacy = self._legacy_file(self._export(self.factory))
        with self.assertRaises(UserError):
            self._preview(legacy)

    def test_original_legacy_batch_still_imports(self):
        raw = self._export(self.factory)
        snapshot = self.env['sample.excel.snapshot'].sudo().search([
            ('kind', '=', 'export')], order='id desc', limit=1)
        snapshot.payload = {'rows': snapshot.payload['rows']}
        legacy = self._edit(self._legacy_file(raw), I5='Legacy feedback')
        self._preview(legacy).action_confirm()
        self.assertEqual(self.line.factory_comment, 'Legacy feedback')

    def _offline_package(self):
        rows = self.env['sample.excel.service'].with_user(self.editor)._export_rows(self.request)
        rows = [{k: v for k, v in row.items() if k != 'image'} for row in rows]
        token = secrets.token_urlsafe(32)
        raw = build_workbook(self.request.name, token, rows)
        now = fields.Datetime.now()
        data = {'format': 'sample-excel-sync/offline-batch/1', 'schema': SCHEMA, 'token': token,
                'database': self.env.cr.dbname, 'request_id': self.request.id,
                'request_name': self.request.name, 'company_id': self.request.company_id.id,
                'user_id': self.editor.id, 'user_login': self.editor.login,
                'exported_at': fields.Datetime.to_string(now),
                'expires_at': fields.Datetime.to_string(now + timedelta(days=90)),
                'workbook_sha256': hashlib.sha256(raw).hexdigest(),
                'payload': {'schema': SCHEMA, 'rows': rows}}
        return raw, data

    def _register(self, raw, data, user=None):
        manifest = json.dumps(data).encode()
        Snapshot = self.env['sample.excel.snapshot']
        if user:
            Snapshot = Snapshot.with_user(user)
        return Snapshot._register_offline(manifest, raw, hashlib.sha256(manifest).hexdigest())

    def test_trusted_offline_file_imports_after_admin_registration(self):
        raw, data = self._offline_package()
        before = (self.line.sample_color, self.line.factory_comment, self.line_b.factory_comment)
        snapshot = self._register(raw, data)
        self.assertEqual(snapshot.user_id, self.editor)
        self.assertEqual(before, (self.line.sample_color, self.line.factory_comment, self.line_b.factory_comment))
        wizard = self._preview(self._edit(raw, J5='Offline export returned'))
        wizard.action_confirm()
        self.assertEqual(self.line.factory_comment, 'Offline export returned')
        self.assertFalse(self.line_b.factory_comment)

    def test_offline_registration_is_idempotent(self):
        raw, data = self._offline_package()
        self.assertEqual(self._register(raw, data), self._register(raw, data))

    def test_regular_user_cannot_register_baseline(self):
        raw, data = self._offline_package()
        with self.assertRaises(AccessError):
            self._register(raw, data, self.editor)

    def test_wrong_database_or_owner_manifest_rejected(self):
        raw, data = self._offline_package()
        for values in [{'database': 'unrelated_database'}, {'user_login': 'another_exporter'}]:
            with self.subTest(values=values), self.assertRaises(UserError):
                self._register(raw, dict(data, **values))

    def test_offline_register_rechecks_factory_identity(self):
        raw, data = self._offline_package()
        self.line.supplier_id = self.factory_b
        with self.assertRaises(UserError):
            self._register(raw, data)

    def test_roundtrip_changes_only_requested_field(self):
        wizard = self._preview(self._edit(self._export(self.factory), I5='2026-11-18'))
        self.assertEqual(len(wizard.change_ids), 1)
        wizard.action_confirm()
        self.assertEqual(str(self.line.factory_ready_date), '2026-11-18')
        self.assertEqual(self.line.sample_color, 'Silver')
        self.assertFalse(self.line_b.factory_ready_date)
        again = self._preview(self._export(self.factory))
        self.assertFalse(again.change_ids)

    def test_reimport_of_updated_file_is_noop(self):
        raw = self._edit(self._export(self.factory), J5='Ready')
        self._preview(raw).action_confirm()
        self.assertFalse(self._preview(raw).change_ids)

    def test_explicit_clear_and_conflict(self):
        raw = self._export(self.factory)
        self.line.sample_color = 'Black'
        wizard = self._preview(self._edit(raw, G5='White'))
        self.assertEqual(wizard.change_ids.kind, 'conflict')
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.change_ids.choice = 'apply'
        wizard.action_confirm()
        self.assertEqual(self.line.sample_color, 'White')
        clear = self._preview(self._edit(self._export(self.factory), H5=None))
        self.assertEqual(clear.change_ids.kind, 'clear')
        clear.change_ids.choice = 'apply'
        clear.action_confirm()
        self.assertFalse(self.line.remarks)

    def test_server_only_change_is_preserved(self):
        raw = self._export(self.factory)
        self.line.sample_color = 'Black'
        self._preview(self._edit(raw, J5='Factory response')).action_confirm()
        self.assertEqual(self.line.sample_color, 'Black')

    def test_stale_preview_rejected(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Ready'))
        self.line.factory_comment = 'Changed after preview'
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(self.line.factory_comment, 'Changed after preview')

    def test_preview_display_values_cannot_override_trusted_plan(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Safe'))
        wizard.change_ids.write({'incoming_value': 'FORGED', 'field_name': 'state'})
        wizard.action_confirm()
        self.assertEqual(self.line.factory_comment, 'Safe')
        self.assertNotEqual(self.line.state, 'FORGED')

    def test_changed_file_after_preview_rejected(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Safe'))
        wizard.file_data = base64.b64encode(self._edit(self._export(self.factory), J5='Other'))
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_other_user_token_and_wizard_rejected(self):
        raw = self._export(self.factory)
        with self.assertRaises(UserError):
            self._preview(raw, self.other)
        wizard = self._preview(self._edit(raw, J5='Ready'))
        with self.assertRaises(AccessError):
            wizard.with_user(self.other).action_confirm()

    def test_private_snapshot_cannot_be_created_or_modified_by_editor(self):
        raw = self._export(self.factory)
        self.assertTrue(raw)
        with self.assertRaises(AccessError):
            self.env['sample.excel.snapshot'].with_user(self.editor).create({
                'kind': 'export', 'request_id': self.request.id, 'payload': {},
            })
        with self.assertRaises(AccessError):
            self.env['sample.excel.snapshot'].with_user(self.editor).search([])

    def test_foreign_row_cancel_and_moved_factory_rejected(self):
        raw = self._export(self.factory)
        with self.assertRaises(UserError):
            self._preview(self._edit(raw, K5='forged-key', J5='Ready'))
        self.line.supplier_id = self.factory_b
        with self.assertRaises(UserError):
            self._preview(self._edit(raw, J5='Ready'))

    def test_cancelled_line_and_request_not_updated(self):
        self.line.state = 'cancelled'
        with self.assertRaises(UserError):
            self._preview(self._edit(self._export(self.factory), J5='Ready'))

    def test_preview_is_consumed(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Ready'))
        wizard.action_confirm()
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_expired_export_rejected(self):
        raw = self._export(self.factory)
        snap = self.env['sample.excel.snapshot'].sudo().search([('kind', '=', 'export')], order='id desc', limit=1)
        snap.expires_at = fields.Datetime.now() - timedelta(days=1)
        with self.assertRaises(UserError):
            self._preview(raw)

    def test_exact_legacy_task_date_sync_without_state_change(self):
        Task = self.env['project.task']
        if 'x_sample_line_id' not in Task._fields:
            self.skipTest('Legacy task fields are unavailable in this installation.')
        task = Task.create({'name': 'Synthetic linked task', 'x_sample_line_id': self.line.id,
                            'user_ids': [(6, 0, [self.editor.id])],
                            'x_sample_ready_date': '2026-11-14'})
        unlinked = Task.create({'name': 'Synthetic unlinked task', 'x_sample_ready_date': '2026-11-10',
                               'user_ids': [(6, 0, [self.editor.id])]})
        state = self.line.state
        self._preview(self._edit(self._export(self.factory), I5='2026-11-18')).action_confirm()
        self.assertEqual(str(task.x_sample_ready_date), '2026-11-18')
        self.assertEqual(str(unlinked.x_sample_ready_date), '2026-11-10')
        self.assertEqual(self.line.state, state)

    def test_duplicate_task_links_stop_update(self):
        Task = self.env['project.task']
        if 'x_sample_line_id' not in Task._fields:
            self.skipTest('Legacy task fields are unavailable.')
        for suffix in ('A', 'B'):
            Task.create({'name': 'Synthetic task ' + suffix, 'x_sample_line_id': self.line.id,
                         'user_ids': [(6, 0, [self.editor.id])]})
        with self.assertRaises(UserError):
            self._preview(self._edit(self._export(self.factory), I5='2026-11-18'))

    def test_lost_record_permission_prevents_update(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Ready'))
        model = self.env['ir.model']._get('mlx.sample.request.line')
        self.env['ir.rule'].create({'name': 'Synthetic deny sample access',
                                   'model_id': model.id, 'domain_force': "[('id','=',0)]"})
        with self.assertRaises(AccessError):
            wizard.action_confirm()

    def test_hidden_task_is_not_treated_as_absent(self):
        Task = self.env['project.task']
        if 'x_sample_line_id' not in Task._fields:
            self.skipTest('Legacy task fields are unavailable.')
        raw = self._export(self.factory)
        Task.create({'name': 'Synthetic hidden task', 'x_sample_line_id': self.line.id})
        with self.assertRaises(AccessError):
            self._preview(self._edit(raw, I5='2026-11-18'))

    def test_indirect_other_line_write_is_rolled_back(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Ready'))
        model_class = type(self.line)
        original = model_class.write
        other_id = self.line_b.id

        def side_effect(records, values):
            result = original(records, values)
            if self.line.id in records.ids and 'factory_comment' in values:
                original(records.browse(other_id), {'sample_color': 'Unexpected automation'})
            return result

        with patch.object(model_class, 'write', side_effect), self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertFalse(self.line.factory_comment)
        self.assertFalse(self.line_b.sample_color)

    def test_unrelated_request_status_change_is_rolled_back(self):
        wizard = self._preview(self._edit(self._export(self.factory), J5='Ready'))
        model_class = type(self.line)
        original = model_class.write

        def side_effect(records, values):
            result = original(records, values)
            if 'factory_comment' in values:
                records.request_id.write({'state': 'cancelled'})
            return result

        with patch.object(model_class, 'write', side_effect), self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(self.request.state, 'draft')
        self.assertFalse(self.line.factory_comment)
