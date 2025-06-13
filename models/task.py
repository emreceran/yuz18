# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # Bu alan, görevin hangi satış siparişi satırından oluşturulduğunu takip eder.
    # Alan adı değiştirildi: sale_line_id -> ilgili_satis_satiri_id
    ilgili_satis_satiri_id = fields.Many2one(
        'sale.order.line',
        string="İlgili Satış Satırı",  # Etiket Türkçe
        readonly=True,
        help="Bu görevin ilişkili olduğu satış siparişi satırı."
    )

    # Satış siparişi ID'sini de tutmak, navigasyon veya raporlama için faydalı olabilir.
    # Alan adı değiştirildi: sale_order_id -> ilgili_satis_siparisi_id
    ilgili_satis_siparisi_id = fields.Many2one(
        'sale.order',
        string="İlgili Satış Siparişi",  # Etiket Türkçe
        related='ilgili_satis_satiri_id.order_id',  # related alan da yeni isme göre güncellendi
        store=True,
        readonly=True,
        help="Bu görevin ilişkili olduğu satış siparişi."
    )

    # Ürün adı ve açıklamasını görev üzerinde tutmak isterseniz (isteğe bağlı):
    # product_id = fields.Many2one(
    #     'product.product',
    #     string="Ürün",
    #     related='ilgili_satis_satiri_id.product_id',
    #     store=True,
    #     readonly=True
    # )
    # product_description = fields.Char(
    #     string="Ürün Açıklaması",
    #     related='ilgili_satis_satiri_id.name',
    #     store=True,
    #     readonly=True
    # )