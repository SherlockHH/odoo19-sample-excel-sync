import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class SampleExcelSnapshot(models.Model):
    """Private immutable baselines; no user CRUD or management page."""
    _name = 'sample.excel.snapshot'
    _description = 'Sample Excel internal snapshot'
    _rec_name = 'token'

    token = fields.Char(required=True, index=True, copy=False,
                        default=lambda self: secrets.token_urlsafe(32))
    kind = fields.Selection([('export', 'Export'), ('preview', 'Preview')], required=True)
    request_id = fields.Many2one('mlx.sample.request', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    payload = fields.Json(required=True)
    expires_at = fields.Datetime(required=True)
    consumed = fields.Boolean(default=False)
    _token_unique = models.Constraint('UNIQUE(token)', 'Snapshot token must be unique.')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(self.env._('Snapshots can only be created by the export/import service.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(self.env._('Export snapshots cannot be edited.'))
        return super().write(vals)

    @api.model
    def _store(self, request, kind, payload):
        request.check_access('read')
        return self.sudo().create({
            'kind': kind, 'request_id': request.id, 'company_id': request.company_id.id,
            'user_id': self.env.uid, 'payload': payload,
            'expires_at': fields.Datetime.now() + timedelta(days=90 if kind == 'export' else 1),
        })

    @api.model
    def _lookup(self, token, kind, request):
        request.check_access('read')
        if request.company_id not in self.env.companies:
            raise AccessError(self.env._('Switch to the sample request company first.'))
        if not isinstance(token, str) or not 20 <= len(token) <= 100:
            raise UserError(self.env._('Unknown export. Export a fresh workbook.'))
        snapshot = self.sudo().search([
            ('token', '=', token), ('kind', '=', kind), ('request_id', '=', request.id),
            ('company_id', '=', request.company_id.id), ('user_id', '=', self.env.uid),
            ('expires_at', '>', fields.Datetime.now()), ('consumed', '=', False),
        ], limit=1)
        if not snapshot:
            raise UserError(self.env._('Unknown, expired or completed session. Use the original exporter account and preview again.'))
        return snapshot

    @api.autovacuum
    def _gc_expired_snapshots(self):
        self.sudo().search([('expires_at', '<', fields.Datetime.now())]).unlink()
