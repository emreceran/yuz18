# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
import re
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mrp_production_count = fields.Integer(
        "Üretilen Miktar",
        compute='_compute_mrp_data',
        store=False,
        help="Bu satış satırı için ilgili Üretim Emirlerinden tamamlanmış ürün miktarı.",
    )
    mrp_production_ids = fields.Many2many(
        'mrp.production',
        string='İlgili Üretim Emirleri',
        compute='_compute_mrp_data',
        store=False,
        help="Ana Satış Siparişinden bu satırdaki ürünle eşleşen Üretim Emirleri.",
        searchable=True,
    )

    # --- HESAPLAMA METOTLARI ---

    @api.depends('order_id.mrp_production_ids', 'product_id',
                 'order_id.mrp_production_ids.qty_produced')
    def _compute_mrp_data(self):
        """
        MO'ları filtreler ve bitmiş üretilen miktarı (qty_produced) hesaplar.
        """
        for line in self:
            order_mos = line.order_id.mrp_production_ids if line.order_id else self.env['mrp.production']
            product_specific_mos = order_mos.filtered(lambda mo: mo.product_id == line.product_id)

            line.mrp_production_ids = product_specific_mos
            line.mrp_production_count = sum(mo.qty_produced for mo in product_specific_mos)

    def action_view_mrp_production(self):
        self.ensure_one()
        mrp_production_ids = self.mrp_production_ids

        action = {
            'res_model': 'mrp.production',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', mrp_production_ids.ids)],
            'context': {'default_origin': self.order_id.name, 'default_product_id': self.product_id.id}
        }

        if len(mrp_production_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': mrp_production_ids.id,
            })
        else:
            action.update({
                'name': _("MOs for %s (Product: %s)", self.order_id.name, self.product_id.display_name),
                'view_mode': 'list,form',
                'views': False,
            })
        return action

