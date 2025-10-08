# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re  # Regex için eklendi

_logger = logging.getLogger(__name__)


class StockLotCustom(models.Model):
    _inherit = 'stock.lot'

    @api.model
    def _get_next_serial(self, company, product, sale_order_ref):
        """Return the next serial number to be attributed to the product."""

        print("**")
        print("**")
        print("**")
        print(product.name)
        print(product.product_tmpl_id)
        print(product.product_tmpl_id.name)
        print("**")
        print("**")
        print("**")

        if product.tracking != "none":
            # Sadece ilgili sale order referansını içeren lotları filtrele
            last_three = sale_order_ref[-3:]
            candidates = self.env['stock.lot'].search([
                '|',
                ('company_id', '=', company.id),
                ('company_id', '=', False),
                ('name', 'like', f"%{last_three}%")
            ], order='id DESC')

            filtered = candidates.filtered(lambda lot: lot.name[4:7] == last_three)

            # for lot in filtered:
            #     print( lot.name + "----" + str(lot.create_date))       
           
            # En son oluşturulan lotu bul (id'ye göre)
            if filtered:
                last_lot = filtered.sorted(key=lambda lot: lot.id)[-1]  # en son oluşturulan
                next_serial = self.generate_lot_names(last_lot.name, 2)[1]['lot_name']
                print(next_serial)
                print("next_serial")
                return next_serial
        return False

    @api.model
    def generate_lot_names(self, first_lot, count):
        """Generate structured lot names: YYPPSSSCCCC → year, product=03, saleorder, counter."""
        if len(first_lot) < 11:
            raise UserError("Lot format geçersiz. En az 11 karakter bekleniyor.")

        # Sale order kısmını koru
        sale_order = first_lot[4:7]

        # Güncel yıl al (son iki hane)
        year = str(fields.Date.today().year % 100).zfill(2)

        # Ürün kodunu sabit tut
        product_code = "03"

        # Sayaç kısmını al
        try:
            counter = int(first_lot[7:11])
        except ValueError:
            counter = 0

        # Yeni lotlar üret
        return [{
            'lot_name': f"{year}{product_code}{sale_order}{str(counter + i).zfill(4)}"
        } for i in range(count)]


class MrpProductionCustom(models.Model):
    _inherit = 'mrp.production'

    def _prepare_stock_lot_values(self):
        self.ensure_one()
        sale_order_ref = self.origin or ''
        name = self.env['stock.lot']._get_next_serial(self.company_id, self.product_id, sale_order_ref)
        if not name:
            raise UserError(_("Please set the first Serial Number or a default sequence"))
        return {
            'product_id': self.product_id.id,
            'name': name,  
        }

class MrpBatchProduceCustom(models.TransientModel):
    _inherit = 'mrp.batch.produce'
    @api.depends('production_id')
    def _compute_lot_name(self):

        sale_order_ref = self.production_id.origin or ''
        for wizard in self:
            if wizard.lot_name:
                continue
            wizard.lot_name = self.production_id.lot_producing_id.name
            if not wizard.lot_name:
                wizard.lot_name = self.env['stock.lot']._get_next_serial(self.production_id.company_id, self.production_id.product_id, sale_order_ref)

# class ProductTemplateCustom(models.Model):
#     _inherit = 'product.template'

#     x_product_group = fields.Char(string="Ürün Grubu", default="01")