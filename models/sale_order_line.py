# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
import re
import logging

_logger = logging.getLogger(__name__)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mrp_production_count = fields.Integer(
        "Üretilen Miktar",  # Alan etiketi güncellendi: 'Üretilen Miktar' yerine 'Bitmiş Üretilen Miktar'
        compute='_compute_mrp_data',  # Metot adı güncellendi (tutarlılık için _compute_mrp_data kullanıyoruz)
        store=False,
        help="Bu satış satırı için ilgili Üretim Emirlerinden tamamlanmış ürün miktarı.",
    )
    mrp_production_ids = fields.Many2many(
        'mrp.production',
        string='İlgili Üretim Emirleri',  # Önceki değişiklikten
        compute='_compute_mrp_data',  # Metot adı güncellendi
        store=False,
        help="Ana Satış Siparişinden bu satırdaki ürünle eşleşen Üretim Emirleri.",
        searchable=True,
    )

    # Yeni eklenen alan: Üretim Emirlerinden toplam üretilen miktarı tutacak (önceki cevabımdaki `mo_produced_qty`)
    # Sizin gönderdiğiniz kodda bu alan gözükmüyor. Eğer kullanmaya devam etmek istiyorsanız, eklemelisiniz.
    # Ancak siz `mrp_production_count`'u "Üretilen Miktar" olarak kullanmak istediğiniz için,
    # bu alanı `mo_produced_qty` yerine kullanabiliriz.
    # Eğer `mo_production_progress_percentage` kullanmaya devam edecekseniz,
    # onun bağımlılığı olan `mo_produced_qty`'yi de tutmanız gerekecektir.

    # Mevcut kodunuzdaki `mrp_production_count`'ı hedef miktar yerine bitmiş miktar yapmak için:

    # Proje alanı (mevcut kodunuzdaki gibi)
    proje_id = fields.Many2one(
        'project.project',
        string='Proje',
        related='order_id.project_id',
        store=True,
        readonly=False,
        ondelete='restrict',
        help="Bu satış siparişi satırıyla ilişkili proje."
    )

    # İndirme ve Montaj Görevi İlerlemesi (mevcut kodunuzdaki gibi)
    task_indir_progress = fields.Float(
        string='İndirilen Miktarısudo',
        compute='_compute_task_progress_hours',
        digits='Product Unit of Measure',
        store=False,
        help="Bu satış siparişi satırı için 'İndirilecekler' görevi üzerinde harcanan toplam saat."
    )
    task_montaj_progress = fields.Float(
        string='Montaj Miktarı',
        compute='_compute_task_progress_hours',
        digits='Product Unit of Measure',
        store=False,
        help="Bu satış siparişi satırı için 'Montaj Yapılacaklar' görevi üzerinde harcanan toplam saat."
    )

    # Ürün Adı ile ilgili alan (mevcut kodunuzdaki gibi)
    product_display_name_custom = fields.Char(
        string='Ürün Adı',
        compute='_compute_product_names_and_description',
        readonly=False,
        store=True,
        help="Açıklama alanından ayrıştırılan ürün adı bilgisi."
    )

    # --- HESAPLAMA METOTLARI ---

    # `_compute_mrp_from_order` metodunu `_compute_mrp_data` olarak güncelledik (önceki yanıtlardan tutarlılık için)
    # Bağımlılıkları da `qty_produced`'a göre güncellendi.
    @api.depends('order_id.mrp_production_ids', 'product_id',
                 'order_id.mrp_production_ids.qty_produced')  # qty_produced'a bağımlılık eklendi
    def _compute_mrp_data(self):  # Metot adı _compute_mrp_data olarak değiştirildi
        """
        MO'ları filtreler ve bitmiş üretilen miktarı (qty_produced) hesaplar.
        """
        for line in self:
            order_mos = line.order_id.mrp_production_ids if line.order_id else self.env['mrp.production']

            # Bu ÜE'leri satırın ürününe göre filtrele VE SADECE 'done' (tamamlandı) durumundaki ÜE'leri al (isteğe bağlı ama mantıklı)
            # Eğer sadece bitmiş MO'ları saymak istiyorsanız:
            # product_specific_mos = order_mos.filtered(lambda mo: mo.product_id == line.product_id and mo.state == 'done')
            # Eğer 'done' durumu yoksa veya tüm MO'lardan üretileni almak istiyorsanız sadece product_id'ye göre filtreleyin:
            product_specific_mos = order_mos.filtered(lambda mo: mo.product_id == line.product_id)

            line.mrp_production_ids = product_specific_mos
            # BURADA DEĞİŞİKLİK: 'product_qty' yerine 'qty_produced' kullanıldı
            line.mrp_production_count = sum(mo.qty_produced for mo in product_specific_mos)

    # action_view_mrp_production metodu (mevcut kodunuzdaki gibi)
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
            })
        else:
            action.update({
                'name': _("MOs for %s (Product: %s)", self.order_id.name, self.product_id.display_name),
                'view_mode': 'list,form',
                'views': False,
            })
        return action

    # task_indir_progress ve task_montaj_progress için compute metodu (mevcut kodunuzdaki gibi)
    @api.depends('order_id.project_id', 'order_id.project_id.task_ids.ilgili_satis_satiri_id',
                 'order_id.project_id.task_ids.effective_hours')
    def _compute_task_progress_hours(self):
        for line in self:
            line.task_indir_progress = 0.0
            line.task_montaj_progress = 0.0

            if not line.order_id.project_id:
                continue

            related_tasks = self.env['project.task'].search([
                ('ilgili_satis_satiri_id', '=', line.id),
                ('project_id', '=', line.order_id.project_id.id),
            ])

            for task in related_tasks:
                if "İndirilecekler" in task.name:
                    line.task_indir_progress += task.effective_hours
                elif "Montaj Yapılacaklar" in task.name:
                    line.task_montaj_progress += task.effective_hours

    @api.depends('name', 'product_id')
    def _compute_product_names_and_description(self):
        for line in self:
            _logger.info(
                f"Processing SaleOrderLine ID: {line.id}, Product ID: {line.product_id.id if line.product_id else 'None'}")
            _logger.info(f"Type of line.product_id: {type(line.product_id)}")
            _logger.info(f"Is line.product_id a recordset? {isinstance(line.product_id, models.BaseModel)}")

            current_name = line.name or ""
            extracted_product_name = False
            cleaned_description = current_name

            # YENİ REGEX VE STRATEJİ:
            # - `re.DOTALL` (re.S) ile birden fazla satırı kapsa.
            # - `re.IGNORECASE` (re.I) ile büyük/küçük harf duyarsızlığı.
            # - `(?m)` = re.MULTILINE bayrağı için. ^ ve $ satır başlangıcı/sonunu işaret etsin diye.
            # - Pattern: 'Ürün adı: Ürün adı: ' ile başlayan ve sonraki 'Ürün açıklama:', 'Uzunluk:' veya satır sonu ile biten kısmı yakala.

            pattern_to_extract = r'(?m)^Ürün\s*adı:\s*Ürün\s*adı:\s*(.*?)(?=\nÜrün\s*açıklama:|\nUzunluk:|$)'
            match = re.search(pattern_to_extract, current_name, re.DOTALL | re.IGNORECASE)

            if match:
                extracted_product_name = match.group(1).strip()
                line.product_display_name_custom = extracted_product_name
                _logger.info(f"Extracted product name: '{extracted_product_name}'")

                # Eşleşen kısmı orijinal metinden çıkar
                cleaned_description = re.sub(pattern_to_extract, '', current_name, 1, re.DOTALL | re.IGNORECASE).strip()
                _logger.info(f"Cleaned description (after removing product name pattern): '{cleaned_description}'")

                # Fazla boşlukları, boş satırları ve baştaki/sondaki özel karakterleri temizle
                cleaned_description = re.sub(r'[\r\n]+', '\n',
                                             cleaned_description).strip()  # Birden fazla yeni satırı tek satıra indir
                cleaned_description = re.sub(r'\s{2,}', ' ',
                                             cleaned_description).strip()  # Birden fazla boşluğu tek boşluğa
                cleaned_description = re.sub(r'^[,\s(]+|[,\s)]+$', '',
                                             cleaned_description).strip()  # Başında/sonunda parantez/virgül temizle

                # Eğer açıklama tamamen boş kalırsa ve geçerli bir ürün varsa, ürünün display_name'ini kullan
                if not cleaned_description and line.product_id and line.product_id.exists():
                    line.name = line.product_id.display_name
                    _logger.info(
                        f"Cleaned description was empty, set line.name to product_display_name: {line.product_id.display_name}")
                elif not cleaned_description:
                    line.name = ""  # Açıklama tamamen boşsa boş bırak
                    _logger.info("Cleaned description was empty, set line.name to empty string.")
                else:
                    line.name = cleaned_description  # Temizlenmiş açıklamayı ata
                    _logger.info(f"Final line.name set to: '{line.name}'")

            else:
                _logger.info("Product name pattern not found in description.")
                # Eğer pattern bulunamazsa, product_display_name_custom'ı ürünün display_name'iyle doldur.
                # 'name' alanına dokunmuyoruz, olduğu gibi kalır.
                if line.product_id and line.product_id.exists():
                    line.product_display_name_custom = line.product_id.display_name
                    _logger.info(
                        f"Pattern not found, set product_display_name_custom to product_display_name: {line.product_id.display_name}")
                else:
                    line.product_display_name_custom = False
                    _logger.info("Product not found, product_display_name_custom set to False.")

                # Eğer ürün yoksa, name alanını temizle (pattern bulunamadıysa da bu mantık uygulanabilir)
                if not line.product_id:
                    line.name = ""
                    _logger.info("No product linked, line.name cleared.")