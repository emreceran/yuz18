from odoo import models, fields, api
from datetime import datetime, timedelta, time
import pytz # Saat dilimi için gerekli

class ReportMrpProductionPlanning(models.AbstractModel):
    _name = 'report.yuz18.report_planning_template' # BURAYI KENDİ MODÜL ADINLA DÜZELT
    _description = 'Günlük ve Ertesi Gün Üretim Raporu'

    @api.model
    def _get_report_values(self, docids, data=None):
        report_type = data.get('report_type', 'daily')
        
        # 1. Kullanıcının Saat Dilimini Al (Yoksa UTC kabul et)
        user_tz = pytz.timezone(self.env.context.get('tz') or 'UTC')
        today = fields.Date.context_today(self)

        # 2. Raporun Hangi Gün İçin Olduğunu Belirle
        if report_type == 'next_day':
            target_date = today + timedelta(days=1)
            report_title = f"🗓️ Ertesi Gün Planlama Raporu ({target_date})"
        else:
            target_date = today
            report_title = f"📅 Günlük Üretim Raporu ({target_date})"

        # 3. Yerel Saati UTC'ye Çevir (KRİTİK NOKTA)
        # Senin gününün başlangıcı (00:00:00) -> UTC karşılığı
        local_start = user_tz.localize(datetime.combine(target_date, time.min))
        utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)

        # Senin gününün bitişi (23:59:59) -> UTC karşılığı
        local_end = user_tz.localize(datetime.combine(target_date, time.max))
        utc_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)

        # 4. İş Emirlerini Çek (Tarih aralığı artık UTC'ye çevrildi)
        domain = [
            ('date_start', '>=', utc_start),
            ('date_start', '<=', utc_end),
            ('state', '!=', 'cancel')
        ]
        
        workorders = self.env['mrp.workorder'].search(domain, order='workcenter_id, date_start')

        # --- HATA AYIKLAMA ---
        # Eğer hiç kayıt gelmiyorsa loglara basar (Geliştirici modu açıkken sunucu logunda görünür)
        if not workorders:
            print(f"UYARI: {target_date} için kayıt bulunamadı.")
            print(f"Arama Aralığı (UTC): {utc_start} - {utc_end}")

        # 5. Veriyi İşle ve Grupla (Eski kodun aynısı devam ediyor)
        grouped_data = {} 
        
        for wo in workorders:
            wc = wo.workcenter_id
            
            if wc.id not in grouped_data:
                morning_alert = False
                alert_class = ''
                
                if report_type == 'next_day':
                    # Geçmiş işleri ararken de UTC kullanmalı
                    last_wo = self.env['mrp.workorder'].search([
                        ('workcenter_id', '=', wc.id),
                        ('date_start', '<', utc_start), # Rapor başlangıcından öncekiler
                        ('state', 'not in', ['cancel'])
                    ], order='date_start desc', limit=1)

                    if last_wo:
                        if last_wo.product_id != wo.product_id:
                            morning_alert = f"⚠️ DİKKAT: Güne Kalıp Değişimi ile Başlanacak! (Dünkü: {last_wo.product_id.display_name})"
                            alert_class = 'text-danger font-weight-bold'
                        else:
                            morning_alert = "✅ Üretim Kaldığı Yerden Devam Ediyor (Ayar Gerekmez)"
                            alert_class = 'text-success'
                    else:
                        morning_alert = "ℹ️ Yeni Başlangıç / Önceki Kayıt Yok"
                        alert_class = 'text-muted'

                grouped_data[wc.id] = {
                    'wc_name': wc.name,
                    'morning_alert': morning_alert,
                    'alert_class': alert_class,
                    'lines': [],
                    'last_product_id': None
                }

            # Gün içi değişim
            group = grouped_data[wc.id]
            change_alert = False
            row_class = ''
            
            if group['last_product_id'] and group['last_product_id'] != wo.product_id.id:
                change_alert = "Ürün/Kalıp Değişimi"
                row_class = 'table-warning'
            
            # Satırı ekle
            # workorder state seçimi bazen türkçe gelmeyebilir, manuel map edelim garanti olsun
            state_labels = dict(wo._fields['state'].selection)
            state_display = state_labels.get(wo.state, wo.state)

            group['lines'].append({
                'mo_name': wo.production_id.name,
                'product': wo.product_id.display_name,
                'date': wo.date_start, # Template bunu zaten kullanıcının saatine çevirir
                'state': state_display,
                'qty': wo.qty_production,
                'change_alert': change_alert,
                'row_class': row_class
            })
            
            group['last_product_id'] = wo.product_id.id

        return {
            'doc_ids': docids,
            'doc_model': 'mrp.production',
            'docs': self.env['mrp.production'].browse(docids),
            'data': data,
            'report_title': report_title,
            'grouped_data': grouped_data.values(),
        }
class MrpProductionButton(models.Model):
    """ Butonların olduğu asıl model """
    _inherit = 'mrp.production'

    def action_generate_daily_report(self):
        data = {'report_type': 'daily'}
        return self.env.ref('yuz18.action_report_mrp_planning').report_action(self, data=data)

    def action_generate_next_day_report(self):
        data = {'report_type': 'next_day'}
        return self.env.ref('yuz18.action_report_mrp_planning').report_action(self, data=data)