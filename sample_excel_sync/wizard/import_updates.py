import base64
import binascii
import hashlib

from odoo import fields, models
from odoo.exceptions import AccessError, LockError, UserError

from ..core.comparison import compare_rows, resolve_changes
from ..core.constants import LABELS, MAX_FILE
from ..core.workbook import parse_workbook


class SampleExcelImport(models.TransientModel):
    _name = 'sample.excel.import'
    _description = 'Import Sample Updates'

    request_id = fields.Many2one('mlx.sample.request', required=True, readonly=True)
    file_data = fields.Binary(required=True, attachment=False, string='Updated Excel')
    file_name = fields.Char()
    state = fields.Selection([('upload', 'Upload'), ('preview', 'Preview'), ('done', 'Done')],
                             default='upload', readonly=True)
    preview_token = fields.Char(readonly=True)
    change_ids = fields.One2many('sample.excel.change', 'wizard_id', string='Changed Fields')

    def _check_owner(self):
        self.ensure_one()
        self.check_access('write')
        if self.create_uid != self.env.user and not self.env.su:
            raise AccessError(self.env._('This import belongs to another user.'))

    def _file_bytes(self):
        if not self.file_name or not self.file_name.lower().endswith('.xlsx'):
            raise UserError(self.env._('Upload an .xlsx workbook exported by this module.'))
        if not self.file_data or len(self.file_data) > (MAX_FILE + 2) // 3 * 4:
            raise UserError(self.env._('The workbook must be no larger than 8 MB.'))
        try:
            return base64.b64decode(self.file_data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise UserError(self.env._('Invalid upload encoding.')) from exc

    def action_preview(self):
        self._check_owner()
        raw = self._file_bytes()
        try:
            token, submitted = parse_workbook(raw)
            snapshots = self.env['sample.excel.snapshot']
            export = snapshots._lookup(token, 'export', self.request_id)
            all_bases = export.payload['rows']
            # Validate identities/duplicates before selecting the submitted subset.
            compare_rows(all_bases, all_bases, submitted)
            keys = {r['key'] for r in submitted}
            bases = [r for r in all_bases if r['key'] in keys]
            service = self.env['sample.excel.service']
            current = service._current_rows(self.request_id, bases)
            changes = compare_rows(bases, current, submitted)
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        date_keys = {c['key'] for c in changes if c['field'] == 'factory_ready_date'}
        date_lines = self.env['mlx.sample.request.line'].browse(
            [b['line_id'] for b in bases if b['key'] in date_keys])
        tasks = service._task_facts(date_lines)
        trusted = snapshots._store(self.request_id, 'preview', {
            'wizard_id': self.id, 'file_hash': hashlib.sha256(raw).hexdigest(),
            'export_token': token, 'bases': bases, 'current': current,
            'changes': changes, 'tasks': tasks, 'request_state': self.request_id.state,
        })
        by_key = {r['key']: r for r in bases}
        self.change_ids.unlink()
        self.write({'preview_token': trusted.token, 'state': 'preview', 'change_ids': [
            fields.Command.create({
                'change_key': c['id'], 'product_label': by_key[c['key']]['model'] or
                f"Line {by_key[c['key']]['line_id']}",
                'field_name': c['field'], 'field_label': LABELS[c['field']],
                'current_value': c['current'], 'incoming_value': c['incoming'],
                'kind': c['kind'], 'choice': 'apply' if c['kind'] == 'update'
                else 'keep' if c['kind'] == 'clear' else False,
            }) for c in changes]})
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Preview Sample Updates')}

    def action_confirm(self):
        self._check_owner()
        snapshot = self.env['sample.excel.snapshot']._lookup(self.preview_token, 'preview', self.request_id)
        try:
            with self.env.cr.savepoint():
                return self._confirm_locked(snapshot)
        except LockError as exc:
            raise UserError(self.env._('These records are being updated. Preview again after the other operation finishes.')) from exc
        except ValueError as exc:
            raise UserError(str(exc)) from exc

    def _confirm_locked(self, snapshot):
        # Lock the private session first so a double click cannot apply it twice.
        snapshot.lock_for_update()
        snapshot.invalidate_recordset()
        if snapshot.consumed or snapshot.expires_at <= fields.Datetime.now():
            raise UserError(self.env._('Preview expired or already saved. Preview again.'))
        plan = snapshot.payload
        if plan['wizard_id'] != self.id or hashlib.sha256(self._file_bytes()).hexdigest() != plan['file_hash']:
            raise UserError(self.env._('The uploaded file changed. Preview it again.'))
        self.env['sample.excel.snapshot']._lookup(plan['export_token'], 'export', self.request_id)
        request = self.request_id
        service = self.env['sample.excel.service']
        service._check_request(request, importing=True)
        request.lock_for_update()
        request.invalidate_recordset()
        service._current_rows(request, plan['bases'])  # ACL check before locking business records.
        lines = self.env['mlx.sample.request.line'].browse([r['line_id'] for r in plan['bases']])
        lines.lock_for_update()
        lines.invalidate_recordset()
        tasks = self.env['project.task'].browse([f['id'] for f in plan['tasks'].values()])
        tasks.check_access('write') if tasks else None
        tasks.lock_for_update()
        tasks.invalidate_recordset()
        current = service._current_rows(request, plan['bases'])
        date_line_ids = [int(line_id) for line_id in plan['tasks']]
        # Include date-changed rows without a task at preview time to detect new links.
        date_keys = {c['key'] for c in plan['changes'] if c['field'] == 'factory_ready_date'}
        date_line_ids += [r['line_id'] for r in plan['bases'] if r['key'] in date_keys]
        task_facts = service._task_facts(lines.browse(sorted(set(date_line_ids))))
        if (current != plan['current'] or request.state != plan['request_state']
                or task_facts != plan['tasks']):
            raise UserError(self.env._('Odoo data changed after preview. Preview the workbook again.'))
        expected_keys = {c['id'] for c in plan['changes']}
        if len(self.change_ids) != len(expected_keys) or set(self.change_ids.mapped('change_key')) != expected_keys:
            raise UserError(self.env._('The preview rows changed. Preview the workbook again.'))
        decisions = {line.change_key: line.choice or None for line in self.change_ids}
        updates = resolve_changes(plan['changes'], decisions)
        service._apply(request, plan['bases'], updates, task_facts)
        snapshot.write({'consumed': True})
        self.state = 'done'
        count = sum(len(values) for values in updates.values())
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': self.env._('Sample updates saved'),
            'message': self.env._('%s field(s) updated.', count), 'type': 'success',
            'next': {'type': 'ir.actions.act_window_close'},
        }}


class SampleExcelChange(models.TransientModel):
    _name = 'sample.excel.change'
    _description = 'Sample Excel changed field'

    wizard_id = fields.Many2one('sample.excel.import', required=True, ondelete='cascade')
    change_key = fields.Char(required=True, readonly=True)
    product_label = fields.Char(string='Product', readonly=True)
    field_name = fields.Char(readonly=True)
    field_label = fields.Char(string='Field', readonly=True)
    current_value = fields.Text(string='Current Odoo', readonly=True)
    incoming_value = fields.Text(string='Excel', readonly=True)
    kind = fields.Selection([('update', 'Update'), ('clear', 'Clear'), ('conflict', 'Conflict')], readonly=True)
    choice = fields.Selection([('apply', 'Use Excel / Confirm Clear'), ('keep', 'Keep Odoo / Ignore')], string='Action')
