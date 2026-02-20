# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Step2ProductGroup(models.TransientModel):
    """Step 2'de kalıp seçildiğinde ürün bazlı gruplama için geçici model"""
    _name = 'step2.product.group'
    _description = 'Step 2 Ürün Grubu'

    wizard_id = fields.Many2one(
        'mrp.batch.planning.wizard', 
        string="Wizard", 
        required=True, 
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product', 
        string="Ürün", 
        required=True
    )
    
    diameter_width = fields.Float(string="En/Çap (cm)")
    height = fields.Float(string="Boy (cm)")
    
    available_mo_count = fields.Integer(
        string="Bekleyen", 
        compute='_compute_available_mo_count', 
        store=True
    )
    
    selected_count = fields.Integer(
        string="Planlanacak", 
        default=0
    )
    
    mo_ids = fields.Many2many(
        'mrp.production', 
        'step2_group_mo_rel',
        'group_id',
        'production_id',
        string="Üretim Emirleri"
    )
    
    total_length = fields.Float(
        string="Seçilen Uzunluk",
        compute='_compute_total_length'
    )

    @api.depends('mo_ids')
    def _compute_available_mo_count(self):
        for rec in self:
            rec.available_mo_count = len(rec.mo_ids)
    
    @api.depends('selected_count', 'mo_ids')
    def _compute_total_length(self):
        for rec in self:
            if rec.selected_count <= 0:
                rec.total_length = 0.0
                continue
            # İlk N adet MO'nun toplam uzunluğu
            sorted_mos = rec.mo_ids.sorted(key=lambda m: m.date_deadline or fields.Datetime.now())
            selected_mos = sorted_mos[:rec.selected_count]
            rec.total_length = sum(mo.uzunluk or 0 for mo in selected_mos)

    @api.onchange('selected_count')
    def _onchange_selected_count(self):
        for rec in self:
            if rec.selected_count < 0:
                rec.selected_count = 0
            elif rec.selected_count > rec.available_mo_count:
                rec.selected_count = rec.available_mo_count
