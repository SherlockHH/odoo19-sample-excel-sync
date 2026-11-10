"""Synthetic integration contract, not company code. NEVER deploy this fixture."""
from odoo import fields, models


class Request(models.Model):
    _name = 'mlx.sample.request'
    _description = 'Synthetic sample request'
    _inherit = ['mail.thread']

    name = fields.Char(default='SMP-SYNTHETIC')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    partner_id = fields.Many2one('res.partner')
    state = fields.Selection([('draft', 'Draft'), ('in_progress', 'In Progress'),
                              ('resolved', 'Resolved'), ('cancelled', 'Cancelled')], default='draft')
    line_ids = fields.One2many('mlx.sample.request.line', 'request_id')


class Line(models.Model):
    _name = 'mlx.sample.request.line'
    _description = 'Synthetic sample line'

    request_id = fields.Many2one('mlx.sample.request', required=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template')
    supplier_id = fields.Many2one('res.partner')
    quantity = fields.Integer()
    sample_color = fields.Char()
    remarks = fields.Text()
    factory_ready_date = fields.Date()
    factory_comment = fields.Text()
    state = fields.Selection([('draft', 'Draft'), ('cancelled', 'Cancelled')], default='draft')


class Task(models.Model):
    _inherit = 'project.task'

    x_sample_line_id = fields.Integer()
    x_sample_ready_date = fields.Date()
    x_sample_logo = fields.Char()
