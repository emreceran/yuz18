# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re  # Regex için eklendi

_logger = logging.getLogger(__name__)


class StockLotCustom(models.Model):
    _inherit = 'stock.lot'

    def _get_so_from_production_custom(self, production_id):
        # Bu yardımcı fonksiyon, bir Üretim Emrinden (MO) Satış Siparişini (SO) bulur.
        # Önceki cevaplardaki gibi kullanılabilir.
        prod = self.env['mrp.production'].browse(production_id)
        if hasattr(prod, 'sale_order_id') and prod.sale_order_id:
            return prod.sale_order_id
        if prod.origin:
            so_name = prod.origin.split(':')[0] if prod.origin and ':' in prod.origin else prod.origin
            so = self.env['sale.order'].search([('name', '=', so_name)], limit=1)
            if so:
                return so
        if prod.group_id:
            moves = self.env['stock.move'].search([
                ('group_id', '=', prod.group_id.id),
                ('sale_line_id', '!=', False)
            ], limit=1)
            if moves and moves.sale_line_id:
                return moves.sale_line_id.order_id
        _logger.warning(f"Üretim Emri {prod.name} için Satış Siparişi bulunamadı.")
        return False

    @api.model_create_multi
    def create(self, vals_list):
        processed_vals_list = []
        for vals in vals_list:
            generate_custom_sn = self.env.context.get('generate_custom_simple_sn_for_mo', False)
            mo_id = self.env.context.get('custom_simple_sn_mo_id')
            # Üretim Emri (MO) içindeki mevcut ürünün 1 tabanlı sırası (örn: 1, 2, 3...)
            item_sequence_in_mo = self.env.context.get('custom_simple_sn_item_seq_in_mo', 1)

            if vals.get('name') or not generate_custom_sn or not mo_id or not vals.get('product_id'):
                if 'company_id' not in vals:
                    vals['company_id'] = vals.get('company_id', self.env.company.id)
                processed_vals_list.append(vals)
                continue

            product = self.env['product.product'].browse(vals['product_id'])
            if product.tracking != 'serial':
                if 'company_id' not in vals:
                    vals['company_id'] = vals.get('company_id', self.env.company.id)
                processed_vals_list.append(vals)
                continue

            mo = self.env['mrp.production'].browse(mo_id)
            so = self._get_so_from_production_custom(mo.id)

            if so and so.name:
                so_name_str = so.name
                # SO adından sayısal kısmı çıkar (örn: "s2502" -> "2502")
                # Bu regex, string içindeki tüm sayıları birleştirir.
                # Eğer SO adı "SO-001-A-2502" ise sonuç "0012502" olabilir.
                # Sadece belirli bir kısımdaki sayıları almak için regex'i özelleştirmeniz gerekebilir.
                # Örnek: Sadece sondaki sayıları almak için: found_numbers = re.findall(r'\d+$', so_name_str)
                numerical_so_part = "".join(filter(str.isdigit, so_name_str))

                if not numerical_so_part:  # Sayısal kısım bulunamazsa
                    _logger.warning(f"Satış Siparişi adı '{so_name_str}' içinden sayısal kısım çıkarılamadı.")
                    # Fallback: Standart Odoo seri numarası veya hata
                    if not vals.get('name'):  # Eğer özel isim atanamadıysa
                        vals['name'] = self.env['ir.sequence'].next_by_code('stock.lot.serial') or _('HATA_SO_SN')
                    numerical_so_part = "SO kısmı Hatalı"  # Hata durumunda log için

                # Sıra numarasını formatla (örn: 1 -> "001")
                sequence_part_str = f"{item_sequence_in_mo:03d}"  # 3 haneli, başına sıfır ekler

                custom_serial_name = f"{numerical_so_part}{sequence_part_str}"  # Örn: "2502001"
                vals['name'] = custom_serial_name
                _logger.info(
                    f"Özel Basit Seri Numarası Üretildi: {custom_serial_name} (ÜE: {mo.name}, Ürün Sıra: {item_sequence_in_mo})")
            else:
                _logger.warning(f"Özel basit seri numarası için SO bilgisi eksik (ÜE: {mo.name}).")
                if not vals.get('name'):
                    vals['name'] = self.env['ir.sequence'].next_by_code('stock.lot.serial') or _('TASLAK_SN_BASIT')

            if 'company_id' not in vals:
                vals['company_id'] = vals.get('company_id', self.env.company.id)
            processed_vals_list.append(vals)

        return super(StockLotCustom, self.with_context(mail_create_nosubscribe=True)).create(processed_vals_list)