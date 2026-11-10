import base64
import io
from datetime import timedelta

from openpyxl import load_workbook

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSampleExcelSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(cls.env, login='sample_excel_editor', groups='base.group_user,project.group_project_user')
        cls.other = new_test_user(cls.env, login='sample_excel_other', groups='base.group_user,project.group_project_user')
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

    def test_roundtrip_changes_only_requested_field(self):
        wizard = self._preview(self._edit(self._export(self.factory), H5='2026-11-18'))
        self.assertEqual(len(wizard.change_ids), 1)
        wizard.action_confirm()
        self.assertEqual(str(self.line.factory_ready_date), '2026-11-18')
        self.assertEqual(self.line.sample_color, 'Silver')
        self.assertFalse(self.line_b.factory_ready_date)
        again = self._preview(self._export(self.factory))
        self.assertFalse(again.change_ids)

    def test_reimport_of_updated_file_is_noop(self):
        raw = self._edit(self._export(self.factory), I5='Ready')
        self._preview(raw).action_confirm()
        self.assertFalse(self._preview(raw).change_ids)

    def test_explicit_clear_and_conflict(self):
        raw = self._export(self.factory)
        self.line.sample_color = 'Black'
        wizard = self._preview(self._edit(raw, F5='White'))
        self.assertEqual(wizard.change_ids.kind, 'conflict')
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.change_ids.choice = 'apply'
        wizard.action_confirm()
        self.assertEqual(self.line.sample_color, 'White')
        clear = self._preview(self._edit(self._export(self.factory), G5=None))
        self.assertEqual(clear.change_ids.kind, 'clear')
        clear.change_ids.choice = 'apply'
        clear.action_confirm()
        self.assertFalse(self.line.remarks)

    def test_server_only_change_is_preserved(self):
        raw = self._export(self.factory)
        self.line.sample_color = 'Black'
        self._preview(self._edit(raw, I5='Factory response')).action_confirm()
        self.assertEqual(self.line.sample_color, 'Black')

    def test_stale_preview_rejected(self):
        wizard = self._preview(self._edit(self._export(self.factory), I5='Ready'))
        self.line.factory_comment = 'Changed after preview'
        with self.assertRaises(UserError):
            wizard.action_confirm()
        self.assertEqual(self.line.factory_comment, 'Changed after preview')

    def test_preview_display_values_cannot_override_trusted_plan(self):
        wizard = self._preview(self._edit(self._export(self.factory), I5='Safe'))
        wizard.change_ids.write({'incoming_value': 'FORGED', 'field_name': 'state'})
        wizard.action_confirm()
        self.assertEqual(self.line.factory_comment, 'Safe')
        self.assertNotEqual(self.line.state, 'FORGED')

    def test_changed_file_after_preview_rejected(self):
        wizard = self._preview(self._edit(self._export(self.factory), I5='Safe'))
        wizard.file_data = base64.b64encode(self._edit(self._export(self.factory), I5='Other'))
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_other_user_token_and_wizard_rejected(self):
        raw = self._export(self.factory)
        with self.assertRaises((UserError, AccessError)):
            self._preview(raw, self.other)
        wizard = self._preview(self._edit(raw, I5='Ready'))
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
            self._preview(self._edit(raw, L5='forged-key', I5='Ready'))
        self.line.supplier_id = self.factory_b
        with self.assertRaises(UserError):
            self._preview(self._edit(raw, I5='Ready'))

    def test_cancelled_line_and_request_not_updated(self):
        self.line.state = 'cancelled'
        with self.assertRaises(UserError):
            self._preview(self._edit(self._export(self.factory), I5='Ready'))

    def test_preview_is_consumed(self):
        wizard = self._preview(self._edit(self._export(self.factory), I5='Ready'))
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
                            'x_sample_ready_date': '2026-11-14'})
        unlinked = Task.create({'name': 'Synthetic unlinked task', 'x_sample_ready_date': '2026-11-10'})
        state = self.line.state
        self._preview(self._edit(self._export(self.factory), H5='2026-11-18')).action_confirm()
        self.assertEqual(str(task.x_sample_ready_date), '2026-11-18')
        self.assertEqual(str(unlinked.x_sample_ready_date), '2026-11-10')
        self.assertEqual(self.line.state, state)

    def test_duplicate_task_links_stop_update(self):
        Task = self.env['project.task']
        if 'x_sample_line_id' not in Task._fields:
            self.skipTest('Legacy task fields are unavailable.')
        for suffix in ('A', 'B'):
            Task.create({'name': 'Synthetic task ' + suffix, 'x_sample_line_id': self.line.id})
        with self.assertRaises(UserError):
            self._preview(self._edit(self._export(self.factory), H5='2026-11-18'))

    def test_lost_record_permission_prevents_update(self):
        wizard = self._preview(self._edit(self._export(self.factory), I5='Ready'))
        model = self.env['ir.model']._get('mlx.sample.request.line')
        self.env['ir.rule'].create({'name': 'Synthetic deny sample access',
                                   'model_id': model.id, 'domain_force': "[('id','=',0)]"})
        with self.assertRaises(AccessError):
            wizard.action_confirm()
