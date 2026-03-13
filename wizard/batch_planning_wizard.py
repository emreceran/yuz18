from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta, datetime
from odoo.tools import float_compare
# Mesai saati kontrol fonksiyonu
# Kurallar: Pzt-Cmt 08:00-17:00 TR (UTC 05:00-14:00), Pazar tatil
# Hiçbir slot 1 günü geçmez

# UTC karşılıkları (TR UTC+3)
UTC_START_HOUR = 5   # TR 08:00
UTC_END_HOUR = 14    # TR 17:00

def _next_working_day(dt):
    """Verilen tarihten sonraki çalışma gününün sabah 08:00'ini (UTC 05:00) döndürür.
    Pazar (weekday=6) atlanır."""
    next_day = dt.date() + timedelta(days=1)
    # Pazar ise Pazartesi'ye atla
    if next_day.weekday() == 6:
        next_day += timedelta(days=1)
    return datetime.combine(next_day, datetime.min.time().replace(hour=UTC_START_HOUR))

def _normalize_to_working_hours(dt):
    """Verilen datetime'ı çalışma saatlerine normalize eder.
    Mesai dışıysa en yakın çalışma saatine çeker."""
    if not dt:
        return dt
    dt = dt.replace(second=0, microsecond=0)
    
    # Pazar ise Pazartesi sabahına atla
    if dt.weekday() == 6:
        return _next_working_day(dt - timedelta(days=1))
    
    # Mesai bittiyse (>=14:00 UTC) → sonraki çalışma günü sabahı
    if dt.hour >= UTC_END_HOUR:
        return _next_working_day(dt)
    
    # Mesai başlamadıysa (<05:00 UTC) → o günün sabahı
    if dt.hour < UTC_START_HOUR:
        result = datetime.combine(dt.date(), datetime.min.time().replace(hour=UTC_START_HOUR))
        # O gün Pazar mı kontrol et
        if result.weekday() == 6:
            return _next_working_day(result - timedelta(days=1))
        return result
    
    return dt

def calculate_next_slot(start_dt, duration_hours):
    """
    Mesai saatlerine göre slot hesaplar.
    Pazar atlanır. Eğer kalan süre o güne sığmazsa,
    bugünün kalanını kullanır + ertesi çalışma gününe taşar.
    Returns: (slot_start, slot_end)
    """
    if not start_dt:
        return False, False
    
    start_dt = _normalize_to_working_hours(start_dt)
    if not start_dt:
        return False, False
    
    remaining = duration_hours
    current = start_dt
    
    while remaining > 0:
        day_limit = datetime.combine(current.date(), datetime.min.time().replace(hour=UTC_END_HOUR))
        available = (day_limit - current).total_seconds() / 3600.0
        
        if available <= 0:
            current = _next_working_day(current)
            continue
        
        if remaining <= available:
            end_dt = current + timedelta(hours=remaining)
            return start_dt, end_dt
        else:
            remaining -= available
            current = _next_working_day(current)
    
    return start_dt, current

class MrpBatchPlanningWizard(models.TransientModel):
    _name = 'mrp.batch.planning.wizard'
    _description = 'Toplu Üretim Planlama Sihirbazı'
    
    def _default_scheduled_date(self):
        """Yarın sabah 08:00 (Türkiye saati) - UTC 05:00"""
        tomorrow = fields.Date.today() + timedelta(days=1)
        # Türkiye UTC+3, 08:00 lokal = 05:00 UTC
        return datetime.combine(tomorrow, datetime.min.time().replace(hour=5, minute=0))


    scheduled_date = fields.Datetime(string="Planlanacak Başlangıç Tarihi", required=True, default=_default_scheduled_date)

    batch_line_ids = fields.One2many('mrp.batch.planning.wizard.line', 'wizard_id', string="Önerilen Planlar")
    
    # YENİ: Manuel kalıp seçimi için
    available_mo_ids = fields.Many2many(
        'mrp.production',
        'wizard_available_mo_rel',
        'wizard_id',
        'production_id',
        string='Kullanılabilir Üretim Emirleri',
        help='Step 1\' den gelen, henüz yerleştirilmemiş MO\'lar'
    )
    
    # Kullanılmış (atanmış) MO'lar - çift sayımı önlemek için
    used_mo_ids = fields.Many2many(
        'mrp.production',
        'wizard_used_mo_rel',
        'wizard_id',
        'production_id',
        string='Kullanılmış Üretim Emirleri'
    )

    
    # YENİ: Kalıp bazlı gruplar (Notebook tabs)  
    workcenter_group_ids = fields.One2many(
        'mrp.batch.planning.workcenter.group',
        'wizard_id',
        string='Kalıp Grupları'
    )
    
    # YENİ: Inline kalıp seçimi için (picker wizard yerine)
    selected_workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Kalıp Seç',
        domain="[('id', 'in', available_workcenter_ids)]"
    )
    
    # Önceki kalıbı takip etmek için (otomatik kaydetme)
    previous_workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Önceki Kalıp'
    )

    
    available_workcenter_ids = fields.Many2many(
        'mrp.workcenter',
        compute='_compute_available_workcenters',
        string='Uygun Kalıplar'
    )
    
    # Seçilen kalıba uygun MO'lar (filtrelenmiş)
    filtered_mo_ids = fields.Many2many(
        'mrp.production',
        'wizard_filtered_mo_rel',
        'wizard_id',
        'production_id',
        compute='_compute_filtered_mos',
        string='Uygun Üretim Emirleri'
    )
    
    # Kullanıcının seçtiği MO'lar
    selected_production_ids = fields.Many2many(
        'mrp.production',
        'wizard_selected_production_rel',
        'wizard_id',
        'production_id',
        string='Seçilen Üretim Emirleri',
        domain="[('id', 'in', filtered_mo_ids)]"
    )
    
    available_for_placement_ids = fields.Many2many(
        'mrp.production',
        'wizard_available_placement_rel',
        'wizard_id',
        'production_id',
        compute='_compute_available_for_placement',
        string='Yerleştirilebilir Üretim Emirleri'
    )
    
    # Ürün bazlı gruplar (kalıp seçilince oluşturulur)
    step2_product_group_ids = fields.One2many(
        'step2.product.group',
        'wizard_id',
        string='Ürün Grupları'
    )
    
    workcenter_date_start = fields.Datetime(
        string='Kalıp Başlangıç Tarihi',
        default=_default_scheduled_date
    )


    
    preview_mo_count = fields.Integer(
        string='Seçilen Üretim Emri',
        compute='_compute_preview'
    )
    
    preview_length = fields.Float(
        string='Toplam Uzunluk',
        compute='_compute_preview'
    )
    
    remaining_mo_count = fields.Integer(
        string='Kalan Üretim Emri Sayısı',
        compute='_compute_remaining_mo_count'
    )

    existing_plan_info = fields.Html(
        string='Mevcut Planlamalar',
        compute='_compute_existing_plan_info',
    )

    @api.depends('selected_workcenter_id', 'workcenter_date_start')
    def _compute_existing_plan_info(self):
        import pytz
        tz = pytz.timezone('Europe/Istanbul')
        for rec in self:
            if not rec.selected_workcenter_id:
                rec.existing_plan_info = False
                continue

            date_filter = rec.workcenter_date_start or fields.Datetime.now()
            work_orders = self.env['mrp.workorder'].search([
                ('workcenter_id', '=', rec.selected_workcenter_id.id),
                ('state', 'not in', ['done', 'cancel']),
                ('date_start', '>=', date_filter),
            ], order='date_start asc', limit=20)

            if not work_orders:
                rec.existing_plan_info = '<p style="color:#888;">Bu tarihten sonra planlama yok.</p>'
                continue

            rows = ''
            for i, wo in enumerate(work_orders):
                mo_name = wo.production_id.name or '-'
                product = wo.production_id.product_id.display_name or '-'
                lot_no = wo.production_id.lot_producing_id.name if wo.production_id.lot_producing_id else '-'
                d_start = wo.date_start.replace(tzinfo=pytz.utc).astimezone(tz).strftime('%d.%m %H:%M') if wo.date_start else '-'
                d_end = wo.date_finished.replace(tzinfo=pytz.utc).astimezone(tz).strftime('%d.%m %H:%M') if wo.date_finished else '-'
                bg = '#f9f9f9' if i % 2 == 0 else '#fff'
                rows += f'<tr style="background:{bg};"><td style="padding:3px 6px;">{mo_name}</td><td style="padding:3px 6px;">{product}</td><td style="padding:3px 6px;">{lot_no}</td><td style="padding:3px 6px;">{d_start}</td><td style="padding:3px 6px;">{d_end}</td></tr>'

            rec.existing_plan_info = f'''
                <table style="width:100%;font-size:12px;border-collapse:collapse;border:1px solid #ddd;">
                    <thead><tr style="background:#875A7B;color:#fff;">
                        <th style="padding:5px 6px;text-align:left;">MO</th>
                        <th style="padding:5px 6px;text-align:left;">Ürün</th>
                        <th style="padding:5px 6px;text-align:left;">Lot No</th>
                        <th style="padding:5px 6px;text-align:left;">Başlangıç</th>
                        <th style="padding:5px 6px;text-align:left;">Bitiş</th>
                    </tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            '''

    @api.depends('available_mo_ids', 'used_mo_ids')
    def _compute_remaining_mo_count(self):
        for rec in self:
            rec.remaining_mo_count = len(rec.available_mo_ids)
    
    @api.depends('selected_workcenter_id', 'available_mo_ids')
    def _compute_filtered_mos(self):
        """Seçilen kalıba uygun MO'ları filtrele"""
        for rec in self:
            if not rec.selected_workcenter_id or not rec.available_mo_ids:
                rec.filtered_mo_ids = self.env['mrp.production']
                continue
            
            wc = rec.selected_workcenter_id
            filtered = self.env['mrp.production']
            
            for mo in rec.available_mo_ids:
                # Boyut kontrolü
                if wc.x_width_capacity and mo.en > wc.x_width_capacity:
                    continue
                if wc.x_height_capacity and mo.boy > wc.x_height_capacity:
                    continue
                filtered |= mo
            
            rec.filtered_mo_ids = filtered
    
    @api.depends('selected_workcenter_id', 'filtered_mo_ids', 'workcenter_group_ids.line_ids.production_ids')
    def _compute_available_for_placement(self):
        """Seçili kalıba uygun, henüz yerleştirilmemiş MO'ları hesapla"""
        for rec in self:
            if not rec.selected_workcenter_id:
                rec.available_for_placement_ids = self.env['mrp.production']
                continue
            
            current_wc_groups = rec.workcenter_group_ids.filtered(
                lambda g: g.workcenter_id == rec.selected_workcenter_id
            )
            placed_mos = current_wc_groups.mapped('line_ids.production_ids')
            rec.available_for_placement_ids = rec.filtered_mo_ids - placed_mos
    
    @api.onchange('selected_workcenter_id')
    def _onchange_selected_workcenter(self):
        """Kalıp değişince: önceki seçimleri kaydet, yeni grupları oluştur"""
        
        # Önceki kalıpta seçim varsa kaydet (MANUEL DÜZENLEME İÇİN TEK SATIR OLARAK)
        if self.previous_workcenter_id and self.step2_product_group_ids:
            has_selections = any(g.selected_count > 0 for g in self.step2_product_group_ids)
            if has_selections:
                self._auto_save_previous_workcenter()
        
        # Yeni kalıbı önceki olarak kaydet
        self.previous_workcenter_id = self.selected_workcenter_id
        self.selected_production_ids = False
        
        # Komut listesini başlat (Önce temizle: (5,0,0) komutu tüm satırları siler)
        # Bu sayede her kalıp değişiminde liste sıfırlanır ve yeniden dolar.
        commands = [(5, 0, 0)]
        
        if not self.selected_workcenter_id or not self.available_mo_ids:
            self.step2_product_group_ids = commands
            return

        wc = self.selected_workcenter_id
        
        # Kullanılabilir MO'lar (zaten available_mo_ids'den çıkarılmış olanlar)
        remaining_mos = self.available_mo_ids
        
        # Uygun MO'ları filtrele (computed field yerine doğrudan)
        filtered_mos = self.env['mrp.production']
        for mo in remaining_mos:
            # Kapasite kontrolü
            # YENİ: Strand Rules (Birebir Uyuşma) kontrolü
            if mo.product_id.product_tmpl_id.x_check_strand_rules:
                # Birebir eşitlik gerekli (Tolerans 0.01)
                if float_compare(mo.en, wc.x_width_capacity, precision_digits=2) != 0:
                    continue
                if float_compare(mo.boy, wc.x_height_capacity, precision_digits=2) != 0:
                    continue
            else:
                # Standart kontrol (Sığması yeterli)
                if wc.x_width_capacity and mo.en > wc.x_width_capacity:
                    continue
                if wc.x_height_capacity and mo.boy > wc.x_height_capacity:
                    continue
            
            # Ürünün bu kalıpta üretilmesine izin var mı? (Product Template ayarı)
            # Eğer ürün kartında "Uygulanabilir İş Merkezleri" tanımlıysa ve bu kalıp yoksa -> Gösterme
            if mo.product_id and mo.product_id.product_tmpl_id.allowed_workcenter_ids:
                if wc.id not in mo.product_id.product_tmpl_id.allowed_workcenter_ids.ids:
                    continue
                
                
            filtered_mos |= mo
        
        if not filtered_mos:
            self.step2_product_group_ids = commands
            return
        
        # Filtrelenmiş MO'ları ürün bazında grupla
        product_groups = {}
        for mo in filtered_mos:
            if not mo.product_id:
                continue
            key = (mo.product_id.id, mo.en or 0, mo.boy or 0)
            if key not in product_groups:
                product_groups[key] = {
                    'product_id': mo.product_id.id,
                    'diameter_width': mo.en or 0,
                    'height': mo.boy or 0,
                    'mo_ids': [],
                }
            product_groups[key]['mo_ids'].append(mo.id)
        
        # Grupları oluştur ve komutlara ekle
        for key, data in product_groups.items():
            if data['product_id']:
                group_cmd = (0, 0, {
                    'product_id': data['product_id'],
                    'diameter_width': data['diameter_width'],
                    'height': data['height'],
                    'mo_ids': [(6, 0, data['mo_ids'])]
                })
                commands.append(group_cmd)
        
        self.step2_product_group_ids = commands
    
    def _check_existing_groups_complete(self):
        """Mevcut grupların tamamlanıp tamamlanmadığını kontrol et"""
        for group in self.workcenter_group_ids:
            # Gruptaki toplam MO'lar
            total_mos = group.initial_mo_ids
            # Plana yerleştirilmiş MO'lar
            placed_mos = group.line_ids.production_ids
            
            # Fark var mı?
            remaining = total_mos - placed_mos
            if remaining:
                raise UserError(f"'{group.workcenter_id.name}' grubunda yerleştirilmemiş {len(remaining)} adet MO var.\n\nLütfen önce mevcut grubun planlamasını tamamlayın.")

    def _auto_save_previous_workcenter(self):
        """Önceki kalıptaki seçimleri kaydet - MO'ları initial_mo_ids'e kaydet, line'ları BOŞ bırak"""
        if not self.previous_workcenter_id:
            return
            
        # Mevcut grupların tamamlandığını kontrol et
        # Not: Seçim değişikliği sırasında hata fırlatmak UI'da bazen sorun olabilir
        # ama kullanıcı kesin kısıtlama istediği için ekliyoruz.
        self._check_existing_groups_complete()
        
        previous_wc = self.previous_workcenter_id
        
        # Gruplardan seçilen MO'ları topla
        all_selected_mos = self.env['mrp.production']
        for group in self.step2_product_group_ids:
            if group.selected_count <= 0:
                continue
            sorted_mos = group.mo_ids.sorted(key=lambda m: m.date_deadline or fields.Datetime.now())
            selected = sorted_mos[:group.selected_count]
            all_selected_mos |= selected
        
        if not all_selected_mos:
            return
        
        # Grup oluştur veya güncelle
        existing_group = self.workcenter_group_ids.filtered(
            lambda g: g.workcenter_id == previous_wc
        )
        
        if existing_group:
            # Mevcut gruba yeni MO'ları initial listesine ekle
            existing_group.write({'initial_mo_ids': [(4, mo.id) for mo in all_selected_mos]})
        else:
            # Yeni grup oluştur - ÖNCe grubu oluştur, SONRA initial_mo_ids yaz
            group_vals = {
                'workcenter_id': previous_wc.id,
                'date_start': self.workcenter_date_start or self._default_scheduled_date(),
                'line_ids': []
            }
            self.workcenter_group_ids = [(0, 0, group_vals)]
            
            # Yeni oluşturulan grubu bul ve initial_mo_ids'i AYRI YAZ
            new_group = self.workcenter_group_ids.filtered(
                lambda g: g.workcenter_id == previous_wc
            )
            if new_group:
                new_group.write({'initial_mo_ids': [(6, 0, all_selected_mos.ids)]})
        
        # MO'ları kullanılmış olarak işaretle
        self.used_mo_ids = [(4, mo.id) for mo in all_selected_mos]


    def action_create_empty_group(self):
        """Manuel yerleştirme için BOŞ bir kalıp grubu oluştur"""
        if not self.selected_workcenter_id:
            raise UserError("Lütfen önce bir kalıp seçin")
            
        # Mevcut grupların tamamlandığını kontrol et
        self._check_existing_groups_complete()
        
        # Aynı kalıp için grup var mı kontrol et
        existing = self.workcenter_group_ids.filtered(
            lambda g: g.workcenter_id == self.selected_workcenter_id
        )
        if existing:
            raise UserError(f"{self.selected_workcenter_id.name} için zaten bir grup var. Detayına girerek MO ekleyebilirsiniz.")
        
        # BOŞ grup oluştur
        group_vals = {
            'workcenter_id': self.selected_workcenter_id.id,
            'date_start': self.workcenter_date_start or self._default_scheduled_date(),
            'line_ids': []  # BOŞ satır listesi
        }
        
        self.workcenter_group_ids = [(0, 0, group_vals)]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{self.selected_workcenter_id.name} için boş grup oluşturuldu. Detayına girerek MO ekleyebilirsiniz.',
                'type': 'success',
                'sticky': False,
            }
        }


    @api.onchange('scheduled_date')
    def _onchange_scheduled_date(self):
        self._recalculate_dates()

    @api.onchange('batch_line_ids')
    def _onchange_batch_line_ids(self):
        self._recalculate_dates()

    def _recalculate_dates(self):
        base_start = self.scheduled_date or fields.Datetime.now()
        wc_pointer = {} 

        for line in self.batch_line_ids:
            if not line.workcenter_id: continue

            wc_id = line.workcenter_id.id
            naive_start = wc_pointer.get(wc_id, base_start)
            
            work_minutes = self._calculate_minutes(line.workcenter_id, line.time_mode)
            work_hours = work_minutes / 60.0
            
            calendar = line.workcenter_id.resource_calendar_id
            real_start = naive_start
            real_end = False

            if calendar:
                try:
                    # Snap Mantığı: En yakın uygun başlangıcı bul
                    real_start = calendar.plan_hours(0, naive_start, compute_leaves=True)
                    real_end = calendar.plan_hours(work_hours, real_start, compute_leaves=True)
                except: pass
            
            if not real_end:
                real_start = naive_start
                real_end = real_start + timedelta(minutes=work_minutes)
            
            line.date_start = real_start
            line.date_finished = real_end
            wc_pointer[wc_id] = real_end

    def _calculate_minutes(self, wc, mode):
        # Varsayılan: Tam gün = 9 saat (08:00 - 17:00)
        hours_per_day = 9.0
        if wc.resource_calendar_id:
            # Takvim varsa oradan al, ama wizard mantığı 9 saat üzerine kurulu
            hours_per_day = wc.resource_calendar_id.hours_per_day or 9.0
        
        total_minutes = hours_per_day * 60
        
        if mode == '1_1': return total_minutes
        if mode == '1_2': return total_minutes / 2
        if mode == '1_3': return total_minutes / 3
        if mode == '1_4': return total_minutes / 4
        return total_minutes


    @api.model
    def default_get(self, fields_list):
        res = super(MrpBatchPlanningWizard, self).default_get(fields_list)
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"=== DEBUG Step 2: default_get called ===")
        
        # Check if we're coming from Step 1
        from_step1 = self.env.context.get('from_step1', False)
        selected_mo_ids = self.env.context.get('selected_mo_ids', [])
        
        _logger.info(f"from_step1: {from_step1}")
        _logger.info(f"selected_mo_ids count: {len(selected_mo_ids)}")
        
        if from_step1 and selected_mo_ids:
            # YENİ AKIŞ: Step 1'den sadece MO ID'leri geldi
            # Step 2 boş başlayacak, kullanıcı kalıp ekleyecek
            _logger.info(f"=== Step 2: Starting empty with {len(selected_mo_ids)} available MOs ===")
            
            # MO'ları available_mo_ids'e yükle
            res['available_mo_ids'] = [(6, 0, selected_mo_ids)]
            res['workcenter_group_ids'] = []  # Boş başla
            res['batch_line_ids'] = []

            return res
        
        else:
            # ESKİ DAVR ANIŞ: Otomatik gruplama (backward compatibility)

            # Context'teki tüm active_ids'leri kullan
            active_ids = self.env.context.get('active_ids', [])
            _logger.info(f"Using old behavior, active_ids: {len(active_ids)}")
            productions = self.env['mrp.production'].browse(active_ids)
        
        _logger.info(f"Before filtering: {len(productions)} productions")
        
        # Ortak filtreleme - Step 1'den gelince daha esnek
        if from_step1:
            # Step 1'den gelen MO'lar zaten seçilmiş, sadece done/cancel'ı çıkar
            productions = productions.filtered(
                lambda mo: mo.state not in ['done', 'cancel']
            )
        else:
            # Eski davranış: Daha sıkı filtre + kalip_id kontrolü
            productions = productions.filtered(
                lambda mo: mo.state not in ['done', 'cancel', 'progress'] and not mo.date_start and not mo.kalip_id
            )
        
        _logger.info(f"After filtering: {len(productions)} productions")
        
        all_batches = [] 

        for mo in productions.sorted(key=lambda p: p.date_deadline or p.date_start):
            tech = self._get_tech_data(mo)
            p_len = tech['uzunluk']
            if p_len <= 0: p_len = 1.0

            tmpl = mo.product_id.product_tmpl_id
            group_key = [tmpl.id]
            
            group_key.extend([tech['en'], tech['boy']])
            
            if tmpl.x_check_strand_rules: group_key.append(1) 
            else: group_key.append(0)
            
            final_key = tuple(group_key)
            
            assigned = False
            for batch in all_batches:
                if batch['key'] == final_key:
                    if batch['max_len'] <= 0 or (batch['len'] + p_len) <= batch['max_len']:
                        batch['mos'].append(mo.id)
                        batch['len'] += p_len
                        assigned = True
                        break 
            
            if not assigned:
                pool = tmpl.allowed_workcenter_ids
                wc = False
                
                if tmpl.x_check_strand_rules:
                    if pool:
                        matches = pool.filtered(lambda w: w.x_width_capacity == tech['en'] and w.x_height_capacity == tech['boy'])
                        if matches: wc = matches[0]
                    if not wc: 
                        wc = self.env['mrp.workcenter'].search([
                            ('x_width_capacity', '=', tech['en']),
                            ('x_height_capacity', '=', tech['boy'])
                        ], limit=1)
                
                else:
                    if pool: wc = pool[0]
                    if not wc:
                         wc = self.env['mrp.workcenter'].search([], limit=1)

                if wc:
                    wc_cap = wc.x_max_length_capacity or 0.0
                else:
                    wc_cap = 0.0 

                all_batches.append({
                    'key': final_key, 'wc': wc, 'mos': [mo.id], 'len': p_len, 'max_len': wc_cap
                })

        lines = []
        for b in all_batches:
            batch_mos = self.env['mrp.production'].browse(b['mos'])
            names_list = []
            for m in batch_mos:
                 serial_no = m.lot_producing_id.name if m.lot_producing_id else "SN-Yok"
                 names_list.append(f"{m.name} / {m.product_id.display_name} / {getattr(m, 'uzunluk', 0.0):.0f} [{serial_no}]")
            names_str = "\n".join(names_list)
            
            lines.append((0, 0, {
                'workcenter_id': b['wc'].id if b['wc'] else False,
                'production_ids': [(6, 0, b['mos'])],
                'product_names': names_str, 
                'total_length_usage': b['len'],
                'time_mode': '1_1', 
            }))
        
        res['batch_line_ids'] = lines
        
        # Manuel Tarih Hesaplama (Memory'deki veriler için)
        wc_pointer = {}
        base_start = fields.Datetime.now()
        for cmd in lines:
            vals = cmd[2]
            wc_id = vals['workcenter_id']
            wc = self.env['mrp.workcenter'].browse(wc_id)
            naive_start = wc_pointer.get(wc_id, base_start)
            
            hours_per_day = 8.0
            if wc.resource_calendar_id:
                hours_per_day = wc.resource_calendar_id.hours_per_day or 8.0
            work_hours = hours_per_day 
            
            calendar = wc.resource_calendar_id
            real_start = naive_start
            real_end = False
            
            if calendar:
                try:
                    real_start = calendar.plan_hours(0, naive_start, compute_leaves=True)
                    real_end = calendar.plan_hours(work_hours, real_start, compute_leaves=True)
                except: pass
            
            if not real_end:
                real_start = naive_start
                real_end = real_start + timedelta(hours=work_hours)
            
            vals['date_start'] = real_start
            vals['date_finished'] = real_end
            wc_pointer[wc_id] = real_end

        return res


    def _get_tech_data(self, mo):
        return {
            'en': getattr(mo, 'en', 0.0),
            'boy': getattr(mo, 'boy', 0.0),
            'uzunluk': getattr(mo, 'uzunluk', 0.0)
        }

    def _check_constraints(self):
        errors = []
        for line in self.batch_line_ids:
            wc = line.workcenter_id
            if wc.x_max_length_capacity > 0:
                if line.total_length_usage > wc.x_max_length_capacity:
                    errors.append(f"Kapasite Hatası ({wc.name}): Yüklenen {line.total_length_usage} > Limit")

            if line.production_ids:
                first_mo = line.production_ids[0]
                ref_tmpl = first_mo.product_id.product_tmpl_id
                check_rules = ref_tmpl.x_check_strand_rules
                
                ref_en = getattr(first_mo, 'en', 0.0)
                ref_boy = getattr(first_mo, 'boy', 0.0)
                
                for mo in line.production_ids:
                    # Tip Kontrolü (Her zaman yapılmalı mı? Evet, aynı tip ürünler birleşmeli demişti)
                    if mo.product_id.product_tmpl_id != ref_tmpl:
                         errors.append(f"Ürün Tipi Uyuşmazlığı: {mo.name}")
                         continue
                         
                    # Ölçü Kontrolü (Sadece Kural Aktifse)
                    if check_rules:
                        mo_en = getattr(mo, 'en', 0.0)
                        mo_boy = getattr(mo, 'boy', 0.0)
                        if mo_en != ref_en or mo_boy != ref_boy:
                            errors.append(f"Ölçü Uyuşmazlığı (Çap Kontrolü Aktif): {mo.name}")
        if errors: raise UserError("\n---\n".join(errors))

    @api.depends('available_mo_ids')
    def _compute_available_workcenters(self):
        """Henüz yerleştirilmemiş MO'lara uygun kalıpları bul"""
        for rec in self:
            if not rec.available_mo_ids:
                rec.available_workcenter_ids = self.env['mrp.workcenter']
                continue
            
            suitable_wcs = self.env['mrp.workcenter']
            for mo in rec.available_mo_ids:
                tmpl = mo.product_id.product_tmpl_id
                
                if tmpl.allowed_workcenter_ids:
                    suitable_wcs |= tmpl.allowed_workcenter_ids
                elif tmpl.x_check_strand_rules:
                    wcs = self.env['mrp.workcenter'].search([
                        ('x_width_capacity', '>=', mo.en),
                        ('x_height_capacity', '>=', mo.boy)
                    ])
                    suitable_wcs |= wcs
                else:
                    suitable_wcs |= self.env['mrp.workcenter'].search([])
            
            rec.available_workcenter_ids = suitable_wcs
    
    @api.depends('selected_production_ids')
    def _compute_preview(self):
        """Seçilen MO'ların istatistiklerini göster"""
        for rec in self:
            rec.preview_mo_count = len(rec.selected_production_ids)
            rec.preview_length = sum(mo.uzunluk or 0 for mo in rec.selected_production_ids)

    
    def _get_placeable_mos(self, workcenter):
        """Verilen workcenter'a sığacak MO'ları döndür"""
        available = self.available_mo_ids
        capacity = workcenter.x_max_length_capacity or float('inf')
        placed = self.env['mrp.production']
        total_length = 0.0
        
        for mo in available.sorted(key=lambda m: m.date_deadline or fields.Datetime.now()):
            if workcenter.x_width_capacity and mo.en > workcenter.x_width_capacity:
                continue
            if workcenter.x_height_capacity and mo.boy > workcenter.x_height_capacity:
                continue
            
            mo_length = mo.uzunluk or 0
            if total_length + mo_length <= capacity:
                placed |= mo
                total_length += mo_length
            else:
                break
        
        return placed

    def action_add_workcenter(self):
        """Seçilen kalıba gruplardan seçilen MO'ları yerleştir - MO'ları initial_mo_ids'e kaydet"""
        self.ensure_one()
        
        # Mevcut grupların tamamlandığını kontrol et
        self._check_existing_groups_complete()
        
        if not self.selected_workcenter_id:
            raise UserError("Lütfen bir kalıp seçin!")
        
        # Gruplardan seçilen MO'ları topla
        all_selected_mos = self.env['mrp.production']
        
        # 1. Step 1'den gelen seçimler
        for group in self.step2_product_group_ids:
            if group.selected_count <= 0:
                continue
            # İlk N adet MO'yu seç
            sorted_mos = group.mo_ids.sorted(key=lambda m: m.date_deadline or fields.Datetime.now())
            selected = sorted_mos[:group.selected_count]
            all_selected_mos |= selected
            
        if not all_selected_mos:
            raise UserError("Lütfen yerleştirilecek MO adetlerini girin!")
        
        # Workcenter ID'yi sakla
        wc = self.selected_workcenter_id
        
        # Grubu doğrudan oluştur (aynı kalıp birden fazla kez eklenebilir)
        new_group = self.env['mrp.batch.planning.workcenter.group'].create({
            'wizard_id': self.id,
            'workcenter_id': wc.id,
            'date_start': self.workcenter_date_start or self.scheduled_date or self._default_scheduled_date(),
            'initial_mo_ids': [(6, 0, all_selected_mos.ids)],
        })
        
        # Wizard alanlarını güncelle
        self.write({
            'available_mo_ids': [(3, mo.id) for mo in all_selected_mos],
            'used_mo_ids': [(4, mo.id) for mo in all_selected_mos],
            'selected_workcenter_id': False,
            'previous_workcenter_id': False,
            'step2_product_group_ids': [(5, 0, 0)],
        })

        # Wizard'ı yeniden aç
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.batch.planning.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }





    def _get_workcenter_last_planned_date(self, workcenter_id):
        """Veritabanında bu kalıpta zaten planlanmış MO'ların en son bitiş tarihini bul."""
        # İş emirlerinde (workorder) bu kalıba atanmış ve planlanmış olanları ara
        last_wo = self.env['mrp.workorder'].search([
            ('workcenter_id', '=', workcenter_id),
            ('state', 'not in', ['done', 'cancel']),
            ('date_finished', '!=', False),
        ], order='date_finished desc', limit=1)
        
        if last_wo:
            return last_wo.date_finished
        return False
    
    def _resequence_workcenter_lines(self, workcenter_id):
        """
        Belirtilen kalıba ait TÜM satırları bulur,
        sıraya dizer ve mesai saatlerine göre tarihlerini günceller.
        - Veritabanındaki mevcut planlarla çakışma önlenir
        - Her grubun başlangıcı = MAX(kendi date_start, önceki grubun bitişi, DB son plan)
        - Çakışma yoksa kullanıcının tarihine dokunulmaz
        - Pazar atlanır
        """
        if not workcenter_id:
            return
        
        time_mode_hours = {
            '1_1': 9.0, '1_2': 4.5, '1_3': 3.0, '1_4': 2.25
        }
        
        # 1. Veritabanındaki mevcut planların en son bitiş tarihini bul
        db_last_date = self._get_workcenter_last_planned_date(workcenter_id)
        
        target_groups = self.workcenter_group_ids.filtered(
            lambda g: g.workcenter_id and g.workcenter_id.id == workcenter_id and g.line_ids
        )
        
        if not target_groups:
            return
        
        # Önceki grubun bitiş tarihini takip et
        previous_group_end = None
        
        for group in target_groups:
            # Grubun kendi başlangıç tarihi
            group_start = group.date_start or self.workcenter_date_start or self._default_scheduled_date()
            group_start = _normalize_to_working_hours(group_start)
            
            # DB'deki son plan varsa kontrol et
            if db_last_date:
                db_next = _normalize_to_working_hours(db_last_date)
                if db_next and group_start and db_next > group_start:
                    group_start = db_next
            
            # Önceki grubun bitişiyle çakışma kontrolü
            if previous_group_end:
                prev_end_norm = _normalize_to_working_hours(previous_group_end)
                current_start = _normalize_to_working_hours(group_start)
                if prev_end_norm and current_start and prev_end_norm > current_start:
                    # Çakışma var: Grubu ileri taşı ve SATIRLARI ZORLA GÜNCELLE
                    group.date_start = prev_end_norm
                    # force_start_date vererek ilk satırın eski tarihine takılmasını engelle
                    group.resequence_lines(force_start_date=prev_end_norm)
                else:
                    # Çakışma yok, grubun kendi başlangıç tarihini kullan
                    group.resequence_lines(force_start_date=group_start)
            else:
                # İlk grup, kendi başlangıç tarihini kullan
                group.resequence_lines(force_start_date=group_start)
            
            # Bu grubun yeni bitiş tarihini bul (son satırın bitişi)
            sorted_lines = group.line_ids.sorted('sequence')
            if sorted_lines:
                last_line = sorted_lines[-1]
                if last_line.date_finished:
                    previous_group_end = last_line.date_finished
            else:
                # Satır yoksa, başlangıç tarihi bitiş gibidir (uzunluk 0)
                previous_group_end = group.date_start
                 
                 
    @api.onchange('workcenter_group_ids')
    def _onchange_workcenter_group_ids(self):
        """
        Gruplardan biri değiştiğinde (örn: süre modu değişip uzadığında),
        sonraki grupların SADECE çakışma varsa tarihlerini ileri kaydır.
        Çakışma yoksa mevcut tarihlere DOKUNMA.
        Satırı olmayan (boş) gruplar atlanır.
        """
        if not self.workcenter_group_ids:
            return
            
        # Grupları workcenter bazında ayır
        wc_groups = {}
        for group in self.workcenter_group_ids:
            if not group.workcenter_id:
                continue
            if group.workcenter_id.id not in wc_groups:
                wc_groups[group.workcenter_id.id] = []
            wc_groups[group.workcenter_id.id].append(group)
            
        # Her workcenter için zincirleme kontrol
        for wc_id, groups in wc_groups.items():
            previous_end = None
            
            for group in groups:
                # Satırı olmayan grupları atla - boş gruplar mevcut grupları bozmamalı
                if not group.line_ids:
                    continue
                    
                current_start = group.date_start
                if not current_start:
                    continue
                
                # Sadece çakışma varsa müdahale et
                if previous_end:
                    prev_end_norm = _normalize_to_working_hours(previous_end)
                    current_start_norm = _normalize_to_working_hours(current_start)
                    if prev_end_norm and current_start_norm and prev_end_norm > current_start_norm:
                        # Çakışma var: Grubu ileri taşı ve satırları yeniden hesapla
                        group.date_start = prev_end_norm
                        group.resequence_lines(force_start_date=prev_end_norm)
                
                # Bu grubun bitiş tarihini bul (mevcut veriden, yeniden hesaplamadan)
                sorted_lines = group.line_ids.sorted('sequence')
                if sorted_lines:
                    last_line = sorted_lines[-1]
                    if last_line.date_finished:
                        previous_end = last_line.date_finished


    def action_confirm(self):
        # Son seçili kalıbı kaydet
        if self.selected_workcenter_id and self.step2_product_group_ids:
            has_selections = any(g.selected_count > 0 for g in self.step2_product_group_ids)
            if has_selections:
                self.previous_workcenter_id = self.selected_workcenter_id
                self._auto_save_previous_workcenter()
        
        # Tüm kalıplar için sıralamayı son kez garantiye al
        processed_wcs = set()
        for group in self.workcenter_group_ids:
            if group.workcenter_id.id not in processed_wcs:
                self._resequence_workcenter_lines(group.workcenter_id.id)
                processed_wcs.add(group.workcenter_id.id)
                
        self._check_constraints()
        self._recalculate_dates()
        
        # Workcenter groups varsa onları kullan
        processed_count = 0
        if self.workcenter_group_ids:
            for group in self.workcenter_group_ids:
                target_wc = group.workcenter_id
                if not target_wc:
                    # Hata vermek yerine bu bozuk kaydı atla (Transient model çöpü olabilir)
                    continue
                    
                # start_dt = group.date_start (Kaldırıldı - Satır bazlı olmalı)
                
                for line in group.line_ids:
                    start_dt = line.date_start # Satırın kendi başlangıç saati
                    end_dt = line.date_finished
                    if not start_dt:
                        raise UserError(f"Hata: {line.product_names} satırı için tarih hesaplanamadı! Lütfen tekrar deneyin.")
                        
                    work_minutes = self._calculate_minutes(target_wc, line.time_mode)

                    mos_to_process = line.production_ids
                    mos_to_confirm = mos_to_process.filtered(lambda m: m.state == 'draft')
                    if mos_to_confirm: mos_to_confirm.action_confirm()

                    for mo in mos_to_process:
                        if mo.date_start:
                            try: mo.button_unplan()
                            except: pass
                        mo.write({'date_start': start_dt, 'date_finished': end_dt})
                        wos = mo.workorder_ids.filtered(lambda w: w.state not in ('done','cancel'))
                        if wos:
                            wos.write({
                                'workcenter_id': target_wc.id, 'date_start': start_dt,
                                'date_finished': end_dt, 'duration_expected': work_minutes
                            })
                        mo.button_plan()
                    
                    # Başarılı sayacı artır
                    processed_count += 1
                    
            if processed_count == 0:
                raise UserError("Uyarı: Planlanacak geçerli bir kalıp grubu bulunamadı!\n\nOlası Sebepler:\n1. 'Kalıp Ekle' kısmından kalıp seçilmemiş olabilir.\n2. Seçili kalıba MO eklenmemiş olabilir.\n3. Sistemde kayıtlı 'hayalet' gruplar temizlenmiş olabilir.")
        else:
            # Eski batch_line_ids kullan (backward compatibility)
            for line in self.batch_line_ids:
                target_wc = line.workcenter_id
                start_dt = line.date_start
                end_dt = line.date_finished
                work_minutes = self._calculate_minutes(target_wc, line.time_mode)

                mos_to_process = line.production_ids
                mos_to_confirm = mos_to_process.filtered(lambda m: m.state == 'draft')
                if mos_to_confirm: mos_to_confirm.action_confirm()

                for mo in mos_to_process:
                    if mo.date_start:
                        try: mo.button_unplan()
                        except: pass
                    mo.write({'date_start': start_dt, 'date_finished': end_dt})
                    wos = mo.workorder_ids.filtered(lambda w: w.state not in ('done','cancel'))
                    if wos:
                        wos.write({
                            'workcenter_id': target_wc.id, 'date_start': start_dt,
                            'date_finished': end_dt, 'duration_expected': work_minutes
                        })
                    mo.button_plan()
        return {'type': 'ir.actions.act_window_close'}



class MrpBatchPlanningWizardLine(models.TransientModel):
    _name = 'mrp.batch.planning.wizard.line'
    _description = 'Planlama Satırı'

    wizard_id = fields.Many2one('mrp.batch.planning.wizard')
    group_id = fields.Many2one('mrp.batch.planning.workcenter.group', string="Kalıp Grubu", ondelete='cascade')
    workcenter_id = fields.Many2one('mrp.workcenter', string="Atanan Kalıp")
    allowed_workcenter_ids = fields.Many2many('mrp.workcenter', compute='_compute_allowed_workcenter_ids')
    allowed_production_ids = fields.Many2many('mrp.production', compute='_compute_allowed_production_ids')
    production_ids = fields.Many2many('mrp.production', string="Üretim Emirleri")
    product_names = fields.Text(string="İçerik", compute='_compute_total_length_and_names')
    total_length_usage = fields.Float(string="Kullanılan Boy", compute='_compute_total_length_and_names')
    capacity_exceeded = fields.Boolean(string="Kapasite Aşıldı", compute='_compute_total_length_and_names')
    capacity_status = fields.Char(string="Durum", compute='_compute_total_length_and_names')
    line_capacity = fields.Float(string="Kalıp Kapasitesi", related='group_id.workcenter_capacity')
    sequence = fields.Integer(string="Sıra", default=10)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('group_id') and 'sequence' not in vals:
                existing = self.search([('group_id', '=', vals['group_id'])], order='sequence desc', limit=1)
                vals['sequence'] = (existing.sequence + 10) if existing else 10
        return super().create(vals_list)

    def _default_line_date_start(self):
        """Yarın sabah 08:00 (Türkiye saati) - UTC 05:00"""
        from datetime import datetime, timedelta
        tomorrow = fields.Date.today() + timedelta(days=1)
        # Türkiye UTC+3, 08:00 lokal = 05:00 UTC
        return datetime.combine(tomorrow, datetime.min.time().replace(hour=5, minute=0))


    date_start = fields.Datetime(string="Başlangıç", default=_default_line_date_start)

    date_finished = fields.Datetime(string="Bitiş")
    time_mode = fields.Selection([
        ('1_1', 'Tek Döküm (X₁)'), ('1_2', 'Çift Döküm (X₂)'),
        ('1_3', '3 Döküm (X₃)'), ('1_4', '4 Döküm (X₄)')
    ], string="Döküm Sayısı", default='1_1', required=True)


    @api.depends('production_ids')
    def _compute_allowed_workcenter_ids(self):
        for line in self:
            if line.production_ids:
                # Seçilen ürüne uygun kalıpları getir (Çap kontrolü + Allowed listesi)
                first = line.production_ids[0]
                tmpl = first.product_id.product_tmpl_id
                
                # 1. Ürünün kendi listesi varsa
                if tmpl.allowed_workcenter_ids:
                    line.allowed_workcenter_ids = tmpl.allowed_workcenter_ids
                else:
                    # 2. Yoksa ölçüye göre ara
                    domain = []
                    if tmpl.x_check_strand_rules:
                        tech = self.wizard_id._get_tech_data(first)
                        domain = [
                            ('x_width_capacity', '=', tech['en']),
                            ('x_height_capacity', '=', tech['boy'])
                        ]
                    line.allowed_workcenter_ids = self.env['mrp.workcenter'].search(domain)
            else:
                # Ürün seçili değilse hepsi gelebilir
                line.allowed_workcenter_ids = self.env['mrp.workcenter'].search([])



    @api.depends('group_id.workcenter_id', 'group_id.wizard_id.step2_product_group_ids', 'group_id.wizard_id.step2_product_group_ids.mo_ids')
    def _compute_allowed_production_ids(self):
        for line in self:
            # Wizard'ı bul
            wizard = line.group_id.wizard_id if line.group_id else line.wizard_id
            if not wizard:
                line.allowed_production_ids = self.env['mrp.production']
                continue
            
            # Etkili kalıp
            effective_wc = line.group_id.workcenter_id if line.group_id else line.workcenter_id
            if not effective_wc:
                line.allowed_production_ids = self.env['mrp.production']
                continue
            
            # Wizard'daki ürün gruplarından MO'ları topla
            all_mos = self.env['mrp.production']
            for product_group in wizard.step2_product_group_ids:
                all_mos |= product_group.mo_ids
            
            if not all_mos:
                line.allowed_production_ids = self.env['mrp.production']
                continue
            
            # Kalıba uygunluk kontrolü (boyut)
            suitable = self.env['mrp.production']
            for mo in all_mos:
                # Boyut kontrolü
                if effective_wc.x_width_capacity and mo.en > effective_wc.x_width_capacity:
                    continue
                if effective_wc.x_height_capacity and mo.boy > effective_wc.x_height_capacity:
                    continue
                suitable |= mo
            
            line.allowed_production_ids = suitable


    @api.depends('production_ids')
    def _compute_total_length_and_names(self):
        """Toplam uzunluk ve ürün isimlerini hesapla"""
        for line in self:
            if line.production_ids:
                line.total_length_usage = sum(getattr(mo, 'uzunluk', 0.0) or 0.0 for mo in line.production_ids)
                names_list = []
                for mo in line.production_ids:
                    sn = mo.lot_producing_id.name if mo.lot_producing_id else "SN-Yok"
                    names_list.append(f"{mo.name} / {mo.product_id.display_name} / {getattr(mo, 'uzunluk', 0.0):.0f} [{sn}]")
                line.product_names = "\n".join(names_list)
            else:
                line.total_length_usage = 0.0
                line.product_names = ""
            
            # Kapasite kontrolü
            cap = line.line_capacity
            usage = line.total_length_usage
            if cap > 0 and usage > 0:
                if usage > cap:
                    line.capacity_exceeded = True
                    line.capacity_status = '⚠️ KAPASİTE AŞILDI!'
                else:
                    line.capacity_exceeded = False
                    line.capacity_status = '✅ Müsait'
            elif usage > 0:
                line.capacity_exceeded = False
                line.capacity_status = '✅ Müsait'
            else:
                line.capacity_exceeded = False
                line.capacity_status = ''

    @api.onchange('production_ids')
    def _onchange_production_ids(self):
        # 1. Eğer liste boşsa her şeyi temizle
        if not self.production_ids:
            self.total_length_usage = 0.0; self.product_names = ""
            return

        # 2. Akıllı Seçim Mantığı: Eğer kullanıcı YENİ bir tek ürün seçtiyse
        # (Yani henüz kaydedilmemiş, sadece 1 tane MO tetiklendiyse)
        # Bu ürünün "Kardeşlerini" bul ve listeye ekle.
        # Not: Bu mantık biraz riskli olabilir, sonsuz döngüye girmemeli.
        # Bu yüzden sadece "tek bir ürün seçildiğinde" çalıştırıyoruz.
        
        current_ids = self.production_ids.ids
        if len(current_ids) == 1:
            first_mo = self.production_ids[0]
            # Kardeşleri Bul (Aynı procurement group veya aynı origin)
            # Not: Sadece "Planlanmamış" olanları almalıyız.
            
            domain = [
                ('id', '!=', first_mo.id),
                ('state', 'in', ['confirmed', 'draft']),
                ('date_start', '=', False),
                ('kalip_id', '=', False),  # Kalıp atanmamış olanlar
                ('product_id', '=', first_mo.product_id.id) # Genellikle aynı ürün olur
            ]
            
            # Kriter 1: Procurement Group (En güçlü bağ)
            if first_mo.procurement_group_id:
                domain.append(('procurement_group_id', '=', first_mo.procurement_group_id.id))
            # Kriter 2: Origin (Sipariş No)
            elif first_mo.origin:
                domain.append(('origin', '=', first_mo.origin))
            else:
                # Bağ yoksa sadece kendisi kalır
                domain = False 

            if domain:
                siblings = self.env['mrp.production'].search(domain)
                if siblings:
                    # Kardeşleri mevcut listeye ekle
                    new_ids = current_ids + siblings.ids
                    self.production_ids = [(6, 0, new_ids)]
                    # append metodu yerine many2many ataması (6,0) daha güvenlidir onchange içinde
                    # Ancak burada return yaparak tekrar onchange tetiklenmesini bekleyebiliriz 
                    # veya direkt hesaplamaya geçebiliriz.
        
        # 3. Hesaplamaları yap
        self.total_length_usage = sum(getattr(mo, 'uzunluk', 0.0) for mo in self.production_ids)
        names_list = []
        for mo in self.production_ids:
             sn = mo.lot_producing_id.name if mo.lot_producing_id else "SN-Yok"
             names_list.append(f"{mo.name} / {mo.product_id.display_name} / {getattr(mo, 'uzunluk', 0.0):.0f} [{sn}]")
        self.product_names = "\n".join(names_list)

