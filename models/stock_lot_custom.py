# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from collections import defaultdict, deque
from odoo.tools import OrderedSet
import logging
import re  # Regex için eklendi

_logger = logging.getLogger(__name__)


class StockLotCustom(models.Model):
    _inherit = 'stock.lot'

    # ADIM 1: MRP KAYIT BİLGİSİNİ HESAPLA (Lot'un adını kullanarak)
    mrp_producing_id = fields.Many2one(
        'mrp.production',
        string='Üretim Emri',
        compute='_compute_mrp_producing_id',
        store=True # Veritabanında sakla
    )
    
    # ADIM 2: PROJE BİLGİSİNİ BU MRP KAYDINDAN İLİŞKİLENDİR
    # BU ALAN İÇİN ARTIK COMPUTE METODU YAZILMAZ!
    project_id = fields.Many2one(
        'project.project',
        related='mrp_producing_id.project_id', 
        store=True,
        string='Proje',
        readonly=True # İlişkili alanlar genellikle salt okunur olmalıdır
    )
    
    # BU METOT SADECE mrp_producing_id alanını hesaplamalıdır!
    @api.depends('name')
    def _compute_mrp_producing_id(self):
        lot_names = self.mapped('name')
        
        # 1. Sorguyu Lot ID'si ile yapmak daha temiz/hızlıdır, ancak şimdilik lot adını kullanalım.
        mrp_productions = self.env['mrp.production'].search([
            ('lot_producing_id.name', 'in', lot_names)
            # ('project_id', '!=', False) filtrelemesi gereksiz, eşleşme yapıldıktan sonra proje kontrol edilebilir.
        ])
        
        mrp_map = {}
        for mrp in mrp_productions:
            lot_name = mrp.lot_producing_id.name
            # Projenin atanıp atanmadığı önemli değil, MRP'yi eşleştirmeliyiz
            if lot_name not in mrp_map:
                mrp_map[lot_name] = mrp.id # MRP ID'sini sakla

        # 4. Alanı Güncelle
        for lot in self:
            mrp_id = mrp_map.get(lot.name, False)
            lot.mrp_producing_id = mrp_id

    @api.model
    def _get_next_serial(self, company, product, sale_order_ref, project_id):
        """Return the next serial number to be attributed to the product."""

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

           
            # En son oluşturulan lotu bul (id'ye göre)
            if candidates:
                last_lot = candidates.sorted(key=lambda lot: lot.id)[-1]  # en son oluşturulan
                next_serial = self.generate_lot_names(last_lot.name, 2, code, sale_last_three)[1]['lot_name']
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


    def write(self, vals):
        # 1. Değişebilecek Lot'ları önceden yakala
        old_lot = self.mapped('lot_producing_id')
        
        # 2. Orijinal write işlemini çalıştır
        res = super().write(vals)

        # 3. Yeni Lot'u yakala
        new_lot = self.mapped('lot_producing_id')

        # 4. Hem eski hem de yeni Lot'lar üzerinde ilgili compute metodu tetikle
        # compute metodu mrp_producing_id olduğu için bunu çağırıyoruz.
        (old_lot | new_lot)._compute_mrp_producing_id()
        
        return res 

    # Oluşturma anında da tetikleme eklenmeli
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.lot_producing_id:
                record.lot_producing_id._compute_mrp_producing_id()
        return records

    # Create metodu için de benzer bir tetikleme ekleyin.

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

    def _auto_production_checks(self):
        self.ensure_one()
        print(self.lot_producing_id.id)
        return all(p.tracking == 'none' for p in self.move_raw_ids.product_id | self.move_finished_ids.product_id)\
            or (self.product_uom_qty == 1 and self.lot_producing_id.id) or (self.product_id.tracking != 'serial' and self.reservation_state in ('assigned', 'confirmed', 'waiting'))

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

    def action_mass_produce(self):
        self.ensure_one()
        self._check_company()
        if self.state not in ['draft', 'confirmed', 'progress', 'to_close'] or\
                self._auto_production_checks():
            return
        action = self.env["ir.actions.actions"]._for_xml_id("mrp.action_mrp_batch_produce")
        action['context'] = {
            'default_production_id': self.id,
        }
        return action
   
   
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
    
    