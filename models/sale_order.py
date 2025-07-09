from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_create_project_tasks(self):
        """
        Satış siparişi onaylandığında veya manuel olarak tetiklendiğinde
        ilgili projelere ürünler için tek bir görev oluşturur.
        Her satış siparişi satırı için daha önce görev oluşturulup oluşturulmadığını kontrol eder.
        Görev adı sadece ürün adı ve satır açıklamasına göre belirlenir.
        """
        for order in self:
            if not order.project_id:
                raise UserError(
                    _("Bu satış siparişine bağlı bir proje bulunamadı. Lütfen bir proje seçin veya projeye bağlantıyı sağlayın."))

            newly_created_tasks = self.env['project.task']

            for line in order.order_line:
                # Sadece ürün tipi 'product' veya 'consu' olan satırlar için görev oluşturalım
                # ve bu satırın miktarı sıfırdan büyük olsun.
                if line.product_id and line.product_id.type in ['product', 'consu'] and line.product_uom_qty > 0:

                    # Bu satış siparişi satırı için daha önce bir görev oluşturulmuş mu kontrol et
                    existing_task_for_line = self.env['project.task'].search([
                        ('ilgili_satis_satiri_id', '=', line.id)
                    ], limit=1)

                    if existing_task_for_line:
                        continue  # Bu satır için zaten görev varsa, bu satırı atla

                    # Görev adı oluşturma: Ürün adı ve varsa satış satırı açıklaması
                    task_name = f"{line.product_id.name}"
                    if line.name and line.name != line.product_id.name:  # Satış satırı açıklaması ürün adından farklıysa ekle
                        task_name += f" ({line.name})"

                    # Mrp Production'dan gelen ek bilgiler varsa bunları da kullanabiliriz (isteğe bağlı)
                    # related_mo = line.mrp_production_ids[:1] if hasattr(line, 'mrp_production_ids') else False
                    # if related_mo and hasattr(related_mo, 'urun_aciklama') and related_mo.urun_aciklama:
                    #     task_name += f" - {related_mo.urun_aciklama}" # Görev adına Mrp açıklamasını ekle

                    # Görev açıklaması oluşturma
                    task_description = _(
                        f"Satış Siparişi #{order.name} için ürün ({line.product_id.name}) üretilecek/hazırlanacak.\n"
                        f"Talep Edilen Miktar: {line.product_uom_qty} {line.product_uom.name}.\n"
                        f"Satış Satırı Açıklaması: {line.name}\n"
                        f"Müşteri: {order.partner_id.name}"
                    )
                    # if related_mo and hasattr(related_mo, 'urun_aciklama') and related_mo.urun_aciklama:
                    #     task_description += f"\nÜretim Açıklaması: {related_mo.urun_aciklama}"

                    # Yeni görev oluştur
                    new_task = self.env['project.task'].create({
                        'name': task_name,  # Güncellenmiş görev adı
                        'project_id': order.project_id.id,
                        'description': task_description,  # Detaylı açıklama
                        'allocated_hours': line.product_uom_qty,
                        # Miktarı doğrudan saate çevirme konusunda hala dikkatli olunmalı. Eğer 1 adet ürün = 1 saat üretim değilse, buraya farklı bir mantık uygulamalısınız.
                        'ilgili_satis_siparisi_id': order.id,
                        'ilgili_satis_satiri_id': line.id,
                        'urun_adi': line.product_template_id.id,
                        # 'stage_id': False, # stage_id'yi manuel olarak False bırakmak, projenin ilk stage'ine otomatik atamasını sağlar.
                        # Genellikle Odoo, bu belirtilmezse zaten ilk stage'e atar.
                    })
                    newly_created_tasks += new_task

            if not newly_created_tasks:
                raise UserError(
                    _("Bu satış siparişinde henüz görev oluşturulmamış veya yeni eklenecek bir satış siparişi satırı bulunamadı."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Görevler Oluşturuldu!"),
                'message': _("%s adet görev başarıyla oluşturuldu.") % len(newly_created_tasks),
                'type': 'success',
                'sticky': False,
            }
        }