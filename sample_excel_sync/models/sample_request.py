from odoo import models
from odoo.exceptions import AccessError


class SampleRequest(models.Model):
    _inherit = 'mlx.sample.request'

    def _excel_wizard_action(self, model, title):
        self.ensure_one()
        self.check_access('read')
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(self.env._('Only internal users can use sample Excel updates.'))
        return {'type': 'ir.actions.act_window', 'name': title, 'res_model': model,
                'view_mode': 'form', 'target': 'new',
                'context': {'default_request_id': self.id}}

    def action_export_sample_excel(self):
        return self._excel_wizard_action('sample.excel.export', self.env._('Export Sample Excel'))

    def action_import_sample_excel(self):
        return self._excel_wizard_action('sample.excel.import', self.env._('Import Sample Updates'))
