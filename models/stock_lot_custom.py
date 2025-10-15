# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re  # Regex için eklendi

_logger = logging.getLogger(__name__)


class StockLotCustom(models.Model):
    _inherit = 'stock.lot'

    # 1. Hesaplanan Alanı Tanımla
    project_id = fields.Many2one(
        'project.project',
        string='Proje',
        compute='_compute_project_id',
        store=True, # Projenin veritabanında saklanmasını sağlar (filtreleme için gerekli)
        readonly=True # Kullanıcı tarafından değiştirilmesini engeller
    )

    # 2. Hesaplama Metodu
    @api.depends('name')
    def _compute_project_id(self):
        # 1. Seri/Parti (stock.lot) kayıtlarının adlarını al
        lot_names = self.mapped('name')
        
        # 2. mrp.production'da bu lot isimlerine sahip (lot_producing_id) kayıtları bul
        #    Burada lot_producing_id'nin tipinin stock.lot olduğunu varsayıyoruz.
        mrp_productions = self.env['mrp.production'].search([
            ('lot_producing_id.name', 'in', lot_names),
            ('project_id', '!=', False) # Sadece Projesi tanımlı olanları al
        ])
        
        # 3. Lot adına göre MRP üretim emirlerini eşleştir (Sözlük oluştur)
        mrp_map = {}
        for mrp in mrp_productions:
            lot_name = mrp.lot_producing_id.name
            # Eğer bir lot birden fazla MRP'ye atanmışsa (ki olmamalı), ilkini al
            if lot_name not in mrp_map:
                mrp_map[lot_name] = mrp.project_id.id

        # 4. Alanı Güncelle
        for lot in self:
            # Kendi lot ismini (name) kullanarak eşleştirme sözlüğünden proje ID'yi çek
            project_id = mrp_map.get(lot.name, False)
            lot.project_id = project_id


    @api.model
    def _get_next_serial(self, company, product, sale_order_ref, project_id):
        """Return the next serial number to be attributed to the product."""

        print("**")
        print("**")
        print("**")
        print(project_id.name)
        print(product.name)
        print(product.product_tmpl_id)
        print(product.product_tmpl_id.name)
        print(product.product_tmpl_id.urun_kodu)
        print("**")
        print("**")
        print("**")
        
        

        if product.tracking != "none":

            code = product.product_tmpl_id.urun_kodu
            # Sadece ilgili sale order referansını içeren lotları filtrele
            sale_last_three = sale_order_ref[-3:]
            candidates = self.env['stock.lot'].search([
                '|',
                ('company_id', '=', company.id),
                ('company_id', '=', False),
                ('project_id', '=', project_id.name)
            ], order='id DESC')

            # filtered = candidates.filtered(lambda lot: lot.name[4:7] == last_three)

            for lot in candidates:
                print( lot.name + "----" + str(lot.create_date))       
           
            # En son oluşturulan lotu bul (id'ye göre)
            if candidates:
                last_lot = candidates.sorted(key=lambda lot: lot.id)[-1]  # en son oluşturulan
                next_serial = self.generate_lot_names(last_lot.name, 2, code, sale_last_three)[1]['lot_name']
                print(next_serial)
                print("next_serial")
                return next_serial
            else:
                next_serial = self.generate_lot_names("00000000000", 2, code, sale_last_three)[1]['lot_name']
                return next_serial
                
        return False

    @api.model
    def generate_lot_names(self, first_lot, count, code, sale_last_three):
        """Generate structured lot names: YYPPSSSCCCC → year, saleorder, product=ürün kodu, counter."""
        if len(first_lot) < 11:
            raise UserError("Lot format geçersiz. En az 11 karakter bekleniyor.")


        print("sale_order")
        print(sale_last_three)
        print("sale_order")

        # Güncel yıl al (son iki hane)
        year = str(fields.Date.today().year % 100).zfill(2)

        # Sayaç kısmını al
        try:
            counter = int(first_lot[7:11])
        except ValueError:
            counter = 0

        # Yeni lotlar üret
        return [{
            'lot_name': f"{year}{sale_last_three}{code}{str(counter + i).zfill(4)}"
        } for i in range(count)]


class MrpProductionCustom(models.Model):
    _inherit = 'mrp.production'

    def _prepare_stock_lot_values(self):
        self.ensure_one()
        sale_order_ref = self.origin or ''
        name = self.env['stock.lot']._get_next_serial(self.company_id, self.product_id, sale_order_ref,self.project_id)
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
        project_id = self.production_id.project_id
        for wizard in self:
            if wizard.lot_name:
                continue
            wizard.lot_name = self.production_id.lot_producing_id.name
            if not wizard.lot_name:
                wizard.lot_name = self.env['stock.lot']._get_next_serial(self.production_id.company_id, self.production_id.product_id, sale_order_ref, project_id)

    def action_generate_production_text(self):
        self.ensure_one()
        if not self.lot_name:
            raise UserError(_('Please specify the first serial number you would like to use.'))

        code = self.production_id.product_tmpl_id.urun_kodu
        # Sadece ilgili sale order referansını içeren lotları filtrele
        sale_order_ref = self.production_id.origin or ''
        sale_last_three = sale_order_ref[-3:]
        lots_name = self.env['stock.lot'].generate_lot_names(self.lot_name, self.lot_qty, code, sale_last_three)
        self.production_text = '\n'.join([lot['lot_name'] for lot in lots_name])
        action = self.env["ir.actions.actions"]._for_xml_id("mrp.action_mrp_batch_produce")
        action['res_id'] = self.id
        return action


