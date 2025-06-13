from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_create_project_tasks(self):
        """
        Satış siparişi onaylandığında veya manuel olarak tetiklendiğinde
        ilgili projelere üretilecek ürünler için görevler oluşturur.
        """
        for order in self:
            # Satış siparişine bağlı bir proje olup olmadığını kontrol et
            if not order.project_id:
                raise UserError(
                    _("Bu satış siparişine bağlı bir proje bulunamadı. Lütfen bir proje seçin veya projeye bağlantıyı sağlayın."))

            # Daha önce bu satış siparişinden görev oluşturulup oluşturulmadığını kontrol et
            # Görevlerinizi satış siparişine bağlamak için project.task modeline
            # 'sale_order_id' adında Many2one bir alan eklediğinizi varsayıyorum.
            # Eğer eklemediyseniz, bu kontrolü farklı bir yöntemle yapmalıyız (örn. görev açıklamasındaki metni kontrol ederek, ancak bu daha az güvenilirdir).
            existing_tasks = self.env['project.task'].search([
                ('project_id', '=', order.project_id.id),
                ('sale_order_id', '=', order.id)  # Görevi satış siparişine bağlayan alan
            ], limit=1)  # Sadece bir tane bile bulsak yeterli

            if existing_tasks:
                raise UserError(
                    _("Bu satış siparişi için ilgili projede zaten görevler oluşturulmuş. Tekrar görev oluşturulamaz."))

            # Görevlerin atanacağı aşamaları bulalım
            stage_indirilecekler = self.env['project.task.type'].search([
                ('name', '=', 'İndirilecekler'),
                ('project_ids', 'in', order.project_id.id)
            ], limit=1)

            stage_montaj = self.env['project.task.type'].search([
                ('name', '=', 'Montaj Yapılacaklar'),
                ('project_ids', 'in', order.project_id.id)
            ], limit=1)

            if not stage_indirilecekler:
                raise UserError(_("Projede 'İndirilecekler' aşaması bulunamadı. Lütfen kontrol edin."))
            if not stage_montaj:
                raise UserError(_("Projede 'Montaj Yapılacaklar' aşaması bulunamadı. Lütfen kontrol edin."))

            for line in order.order_line:
                if line.product_id and line.product_id.type in ['product', 'consu']:
                    related_mo = line.mrp_production_ids[:1]  # Sadece ilk MO'yu al

                    combined_mo_name = line.product_id.name  # Varsayılan olarak ürün adını kullan
                    task_description_suffix = ""

                    if related_mo:
                        if related_mo.urun_adi and related_mo.urun_aciklama:
                            combined_mo_name = f"{related_mo.urun_adi} {related_mo.urun_aciklama}"
                        elif related_mo.urun_adi:
                            combined_mo_name = related_mo.urun_adi
                        elif related_mo.urun_aciklama:
                            combined_mo_name = related_mo.urun_aciklama

                        if related_mo.urun_aciklama:
                            task_description_suffix = f" - {related_mo.urun_aciklama}"

                    # 1. Görev: İndirilecekler Aşaması
                    self.env['project.task'].create({
                        'name': f"{combined_mo_name} - İndirilecekler",
                        'project_id': order.project_id.id,
                        'description': _(
                            f"Satış Siparişi #{order.name} için ürün ({line.product_id.name}) indirilecekler listesinde.{task_description_suffix}"),
                        'allocated_hours': line.product_uom_qty,
                        'stage_id': stage_indirilecekler.id,
                        'ilgili_satis_siparisi_id': self.id,  # Yeni alan adı
                        'ilgili_satis_satiri_id': line.id,  # Yeni alan adı
                    })

                    # 2. Görev: Montaj Yapılacaklar Aşaması
                    self.env['project.task'].create({
                        'name': f"{combined_mo_name} - Montaj Yapılacaklar",
                        'project_id': order.project_id.id,
                        'description': _(
                            f"Satış Siparişi #{order.name} için ürün ({line.product_id.name}) montajı yapılacak.{task_description_suffix}"),
                        'allocated_hours': line.product_uom_qty,
                        'stage_id': stage_montaj.id,
                        'ilgili_satis_siparisi_id': self.id,  # Yeni alan adı
                        'ilgili_satis_satiri_id': line.id,  # Yeni alan adı
                    })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Görevler Oluşturuldu!"),
                'message': _("İlgili projelerde üretilecek ürünler için görevler başarıyla oluşturuldu."),
                'type': 'success',
                'sticky': False,
            }
        }