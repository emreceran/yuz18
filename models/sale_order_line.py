# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _

class SaleOrderLine(models.Model):
    """
    Inherits sale.order.line to link Manufacturing Orders by filtering
    the parent Sale Order's existing mrp_production_ids field based on the line's product.
    Satırın ürününe göre ana Satış Siparişinin mevcut mrp_production_ids alanını
    filtreleyerek Üretim Emirlerini bağlamak için sale.order.line'ı devralır.
    """
    _inherit = 'sale.order.line'

    mrp_production_count = fields.Integer(
        "Üretilen Miktar", # Alan etiketi güncellendi
        compute='_compute_mrp_from_order', # Hesaplama metodu yeniden adlandırıldı
        store=False, # Performans için saklanmaz
        help="Number of Manufacturing Orders from the parent Sale Order "
             "that match the product on this line.", # Yardım metni güncellendi
        ) # MRP kullanıcıları için görünürlük
    mrp_production_ids = fields.Many2many(
        'mrp.production',
        string='Related MOs (Filtered from SO)', # Alan etiketi güncellendi
        compute='_compute_mrp_from_order', # Hesaplama metodu yeniden adlandırıldı
        store=False, # Performans için saklanmaz
        help="Manufacturing Orders from the parent Sale Order "
             "that match the product on this line.", # Yardım metni güncellendi
        copy=False, # Kopyalamayı engelle
        ) # MRP kullanıcıları için görünürlük

    # Yeni eklenecek project_id alanı
    proje_id = fields.Many2one(
        'project.project',
        string='Proje',
        related='order_id.project_id',  # Siparişin projesiyle otomatik ilişkilendir
        store=True,  # Veritabanında sakla
        readonly=False,  # Kullanıcının değiştirmesine izin ver
        ondelete='restrict',  # Proje silinirse satırın silinmesini engelle
        help="Bu satış siparişi satırıyla ilişkili proje."
    )

    # Bağımlılık order_id'nin mrp_production_ids alanına ve satırın product_id'sine olmalı
    @api.depends('order_id.mrp_production_ids', 'product_id')
    def _compute_mrp_from_order(self):
        """
        Computes Manufacturing Orders (MOs) for the Sale Order Line by
        filtering the MOs already computed on the parent Sale Order.
        It takes the `mrp_production_ids` from the `sale.order` and
        filters them to include only those matching the product_id of this line.

        Ana Satış Siparişinde zaten hesaplanmış olan ÜE'leri filtreleyerek
        Satış Siparişi Satırı için Üretim Emirlerini (ÜE) hesaplar.
        `sale.order`'dan `mrp_production_ids`'yi alır ve bunları yalnızca
        bu satırın `product_id`'si ile eşleşenleri içerecek şekilde filtreler.
        """
        # Başlangıçta tüm satırlar için alanları sıfırla/boşalt
        # self.mrp_production_ids = False # Many2many için False atamak yerine boş kayıt kümesi atamak daha iyi
        # self.mrp_production_count = 0

        for line in self:
            # Satırın bağlı olduğu siparişteki tüm ÜE'leri al
            # Eğer order_id boşsa veya mrp_production_ids hesaplanmamışsa (None olabilir) kontrol et
            order_mos = line.order_id.mrp_production_ids if line.order_id else self.env['mrp.production']

            # Bu ÜE'leri satırın ürününe göre filtrele
            # Eğer product_id boşsa veya order_mos boşsa, filtreleme boş sonuç döndürecektir
            product_specific_mos = order_mos.filtered(lambda mo: mo.product_id == line.product_id)

            # Sonuçları ata
            line.mrp_production_ids = product_specific_mos
            # Eğer amaç toplam ürün miktarı ise:
            line.mrp_production_count = sum(product_specific_mos.mapped('product_qty'))

    def action_view_mrp_production(self):
        self.ensure_one()
        mrp_production_ids = self.mrp_production_ids

        action = {
            'res_model': 'mrp.production',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', mrp_production_ids.ids)],
            'context': {'default_origin': self.order_id.name, 'default_product_id': self.product_id.id}
        }

        if len(mrp_production_ids) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': mrp_production_ids.id,
                # Tek bir kayıt için 'views' listesine gerek yok
            })
        else:  # Birden fazla MO olduğunda
            action.update({
                'name': _("MOs for %s (Product: %s)", self.order_id.name, self.product_id.display_name),
                'view_mode': 'list,form',  # BURASI KESİN OLARAK 'list,form' olmalı (Odoo 18)
                'views': False,  # BURASI DÜZELTİLDİ: Odoo'nun varsayılanı bulmasını sağla
                # Alternatif olarak boş bir liste de kullanılabilir: 'views': [],
            })
        return action

    # İndirme ve Montaj Görevi İlerlemesi (effective_hours olarak gösterilecek)
    task_indir_progress = fields.Float(  # Tipi Float olarak değiştirildi, ismi AYNI KALDI
        string='İndirilen Miktarı',  # Etiket biraz daha açıklayıcı yapıldı
        compute='_compute_task_progress_hours',  # Metot adı güncellendi
        digits='Product Unit of Measure',  # Saatler için uygun bir hassasiyet
        store=False,
        help="Bu satış siparişi satırı için 'İndirilecekler' görevi üzerinde harcanan toplam saat."
    )
    task_montaj_progress = fields.Float(  # Tipi Float olarak değiştirildi, ismi AYNI KALDI
        string='Montaj Miktarı',  # Etiket biraz daha açıklayıcı yapıldı
        compute='_compute_task_progress_hours',  # Metot adı güncellendi
        digits='Product Unit of Measure',  # Saatler için uygun bir hassasiyet
        store=False,
        help="Bu satış siparişi satırı için 'Montaj Yapılacaklar' görevi üzerinde harcanan toplam saat."
    )

    # Hesaplama Metodu: Görevlerin effective_hours değerlerini getirir
    @api.depends('order_id.project_id', 'order_id.project_id.task_ids.ilgili_satis_satiri_id',
                 'order_id.project_id.task_ids.effective_hours')
    def _compute_task_progress_hours(self):  # Metot adı güncellendi
        for line in self:
            line.task_indir_progress = 0.0  # float olarak başlat
            line.task_montaj_progress = 0.0  # float olarak başlat

            if not line.order_id.project_id:
                continue

            # Bu satış siparişi satırı ile doğrudan ilişkili görevleri ara
            related_tasks = self.env['project.task'].search([
                ('ilgili_satis_satiri_id', '=', line.id),
                ('project_id', '=', line.order_id.project_id.id),
            ])

            for task in related_tasks:
                if "İndirilecekler" in task.name:
                    line.task_indir_progress += task.effective_hours
                elif "Montaj Yapılacaklar" in task.name:
                    line.task_montaj_progress += task.effective_hours
