# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


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


 # Satış siparişi satırındaki teslim edilen miktar (qty_delivered) bilgisini göreve getiriyoruz.
    teslim_edilen_miktar = fields.Float(
        string="Teslim Edilen Miktar",
        related='ilgili_satis_satiri_id.qty_delivered',
        store=True,
        readonly=True,
        help="İlgili satış siparişi satırında teslim edilen miktar."
    )

    talep_edilen_miktar = fields.Float(
        string="Talep Edilen Miktar",
        related='ilgili_satis_satiri_id.product_uom_qty',
        store=True,
        readonly=True,
        help="İlgili satış siparişi satırında teslim edilen miktar."
    )

    montaJ_yapilan_miktar = fields.Float(
        string="Monte Edilen Miktar",
        related='ilgili_satis_satiri_id.task_montaj_progress',
        store=True,
        readonly=True,
        help="İlgili satış siparişi satırında teslim edilen miktar."
    )

    urun_adi = fields.Many2one(
        'product.template',
        string="Monte Edilen Ürün",
        related='ilgili_satis_satiri_id.product_template_id',
        store=True,  # BURASI ÇOK ÖNEMLİ! True olmalı.
        readonly=True,
        help="Bu görevin ilişkili olduğu satış siparişi satırındaki ürün."
    )

    def action_open_timesheet_entry(self):
        self.ensure_one()

        # Modül adınızın doğru olduğundan emin olun (örn: 'yuz18')
        custom_view_id = self.env.ref('yuz18.my_custom_timesheet_form_view').id

        return {
            'name': 'Özel Zaman Çizelgesi Girişi',
            'type': 'ir.actions.act_window',
            'res_model': 'account.analytic.line',
            'view_mode': 'form',
            'view_id': custom_view_id,
            'target': 'new',
            'context': {
                'default_project_id': self.project_id.id,
                'default_task_id': self.id,
                'default_employee_id': self.env.user.employee_id.id,  # Bu satır çalışan ID'sini gönderiyor
            },
        }

