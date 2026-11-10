import base64
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..core.workbook import build_workbook
from ..core.constants import IMAGE_KEYS, SCHEMA


class SampleExcelExport(models.TransientModel):
    _name = 'sample.excel.export'
    _description = 'Export Sample Excel'

    request_id = fields.Many2one('mlx.sample.request', required=True, readonly=True)
    scope = fields.Selection([('all', 'All Sample Lines'), ('factory', 'Selected Factory')],
                             default='all', required=True)
    available_supplier_ids = fields.Many2many('res.partner', compute='_compute_suppliers')
    supplier_id = fields.Many2one('res.partner', string='Factory')
    file_data = fields.Binary(readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)

    @api.depends('request_id')
    def _compute_suppliers(self):
        for wizard in self:
            wizard.available_supplier_ids = wizard.request_id.line_ids.mapped('supplier_id')

    def action_export(self):
        self.ensure_one()
        self.check_access('write')
        if self.scope == 'factory' and not self.supplier_id:
            raise UserError(self.env._('Select a factory in this sample request.'))
        supplier = self.supplier_id if self.scope == 'factory' else False
        service = self.env['sample.excel.service']
        rows = service._export_rows(self.request_id, supplier)
        bases = [{k: v for k, v in row.items() if k not in IMAGE_KEYS} for row in rows]
        snapshot = self.env['sample.excel.snapshot']._store(self.request_id, 'export', {'rows': bases, 'schema': SCHEMA})
        try:
            raw = build_workbook(self.request_id.name, snapshot.token, rows)
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        suffix = supplier.name if supplier else 'All'
        filename = re.sub(r'[^\w .-]', '_', f'Sample_{self.request_id.name}_{suffix}')[:160] + '.xlsx'
        self.write({'file_data': base64.b64encode(raw), 'file_name': filename})
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=file_name&download=true'}
