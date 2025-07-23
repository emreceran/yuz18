from odoo import models, fields
from odoo.exceptions import UserError

class MrpProductionSplitCustomWizard(models.TransientModel):
    _name = 'mrp.production.split.custom.wizard'
    _description = 'Özel üretim bölme sihirbazı'

    production_id = fields.Many2one('mrp.production', required=True)
    produce_qty = fields.Float(string='Üretilecek Miktar', required=True)

    def action_split_custom(self):
        self.ensure_one()
        mo = self.production_id

        if self.produce_qty <= 0 or self.produce_qty >= mo.product_qty:
            raise UserError("Geçerli bir miktar girin.")

        kalan = mo.product_qty - self.produce_qty

        shared_vals = {
            'product_id': mo.product_id.id,
            'product_uom_id': mo.product_uom_id.id,
            'bom_id': mo.bom_id.id,
            'origin': mo.origin or mo.name,
            'company_id': mo.company_id.id,
            'user_id': mo.user_id.id,
            'picking_type_id': mo.picking_type_id.id,
            'location_src_id': mo.location_src_id.id,
            'location_dest_id': mo.location_dest_id.id,
            'procurement_group_id': mo.procurement_group_id.id,
            # 'routing_id': mo.routing_id.id if mo.routing_id else False,
            'project_id': mo.project_id.id if hasattr(mo, 'project_id') and mo.project_id else False,
            # 'sale_order_id': mo.sale_order_id.id if hasattr(mo, 'sale_order_id') and mo.sale_order_id else False,
            'priority': mo.priority,
            'custom_description': mo.custom_description,
            # 'date_planned_start': mo.date_planned_start,
            # 'date_planned_finished': mo.date_planned_finished,
        }

        mo1 = self.env['mrp.production'].create({
            **shared_vals,
            'product_qty': self.produce_qty,
        })
        mo1.action_confirm()
        mo1.button_mark_done()

        mo2 = self.env['mrp.production'].create({
            **shared_vals,
            'product_qty': kalan,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Bölünmüş Üretimler',
            'res_model': 'mrp.production',
            'domain': [('id', 'in', [mo1.id, mo2.id])],
            'view_mode': 'list,form',
        }
