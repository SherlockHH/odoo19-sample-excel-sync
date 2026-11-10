import base64
import secrets
from copy import deepcopy

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..core.constants import EDITABLE, LABELS, MAX_ROWS
from ..core.description import choose_description
from .automation_guard import narrow_import_guard


class SampleExcelService(models.AbstractModel):
    _name = 'sample.excel.service'
    _description = 'Sample Excel internal business adapter'

    @api.model
    def _check_request(self, request, importing=False):
        request.ensure_one()
        request.check_access('read')
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(self.env._('Internal user access is required.'))
        if request.company_id not in self.env.companies:
            raise AccessError(self.env._('Switch to the sample request company first.'))
        if importing and request.state in ('cancelled', 'resolved'):
            raise UserError(self.env._('Reopen the sample request before importing updates.'))
        Line = self.env['mlx.sample.request.line']
        for name in EDITABLE:
            field = Line._fields.get(name)
            if not field or field.readonly or not field.store:
                raise UserError(self.env._('The installed Sample Request module does not provide the supported writable fields.'))

    @api.model
    def _tasks(self, lines):
        Task = self.env['project.task']
        link_fields = [f for f in ('sample_request_line_id', 'x_sample_line_id') if f in Task._fields]
        result = {line.id: Task.browse() for line in lines}
        if not lines or not link_fields:
            return result
        Task.check_access('read')
        domain = ['|'] * (len(link_fields) - 1) + [(f, 'in', lines.ids) for f in link_fields]
        visible = Task.with_context(active_test=False).search(domain)
        # Only an association count is elevated, never task contents or writes.
        # Record rules must not make a hidden exact link look like no link.
        total = Task.sudo().with_context(active_test=False).search_count(domain)
        if len(visible) != total:
            raise AccessError(self.env._('Some linked tasks are outside your access. Ask the sample owner or IT to review the task permissions.'))
        for task in visible:
            targets = set()
            for name in link_fields:
                value = task[name]
                if value:
                    targets.add(value.id if hasattr(value, 'id') else value)
            if len(targets) != 1:
                raise UserError(self.env._('A task has conflicting sample links. Ask IT to repair the link.'))
            line_id = targets.pop()
            if line_id in result:
                line = lines.browse(line_id)
                if task.company_id and task.company_id != line.request_id.company_id:
                    raise UserError(self.env._('A linked task belongs to another company.'))
                result[line_id] |= task
        for task_set in result.values():
            if len(task_set) > 1:
                raise UserError(self.env._('More than one task is linked to a sample line. Repair the link before importing.'))
        return result

    @api.model
    def _row(self, line, key, image=False, task=None):
        product = line.product_tmpl_id
        selection = dict(line._fields['state']._description_selection(self.env))
        reference = []
        if 'x_plug' in line._fields and line.x_plug:
            plugs = dict(line._fields['x_plug']._description_selection(self.env))
            reference.append('Plug: ' + plugs.get(line.x_plug, line.x_plug))
        logo = next((line[n] for n in ('logo', 'x_logo') if n in line._fields and line[n]), '')
        if not logo and task:
            logo = next((task[n] for n in ('sample_logo', 'x_sample_logo') if n in task._fields and task[n]), '')
        if logo:
            reference.append('Logo: ' + str(logo))
        row = {
            'key': key, 'line_id': line.id,
            'identity': {'request_id': line.request_id.id, 'supplier_id': line.supplier_id.id,
                         'product_tmpl_id': product.id},
            'source_state': line.state, 'cancelled': line.state == 'cancelled',
            'factory': line.supplier_id.display_name or '',
            'model': (line.x_old_malex_model if 'x_old_malex_model' in line._fields else '')
                     or (product.old_name if 'old_name' in product._fields else '')
                     or product.default_code or '',
            'factory_model': (line.x_factory_model_no if 'x_factory_model_no' in line._fields else '')
                             or (product.factory_model_no if 'factory_model_no' in product._fields else '') or '',
            'quantity': line.quantity,
            'product_description': choose_description(
                line.product_description if 'product_description' in line._fields else '',
                {name: product[name] for name in ('mlx_description_text', 'description', 'description_sale')
                 if name in product._fields}),
            'sample_color': line.sample_color or '', 'remarks': line.remarks or '',
            'factory_ready_date': fields.Date.to_string(line.factory_ready_date) or '',
            'factory_comment': line.factory_comment or '',
            'reference': '\n'.join(reference),
            'state': 'Cancelled' if line.state == 'cancelled' else selection.get(line.state, line.state) or '',
        }
        if image:
            value = (line.x_product_image if 'x_product_image' in line._fields else False) or product.image_256
            if value:
                row['image'] = base64.b64decode(value)
            if 'x_remark_image' in line._fields and line.x_remark_image:
                row['remark_image'] = base64.b64decode(line.x_remark_image)
        return row

    @api.model
    def _export_rows(self, request, supplier=False):
        self._check_request(request)
        lines = request.line_ids
        lines.check_access('read')
        if supplier:
            lines = lines.filtered(lambda line: line.supplier_id == supplier)
        if not lines or len(lines) > MAX_ROWS:
            raise UserError(self.env._('Choose a scope with 1 to 2000 sample lines.'))
        order = 'sequence' if 'sequence' in lines._fields else 'id'
        lines = lines.sorted(key=lambda line: (line.supplier_id.display_name or '', line[order], line.id))
        return [self._row(line, secrets.token_urlsafe(24), image=True) for line in lines]

    @api.model
    def _current_rows(self, request, baselines):
        self._check_request(request, importing=True)
        lines = self.env['mlx.sample.request.line'].browse([r['line_id'] for r in baselines])
        lines.check_access('read')
        lines.check_access('write')
        if len(lines.exists()) != len(lines):
            raise UserError(self.env._('A sample line was removed. Export a fresh workbook.'))
        result = []
        for base in baselines:
            line = lines.browse(base['line_id'])
            if (line.request_id != request or line.supplier_id.id != base['identity']['supplier_id']
                    or line.product_tmpl_id.id != base['identity']['product_tmpl_id']):
                raise UserError(self.env._('A sample line changed product, factory or request. Export again.'))
            row = self._row(line, base['key'])
            # Reference remains immutable in Excel; do not query task text just for comparison.
            row['reference'] = base.get('reference', '')
            result.append(row)
        return result

    @api.model
    def _task_facts(self, lines):
        facts = {}
        for line_id, task in self._tasks(lines).items():
            if not task:
                continue
            names = [n for n in ('sample_ready_date', 'x_sample_ready_date') if n in task._fields]
            if not names:
                continue
            task.check_access('write')
            facts[str(line_id)] = {'id': task.id, 'dates': {
                name: fields.Date.to_string(task[name]) or '' for name in names},
                'stage_id': task.stage_id.id, 'state': task.state}
        return facts

    @api.model
    def _protected_scope(self, request):
        lines = request.line_ids
        lines.check_access('read')
        scope = {'request': {'state': request.state, 'company_id': request.company_id.id,
                             'line_ids': sorted(lines.ids)}, 'lines': {}, 'tasks': {}}
        for line in lines:
            scope['lines'][str(line.id)] = {
                'state': line.state, 'supplier_id': line.supplier_id.id,
                'product_tmpl_id': line.product_tmpl_id.id, 'request_id': line.request_id.id,
                'quantity': line.quantity, 'fields': {
                    name: fields.Date.to_string(line[name]) or '' if name == 'factory_ready_date'
                    else line[name] or '' for name in EDITABLE},
            }
        for line_id, task in self._tasks(lines).items():
            if task:
                scope['tasks'][str(task.id)] = {
                    'line_id': line_id, 'state': task.state, 'stage_id': task.stage_id.id,
                    'company_id': task.company_id.id, 'project_id': task.project_id.id,
                    'user_ids': sorted(task.user_ids.ids), 'dates': {
                        name: fields.Date.to_string(task[name]) or ''
                        for name in ('sample_ready_date', 'x_sample_ready_date') if name in task._fields},
                }
        return scope

    @api.model
    def _apply(self, request, bases, updates, task_facts):
        by_key = {r['key']: r for r in bases}
        logs = []
        expected = deepcopy(self._protected_scope(request))
        for key, values in updates.items():
            line_id = str(by_key[key]['line_id'])
            expected['lines'][line_id]['fields'].update(values)
            fact = task_facts.get(line_id)
            if 'factory_ready_date' in values and fact:
                expected['tasks'][str(fact['id'])]['dates'].update({
                    name: values['factory_ready_date'] for name in fact['dates']})
        context = {
            'sample_request_project_link_syncing': True,
            'skip_sample_line_lifecycle': True, 'skip_sample_project_stage_sync': True,
            'skip_sample_project_objective_sync': True, 'tracking_disable': True,
            'mail_notify_force_send': False, 'mail_create_nosubscribe': True,
        }
        with narrow_import_guard():
            for key, values in updates.items():
                line = self.env['mlx.sample.request.line'].browse(by_key[key]['line_id'])
                if set(values) - set(EDITABLE):
                    raise UserError(self.env._('Unexpected import field.'))
                line.check_access('write')
                before = {name: fields.Date.to_string(line[name]) if name == 'factory_ready_date'
                          else line[name] or '' for name in values}
                state = line.state
                line.with_context(**context).write({name: value or False for name, value in values.items()})
                fact = task_facts.get(str(line.id))
                if 'factory_ready_date' in values and fact:
                    task = self.env['project.task'].browse(fact['id'])
                    task.with_context(**context).write({
                        name: values['factory_ready_date'] or False for name in fact['dates']})
                    if task.stage_id.id != fact['stage_id'] or task.state != fact['state']:
                        raise UserError(self.env._('An existing task automation changed its status. IT must review the integration.'))
                if line.state != state:
                    raise UserError(self.env._('An existing automation changed sample status. IT must review the integration.'))
                for name, value in values.items():
                    logs.append(Markup('<li>{}: {}: {} → {}</li>').format(
                        by_key[key]['model'] or f'Line {line.id}', LABELS[name], before[name] or '—', value or '—'))
        if logs:
            request.with_context(mail_notify_force_send=False).message_post(
                body=Markup('<p>Sample Excel update</p><ul>{}</ul>').format(Markup('').join(logs)),
                subtype_xmlid='mail.mt_note', message_type='comment')
        if self._protected_scope(request) != expected:
            raise UserError(self.env._('An existing automation changed other protected sample/task data. The import was rolled back; ask IT to review the integration.'))
