from odoo import models, fields, api

class ProductPlanningGroup(models.TransientModel):
    """Geçici model - Step 1'de ürün gruplarını tutar"""
    _name = 'product.planning.group'
    _description = 'Ürün Planlama Grubu'

    wizard_id = fields.Many2one('mrp.batch.planning.wizard.step1', string="Wizard", required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Ürün", required=True)
    diameter_width = fields.Float(string="En/Çap (cm)")
    height = fields.Float(string="Boy (cm)")
    length = fields.Float(string="Uzunluk (cm)")
    available_mo_count = fields.Integer(string="Bekleyen Adet", compute='_compute_available_mo_count', store=True)
    selected_count = fields.Integer(string="Planlanacak Adet", default=0)
    mo_ids = fields.Many2many('mrp.production', string="Üretim Emirleri")
    
    # YENİ: Kalıp seçimi için
    available_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        compute='_compute_available_workcenters',
        string='Uygun Kalıplar'
    )
    selected_workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Kalıp',
        domain="[('id', 'in', available_workcenter_ids)]"
    )


    @api.depends('mo_ids')
    def _compute_available_mo_count(self):
        """Gruptaki toplam MO sayısını hesapla"""
        for rec in self:
            rec.available_mo_count = len(rec.mo_ids)

    @api.onchange('selected_count')
    def _onchange_selected_count(self):
        """Seçilen miktar kontrolü"""
        for rec in self:
            if rec.selected_count < 0:
                rec.selected_count = 0
            elif rec.selected_count > rec.available_mo_count:
                rec.selected_count = rec.available_mo_count
    
    @api.depends('product_id', 'diameter_width', 'height')
    def _compute_available_workcenters(self):
        """Ürüne uygun kalıpları hesapla"""
        for rec in self:
            if not rec.product_id:
                rec.available_workcenter_ids = self.env['mrp.workcenter']
                continue
            
            tmpl = rec.product_id.product_tmpl_id
            suitable_wcs = self.env['mrp.workcenter']
            
            # 1. Ürünün kendi allowed list'i varsa oradan başla
            if tmpl.allowed_workcenter_ids:
                suitable_wcs = tmpl.allowed_workcenter_ids
            else:
                # 2. Yoksa tüm workcenter'lardan ara
                suitable_wcs = self.env['mrp.workcenter'].search([])
            
            # 3. ÖNEMLİ: Çap kontrolü (x_check_strand_rules varsa)
            if tmpl.x_check_strand_rules and suitable_wcs:
                # Allowed list içinden sadece uygun çapta olanları filtrele
                # Birebir uyumluluk gerekli (== kontrolü)
                suitable_wcs = suitable_wcs.filtered(
                    lambda wc: wc.x_width_capacity == rec.diameter_width 
                    and wc.x_height_capacity == rec.height
                )
            
            rec.available_workcenter_ids = suitable_wcs
