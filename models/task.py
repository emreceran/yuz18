# -*- coding: utf-8 -*-
from odoo import models, fields

class ProjectTask(models.Model):
    _inherit = 'project.task'

    # project.task modeline Lot/Seri No alanı ekliyoruz
    # Bu alan, stock.production.lot modeline bir Many2one ilişkisi kurar
    # x_lot_id = fields.Many2one(
    #     comodel_name='stock.production.lot', # Bağlanılacak model
    #     string='Lot/Seri No',              # Alanın etiketi (arayüzde görünecek)
    #     copy=False,                        # Görev kopyalandığında bu alan kopyalanmasın
    #     index=True,                        # Veritabanında index oluştur (aramaları hızlandırabilir)
    #     tracking=True,                     # Değişikliklerin chatter'da izlenmesini sağla
    #     help="Bu görevle ilişkili üretim lotu/seri numarası." # Yardım metni
    # )

    # İsteğe bağlı: Sadece seri numarasının adını (metin olarak) göstermek için
    x_lot_id = fields.Char(
        string='Seri Numarası (Metin)',
        readonly=True,
        store=True # Arama ve gruplama için saklanması önerilir
    )