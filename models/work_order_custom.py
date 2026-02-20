# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo import models, fields, _
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class MrpWorkOrder(models.Model):
    _inherit = "mrp.workorder"


    allowed_workcenter_domain = fields.Char(
        compute="_compute_allowed_workcenter_domain",
        store=True,
        readonly=True,
    )

    product_allowed_workcenter_ids = fields.Many2many(
        'mrp.workcenter',  # Model adını mutlaka veriyoruz!
        string="Ürünün İzin Verdiği Merkezler",
        compute="_compute_product_workcenter",
        store=True
    )

    project_name = fields.Char(
        string="Proje Adı",
        related='production_id.project_id.name',
        # store=True
    )

    urun_adi = fields.Char(
        string="Ürün Adı",
        related='production_id.urun_adi',
        # store=True
    )

    @api.depends('product_allowed_workcenter_ids', 'production_id.product_tmpl_id.allowed_workcenter_ids')
    def _compute_allowed_workcenter_domain(self):
        for rec in self:
            ids = rec.product_allowed_workcenter_ids.ids or []
            rec.allowed_workcenter_domain = str([('id', 'in', ids)])
    @api.depends('production_id.product_tmpl_id.allowed_workcenter_ids')
    def _compute_product_workcenter(self):
        for rec in self:
            print(rec.product_allowed_workcenter_ids)
            print(rec.production_id.product_tmpl_id.allowed_workcenter_ids)
            rec.product_allowed_workcenter_ids=rec.production_id.product_tmpl_id.allowed_workcenter_ids


    @api.depends('project_name', 'urun_adi')
    @api.depends_context('prefix_product')
    def _compute_display_name(self):
        for wo in self:
            wo.display_name = f"{wo.project_name} / {wo.urun_adi}"
            if self.env.context.get('prefix_product'):
                wo.display_name = f"{wo.product_id.name} - {wo.production_id.name} - {wo.name}"

  