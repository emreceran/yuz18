# /yuz18/models/product_workcenter_list.py

from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Bu ürünün rotalarındaki İşlemler için uygun olan İş Merkezleri listesi
    allowed_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        string="Uygulanabilir İş Merkezleri",
        help="Bu ürünün tüm İşlemlerinde seçilebilecek İş Merkezleri listesi."
    )