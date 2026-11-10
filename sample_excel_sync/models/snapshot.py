import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..core.offline_batch import validate_offline_batch


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

    @api.model
    def _register_offline(self, manifest_bytes, workbook_bytes, expected_sha256, *, allow_production=False):
        """Administrator-only Odoo-shell helper, never an RPC/wizard entry point."""
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Only an administrator may register a trusted offline export.'))
        if any(marker in self.env.cr.dbname.lower() for marker in ('live', 'prod')) and not allow_production:
            raise UserError(self.env._('Production metadata registration requires explicit IT approval.'))
        try:
            data = validate_offline_batch(manifest_bytes, workbook_bytes, expected_sha256)
        except (ValueError, KeyError, TypeError) as exc:
            raise UserError(str(exc)) from exc
        if data['database'] != self.env.cr.dbname:
            raise UserError(self.env._('Offline export belongs to another database.'))
        expires = fields.Datetime.to_datetime(data['expires_at'])
        issued = fields.Datetime.to_datetime(data['exported_at'])
        if expires <= fields.Datetime.now() or issued > fields.Datetime.now() + timedelta(minutes=5):
            raise UserError(self.env._('The offline export expired or has an invalid issue time.'))
        request = self.env['mlx.sample.request'].browse(data['request_id']).exists()
        owner = self.env['res.users'].browse(data['user_id']).exists()
        if (not request or request.name != data['request_name'] or request.company_id.id != data['company_id']
                or not owner or owner.login != data['user_login'] or not owner.active or owner.share
                or request.company_id not in owner.company_ids):
            raise UserError(self.env._('Offline database, owner, company or request identity changed.'))
        as_owner = request.with_user(owner).with_context(allowed_company_ids=[request.company_id.id])
        # Verify current-user record access and unchanged record/product/factory identity.
        self.env['sample.excel.service'].with_user(owner).with_context(
            allowed_company_ids=[request.company_id.id])._current_rows(as_owner, data['payload']['rows'])
        existing = self.sudo().search([('token', '=', data['token'])], limit=1)
        if existing:
            if (existing.kind != 'export' or existing.request_id != request or existing.user_id != owner
                    or existing.company_id != request.company_id or existing.payload != data['payload']
                    or existing.expires_at != expires):
                raise UserError(self.env._('An incompatible export already uses this token.'))
            return existing
        return self.sudo().create({
            'kind': 'export', 'token': data['token'], 'request_id': request.id,
            'company_id': request.company_id.id, 'user_id': owner.id,
            'payload': data['payload'], 'expires_at': expires,
        })

    @api.autovacuum
    def _gc_expired_snapshots(self):
        self.sudo().search([('expires_at', '<', fields.Datetime.now())]).unlink()
