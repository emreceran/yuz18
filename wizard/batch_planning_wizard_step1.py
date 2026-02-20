from odoo import models, fields, api, _
from odoo.exceptions import UserError

class MrpBatchPlanningWizardStep1(models.TransientModel):
    """Step 1 Wizard - Ürün Seçimi ve Gruplama"""
    _name = 'mrp.batch.planning.wizard.step1'
    _description = 'Toplu Üretim Planlama - Ürün Seçimi'

    group_line_ids = fields.One2many('product.planning.group', 'wizard_id', string="Ürün Grupları")

    @api.model
    def default_get(self, fields_list):
        """Manufacturing orders'ları ürün+boyut bazında grupla"""
        res = super(MrpBatchPlanningWizardStep1, self).default_get(fields_list)
        
        # Context'ten active_ids al
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            return res

        # MO'ları al
        all_productions = self.env['mrp.production'].browse(active_ids)
        
        # Filtreleme: 
        # - done/cancel dışındakiler
        # - product_id olanlar
        # - Planlanmamış (is_planned == False) olanlar
        productions = all_productions.filtered(
            lambda mo: mo.state not in ['done', 'cancel'] 
            and mo.product_id
            and not mo.is_planned
        )

        if not productions:
            return res

        # ÖNEMLİ: Seçilen MO'ların sibling'lerini de ekle
        # Kullanıcı MRP ekranında 3 MO seçse bile, hepsinin siblings'i gelsin
        all_mo_ids = set(productions.ids)
        
        for mo in productions:
            # Kardeşlerini bul (sadece planlanmamış olanlar)
            sibling_domain = [
                ('id', '!=', mo.id),
                ('state', 'not in', ['done', 'cancel']),
                ('product_id', '!=', False),  # NULL olmayanlar
                ('product_id', '=', mo.product_id.id),
                ('is_planned', '=', False)  # Planlanmamış olanlar
            ]
            
            # Kriter 1: Procurement Group (En güçlü bağ - aynı sipariş)
            if mo.procurement_group_id:
                sibling_domain.append(('procurement_group_id', '=', mo.procurement_group_id.id))
            # Kriter 2: Origin (Sipariş No)
            elif mo.origin:
                sibling_domain.append(('origin', '=', mo.origin))
            else:
                # Bağ yoksa sadece kendisi
                continue
            
            # Sibling'leri bul ve ekle
            siblings = self.env['mrp.production'].search(sibling_domain)
            all_mo_ids.update(siblings.ids)
        
        # Tüm MO'ları (seçilenler + siblings) yeniden al
        all_productions_with_siblings = self.env['mrp.production'].browse(list(all_mo_ids))

        # Gruplama: product_id + en + boy + uzunluk kombinasyonu
        groups = {}
        
        for mo in all_productions_with_siblings.sorted(key=lambda p: p.date_deadline or p.date_start or fields.Datetime.now()):
            product = mo.product_id
            
            # Ürün yoksa atla (güvenlik kontrolü)
            if not product:
                continue
                
            en = getattr(mo, 'en', 0.0)
            boy = getattr(mo, 'boy', 0.0)
            # uzunluk artık önemsiz, gruplamaya dahil değil
            
            # Gruplama anahtarı: product + en + boy (uzunluk YOK)
            group_key = (product.id, en, boy)
            
            if group_key not in groups:
                groups[group_key] = {
                    'product_id': product.id,
                    'diameter_width': en,
                    'height': boy,
                    'length': 0.0,  # Önemsiz ama field var
                    'mo_ids': []
                }
            
            groups[group_key]['mo_ids'].append(mo.id)

        # Group line'ları oluştur
        group_lines = []
        for group_data in groups.values():
            # Güvenlik kontrolü: product_id mutlaka olmalı
            if not group_data.get('product_id'):
                continue
                
            group_lines.append((0, 0, {
                'product_id': group_data['product_id'],
                'diameter_width': group_data['diameter_width'],
                'height': group_data['height'],
                'length': group_data['length'],
                'mo_ids': [(6, 0, group_data['mo_ids'])],
                'selected_count': len(group_data['mo_ids'])  # Varsayılan: Hepsini seç
            }))


        res['group_line_ids'] = group_lines
        return res


    def action_next_step(self):
        """Step 2'ye geç - Seçilen MO'ları detaylı planlamaya gönder"""
        self.ensure_one()

        # Seçilen MO'ları topla (kalıp seçimi Step 2'de yapılacak)
        selected_mo_ids = []
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"=== DEBUG: action_next_step called ===")
        _logger.info(f"Total groups: {len(self.group_line_ids)}")
        
        for group in self.group_line_ids:
            _logger.info(f"Group: {group.product_id.name if group.product_id else 'NO PRODUCT'}")
            _logger.info(f"  - Selected count: {group.selected_count}")
            
            if group.selected_count <= 0:
                _logger.info(f"  - SKIPPED (selected_count <= 0)")
                continue

            # İlk N adet MO'yu seç (date_deadline sırasına göre)
            sorted_mos = group.mo_ids.sorted(key=lambda m: m.date_deadline or m.date_start or fields.Datetime.now())
            selected_mos = sorted_mos[:group.selected_count]
            
            selected_mo_ids.extend(selected_mos.ids)
            _logger.info(f"  - Added {len(selected_mos.ids)} MOs")

        _logger.info(f"Total selected MOs: {len(selected_mo_ids)}")
        
        if not selected_mo_ids:
            raise UserError(_("En az bir ürün seçmelisiniz!"))

        # Step 2 wizard'ı aç - BOŞ başlayacak, kullanıcı kalıp ekleyecek
        return {
            'name': _('Toplu Planlama - Kalıp Seçimi'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.batch.planning.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_scheduled_date': fields.Datetime.now(),
                'from_step1': True,
                'selected_mo_ids': selected_mo_ids,
            }
        }

