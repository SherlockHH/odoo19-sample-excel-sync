from contextlib import contextmanager
from contextvars import ContextVar

from odoo import models


# Not a caller-supplied context flag: only this add-on's private write section
# can suppress these two known broad legacy project-followup actions.
_import_write = ContextVar('sample_excel_import_write', default=False)
_LEGACY_ACTIONS = (
    'sample_request_project_link.action_auto_sample_line_lifecycle',
    'sample_request_project_link.action_auto_sample_task_stage_followup',
)


@contextmanager
def narrow_import_guard():
    token = _import_write.set(True)
    try:
        yield
    finally:
        _import_write.reset(token)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    def run(self):
        if not _import_write.get():
            return super().run()
        skipped = self.browse()
        for xmlid in _LEGACY_ACTIONS:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                skipped |= action
        actions = self - skipped
        return super(IrActionsServer, actions).run() if actions else False
