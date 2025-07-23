# -*- coding: utf-8 -*-

from odoo import models, fields, api
import re # Regex modülünü import et
import logging
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # --- Boyutlar ve İlgili Alanlar ---
    en = fields.Integer( # Integer yapıldı
        string="En (cm)",
        compute="_compute_en_boy", # Birleştirilmiş compute
        readonly=False, # Manuel düzenlemeye izin ver
        help="Ürün varyant özelliklerinden veya manuel olarak girilir (Tamsayı)."
    )
    boy = fields.Integer( # Integer yapıldı
        string="Boy (cm)",
        compute="_compute_en_boy", # Birleştirilmiş compute
        readonly=False, # Manuel düzenlemeye izin ver
        help="Ürün varyant özelliklerinden veya manuel olarak girilir (Tamsayı)."
    )
    uzunluk = fields.Integer(
        string="Uzunluk (cm)", # Etiket güncellendi
        compute="_compute_adi_aciklama_uzunluk_from_variants",
        readonly=False, # Manuel düzenlemeye izin ver
        store=False,
        help="Özel ürün varyantlarından 'uzunluk: uzunluk:' kalıbına göre çıkarılır (Tamsayı). Manuel olarak değiştirilebilir."
    )
    yogunluk = fields.Float(
        string="Yoğunluk (g/cm³)",
        default=2.5,
        readonly=False, # Manuel düzenlemeye izin ver
        store=True, # Yoğunluk genellikle sabittir, saklayalım
        help="Malzemenin yoğunluğu (varsayılan: 2.5 g/cm³)."
    )
    hacim = fields.Float(
        string="Hacim (cm³)", # Etiket güncellendi
        compute="_compute_hacim",
        # store=True, # Hesaplanan değer saklansın
        readonly=True, # Hesaplanan alan
        help="Hesaplanan hacim: En(cm) x Boy(cm) x Uzunluk(cm)",
        digits = (16, 3)  # Gösterim hassasiyeti
    )
    agirlik = fields.Float(
        string="Ağırlık (Ton)",
        compute="_compute_agirlik",
        store=True, # Hesaplanan değer saklansın
        readonly=True, # Hesaplanan alan
        help="Hesaplanan ağırlık: Hacim(cm³) x Yoğunluk(g/cm³) / 1000"
    )

    # --- Ürün Bilgileri ---
    urun_adi = fields.Char(
        string="Ürün Adı",
        compute="_compute_adi_aciklama_uzunluk_from_variants",
        store=False,
        readonly=False, # Manuel düzenlemeye izin ver
        help="Özel ürün varyantlarından 'ürün adı: ürün adı:' kalıbına göre çıkarılır. Manuel olarak değiştirilebilir."
    )
    urun_aciklama = fields.Text(
        string="Ürün Açıklama",
        compute="_compute_adi_aciklama_uzunluk_from_variants",
        store=False,
        readonly=False, # Manuel düzenlemeye izin ver
        help="Özel ürün varyantlarından 'ürün açıklama: ürün açıklama:' kalıbına göre çıkarılır. Manuel olarak değiştirilebilir."
    )

    # --- Üretim/Proje Bilgileri ---
    kalip_id = fields.Many2one(  # <<< Char'dan Many2one'a değiştirildi
        comodel_name='mrp.workcenter',  # <<< Hedef model: İş Merkezi
        string="Kalıp/İş Merkezi",
        compute="_compute_kalip",
        store=True,
        readonly=True,  # Hesaplanan alan olduğu için readonly kalabilir
        help="İlgili ilk iş emrinin iş merkezi."  # Yardım metni güncellendi
    )


    procurement_total_quant = fields.Float( # Toplam miktar küsüratlı olabilir, Float daha uygun
        string="Tedarik Grubu Toplam Miktar", # İsim güncellendi
        compute="_compute_procurement_total_quant",
        store=True, # Hesaplanan değer saklansın
        readonly=True, # Hesaplanan alan
        help="Bu üretim emrinin ait olduğu tedarik grubundaki tüm üretim emirlerinin toplam miktarı."
    )
    proje_mikari = fields.Char(
        string="Üretim İlerleme", # Etiket güncellendi
        compute="_compute_proje_miktari",
        store=True, # Hesaplanan değer saklansın
        readonly=True, # Hesaplanan alan
        help="Mevcut üretim sırası / Tedarik grubu toplam miktar"
    )


    project_id = fields.Many2one(
        'project.project',
        string="Proje",
        compute="_compute_project_id", # Sadece bu compute kalsın
        store=True,
        # readonly=False, # Manuel değiştirilebilir olması istendi
    )

    # === COMPUTE METODLARI ===

    # En ve Boy için (Varsayılan Değer Hesaplama)
    # Not: Eğer En/Boy da product_description_variants'dan geliyorsa, bu metod yerine
    # _compute_adi_aciklama_uzunluk_from_variants metoduna eklenmelidir.
    # Bu kod, En/Boy'un ürünün variant attribute'larından geldiğini varsayar.
    @api.depends('product_id.product_template_attribute_value_ids')
    def _compute_en_boy(self):
        """
        Ürünün varyant özelliklerinden En ve Boy değerlerini alır ve Integer'a çevirir.
        Bu değerler başlangıç değeridir, manuel olarak değiştirilebilir.
        """
        for rec in self:
            # Eğer alanlar zaten manuel olarak doldurulmuşsa üzerine yazmamak iyi olabilir,
            # ama compute metodları genellikle bağımlılık değiştiğinde çalışır.
            # Şimdilik her çalıştığında hesaplayacak şekilde bırakalım.
            en_int, boy_int = 0, 0
            if rec.product_id and rec.product_id.product_template_attribute_value_ids:
                for ptav in rec.product_id.product_template_attribute_value_ids:
                    attr_name = ptav.attribute_id.name.strip().lower()
                    val_name = ptav.product_attribute_value_id.name
                    val_int = 0
                    try:
                        # Değeri sayıya çevirmeye çalış (Örn: "10 cm" -> 10)
                        numeric_val_str = ''.join(filter(str.isdigit or str == '.', val_name))
                        if numeric_val_str:
                            # Önce float'a çevirip sonra int'e çevirmek daha güvenli
                            val_int = int(float(numeric_val_str))
                    except ValueError:
                        val_int = 0
                        _logger.warning(f"Özellik ('{attr_name}':'{val_name}') tamsayıya çevrilemedi (Ürün: {rec.product_id.display_name})")

                    if attr_name == "en":
                        en_int = val_int
                    elif attr_name == "boy":
                        boy_int = val_int
            rec.en = en_int
            rec.boy = boy_int

    # Urun Adı, Açıklama ve Uzunluk için (Regex tabanlı)
    @api.depends('product_description_variants', 'product_id')
    def _compute_adi_aciklama_uzunluk_from_variants(self):
        """
        product_description_variants alanından regex kullanarak ürün adı,
        ürün açıklama ve uzunluk değerlerini çıkarır ve ilgili alanlara atar.
        Uzunluk tamsayı olarak atanır. Değerler manuel olarak değiştirilebilir.
        """
        # Regex'lerde kullanılan anahtarları kontrol edin: 'ürün adıx' mi 'ürün adı' mı?
        # Kodunuzdaki pattern'lere göre 'x' olmadan kullanıyorum:
        pattern_adi = re.compile(r"ürün adı:\s*ürün adı:\s*(.*?)\s*(?:ürün açıklama:|uzunluk:|$)", re.IGNORECASE)
        pattern_aciklama = re.compile(r"ürün açıklama:\s*ürün açıklama:\s*(.*?)\s*(?:uzunluk:|$)", re.IGNORECASE)
        pattern_uzunluk = re.compile(r"uzunluk:\s*uzunluk:\s*(\d+(?:[.,]\d+)?)\b", re.IGNORECASE)

        for rec in self:
            source_string = rec.product_description_variants
            extracted_adi = ""
            extracted_aciklama = ""
            uzunluk_int = 0

            if source_string:
                # Ürün Adı
                match_adi = pattern_adi.search(source_string)
                if match_adi: extracted_adi = match_adi.group(1).strip()
                # Ürün Açıklama
                match_aciklama = pattern_aciklama.search(source_string)
                if match_aciklama: extracted_aciklama = match_aciklama.group(1).strip()
                # Uzunluk
                match_uzunluk = pattern_uzunluk.search(source_string)
                if match_uzunluk:
                    extracted_uzunluk_str = match_uzunluk.group(1)
                    try: uzunluk_int = int(float(extracted_uzunluk_str.replace(',', '.')))
                    except ValueError: uzunluk_int = 0; _logger.warning(f"Uzunluk ('{extracted_uzunluk_str}') çevrilemedi.")

            # Fallback for urun_adi
            if not extracted_adi and rec.product_id: extracted_adi = rec.product_id.display_name

            rec.urun_adi = extracted_adi
            rec.urun_aciklama = extracted_aciklama
            rec.uzunluk = uzunluk_int

    # Hacim için
    @api.depends('en', 'boy', 'uzunluk')
    def _compute_hacim(self):
        """Hacmi cm³ cinsinden hesaplar."""
        for rec in self:
            try:
                # en, boy, uzunluk Integer
                rec.hacim = float( (rec.en or 0) * (rec.boy or 0) * (rec.uzunluk or 0) )
            except (ValueError, TypeError) as e:
                _logger.error(f"Hacim hesaplama hatası (ID: {rec.id}): {e}", exc_info=True)
                rec.hacim = 0.0

    # Ağırlık için (Hacim ve Yoğunluğa Bağlı)
    @api.depends('hacim', 'yogunluk')
    def _compute_agirlik(self):
        """ Ağırlığı Hacim (cm³) ve Yoğunluk (g/cm³) kullanarak kg cinsinden hesaplar. """
        for rec in self:
            try:
                hacim_cm3 = rec.hacim or 0.0
                dens_g_cm3 = rec.yogunluk or 0.0

                if hacim_cm3 > 0 and dens_g_cm3 > 0:
                    agirlik_gram = hacim_cm3 * dens_g_cm3
                    calculated_hacim = agirlik_gram / 1000000
                    rec.agirlik = round(calculated_hacim, 2)
                else:
                    rec.agirlik = 0.0
            except (ValueError, TypeError) as e:
                _logger.error(f"Ağırlık hesaplama hatası (ID: {rec.id}): {e}", exc_info=True)
                rec.agirlik = 0.0

    # Kalıp/İş Merkezi için (Güncellendi)
    @api.depends("workorder_ids.workcenter_id")
    def _compute_kalip(self):
        """Üretim emri ile ilişkili ilk iş emrinin iş merkezini (kayıt olarak) atar."""
        for rec in self:
            # İlk uygun iş emrinin iş merkezini bul
            # Eğer workorder_ids boşsa veya ilk iş emrinin workcenter'ı yoksa False ata
            if rec.workorder_ids and rec.workorder_ids[0].workcenter_id:
                # .name yerine doğrudan workcenter ID'sini (kaydı) ata
                rec.kalip_id = rec.workorder_ids[0].workcenter_id
            else:
                # Many2one alanı için boş değer False veya None'dur
                rec.kalip_id = False

    # Tedarik Grubu Toplam Miktarı için
    @api.depends("procurement_group_id.mrp_production_ids.product_qty")
    def _compute_procurement_total_quant(self):
        """İlişkili tedarik grubundaki tüm üretim emirlerinin toplam miktarını hesaplar."""
        for rec in self:
            if rec.procurement_group_id:
                mrp_productions = self.env['mrp.production'].search([
                    ('procurement_group_id', '=', rec.procurement_group_id.id)
                ])
                rec.procurement_total_quant = sum(mrp_productions.mapped("product_qty"))
            else:
                # Eğer grup yoksa, sadece kendi üretim miktarını gösterelim
                rec.procurement_total_quant = rec.product_qty

    # Üretim İlerleme Göstergesi için
    @api.depends('backorder_sequence', 'procurement_total_quant') # Bağımlılık doğru
    def _compute_proje_miktari(self):
        """Üretim ilerlemesini "Mevcut Sıra / Toplam Miktar" formatında gösterir."""
        for rec in self:
            # Miktarı .0 olmadan gösterelim
            total_quant_str = str(int(rec.procurement_total_quant or 0))
            # backorder_sequence 0'dan başlar, 1 ekleyerek göstermek daha anlaşılır olabilir
            # Kullanıcı beklentisine göre karar verin. Şimdilik 0'dan başlatıyorum.
            rec.proje_mikari = f"{rec.backorder_sequence} / {total_quant_str}"

    # Satış Siparişi için (Compute ile)
    @api.depends('procurement_group_id.sale_id')
    def _compute_sale_id(self):
        """Procurement Group üzerinden Sale Order'ı bulur."""
        for rec in self:
            # Odoo standardında mrp.production'da procurement_group_id zaten var.
            rec.sale_id = rec.procurement_group_id.sale_id if rec.procurement_group_id else False

    # Proje için (Compute ile)
    @api.depends('sale_id.project_ids') # sale_id compute ile geldiği için ona bağlamak daha iyi
    def _compute_project_id(self):
        """Satış siparişi ile ilişkili ilk projeyi bulur."""
        for rec in self:
            if rec.sale_id and rec.sale_id.project_ids:
                # Birden fazla proje varsa ilkini alır. Mantık değişebilir.
                rec.project_id = rec.sale_id.project_ids[0]
            else:
                rec.project_id = False

