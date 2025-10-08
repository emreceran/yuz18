# -*- coding: utf-8 -*-

from odoo import models, fields, api
import re # Regex modülünü import et
import logging
from odoo.exceptions import UserError


class MrpWorkOrder(models.Model):
    _inherit = "mrp.workorder"

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

    @api.depends('project_name', 'urun_adi')
    @api.depends_context('prefix_product')
    def _compute_display_name(self):
        for wo in self:
            wo.display_name = f"{wo.project_name} / {wo.urun_adi}"
            if self.env.context.get('prefix_product'):
                wo.display_name = f"{wo.product_id.name} - {wo.production_id.name} - {wo.name}"

