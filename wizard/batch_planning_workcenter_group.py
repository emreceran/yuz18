# -*- coding: utf-8 -*-

from odoo import models, fields, api

class MrpBatchPlanningWorkcenterGroup(models.TransientModel):
    """Her kalıp için bir grup - Notebook tab olarak gösterilecek"""
    _name = 'mrp.batch.planning.workcenter.group'
    _description = 'Kalıp Planlama Grubu'
    _order = 'workcenter_id'
    
    wizard_id = fields.Many2one(
        'mrp.batch.planning.wizard',
        string="Wizard",
        ondelete='cascade'
    )
    
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Kalıp',
        readonly=True,
        required=True
    )
    
    workcenter_capacity = fields.Float(
        string='Kapasite (cm)',
        related='workcenter_id.x_max_length_capacity',
        readonly=True
    )

    # Kalıcı MO referans listesi - başlangıçta seçilen tüm MO'lar
    initial_mo_ids = fields.Many2many(
        'mrp.production',
        'workcenter_group_initial_mo_rel',
        'group_id',
        'production_id',
        string='Başlangıç Üretim Emri Listesi',
        help='Bu kalıp grubuna başlangıçta yerleştirilmek üzere seçilen tüm MO\'lar'
    )
    
    date_start = fields.Datetime(
        string='Başlangıç Tarihi',
        required=True,
        default=fields.Datetime.now
    )
    
    line_ids = fields.One2many(
        'mrp.batch.planning.wizard.line',
        'group_id',
        string='Planlama Satırları'
    )
    
    total_length = fields.Float(
        string='Toplam Uzunluk (cm)',
        compute='_compute_totals',
        readonly=True
    )
    
    production_count = fields.Integer(
        string='Üretim Emri Sayısı',
        compute='_compute_totals',
        readonly=True
    )
    
    # Manuel yerleştirme için: Başlangıçta seçilen MO'lar (sabit liste)
    available_for_placement_ids = fields.Many2many(
        'mrp.production',
        related='initial_mo_ids',
        string='Yerleştirilebilir Üretim Emirleri',
        readonly=True,
    )
    
    # Dropdown filtresi: Satırlara zaten eklenmiş MO'ları çıkar
    dropdown_mo_ids = fields.Many2many(
        'mrp.production',
        compute='_compute_dropdown_mo_ids',
        string='Dropdown Üretim Emri Listesi'
    )
    
    @api.depends('initial_mo_ids', 'line_ids.production_ids')
    def _compute_dropdown_mo_ids(self):
        for group in self:
            placed = group.line_ids.production_ids
            group.dropdown_mo_ids = group.initial_mo_ids - placed
    
    @api.depends('line_ids', 'line_ids.production_ids')
    def _compute_totals(self):
        for group in self:
            total_len = 0.0
            total_count = 0
            for line in group.line_ids:
                total_count += len(line.production_ids)
                for mo in line.production_ids:
                    total_len += getattr(mo, 'uzunluk', 0.0) or 0.0
            group.total_length = total_len
            group.production_count = total_count

    def resequence_lines(self, force_start_date=None):
        """
        Satırları verilen tarihe (veya mevcut ayarlara) göre yeniden dizer.
        force_start_date: Eğer verilirse, ilk satır kontrolünü ezer ve bu tarihten başlar.
        """
        from datetime import datetime
        from odoo.addons.yuz18.wizard.batch_planning_wizard import (
            calculate_next_slot, _normalize_to_working_hours
        )
        
        if not self.line_ids:
            return
        
        # 1. Başlangıç Çapası (Anchor) Belirle
        if force_start_date:
            anchor_date = force_start_date
        else:
            # Öncelik: İlk Satırın Tarihi > Grubun Tarihi > Varsayılan
            anchor_date = self.date_start
            
            # İlk satırın mevcut tarihini kontrol et (varsa onu baz al)
            first_line = self.line_ids.sorted('sequence')[:1]
            if first_line and first_line.date_start:
                # Eğer ilk satırın tarihi, grubun tarihinden ilerideyse onu koru
                current_first_date = _normalize_to_working_hours(first_line.date_start)
                if current_first_date and (not anchor_date or current_first_date > anchor_date):
                    anchor_date = current_first_date

            if not anchor_date and self.wizard_id:
                anchor_date = self.wizard_id.workcenter_date_start or self.wizard_id._default_scheduled_date()
            if not anchor_date:
                anchor_date = datetime.now()
            
        anchor_date = _normalize_to_working_hours(anchor_date)
            
        # 2. DB'deki mevcut planlarla çakışma kontrolü (En geç tarih kazanır)
        if self.wizard_id and self.workcenter_id:
            db_last = self.wizard_id._get_workcenter_last_planned_date(self.workcenter_id.id)
            if db_last:
                db_next = _normalize_to_working_hours(db_last)
                if db_next and anchor_date and db_next > anchor_date:
                    anchor_date = db_next
        
        # 3. Aynı kalıptaki önceki grupların bitişini kontrol et (Wizard içindeki diğer gruplar)
        if not force_start_date and self.wizard_id and self.workcenter_id:
            sibling_groups = self.wizard_id.workcenter_group_ids.filtered(
                lambda g: g.workcenter_id and g.workcenter_id.id == self.workcenter_id.id 
                       and g.line_ids
            )
            
            my_index = -1
            for i, g in enumerate(sibling_groups):
                if g.id == self.id or (hasattr(self, '_origin') and g.id == self._origin.id):
                    my_index = i
                    break
            
            if my_index > 0:
                prev_group = sibling_groups[my_index - 1]
                last_line = prev_group.line_ids.sorted('sequence', reverse=True)[:1]
                if last_line and last_line.date_finished:
                    prev_end = _normalize_to_working_hours(last_line.date_finished)
                    if prev_end and anchor_date and prev_end > anchor_date:
                        anchor_date = prev_end
        
        # Grubun başlangıç tarihini güncelle
        if self.date_start != anchor_date:
            self.date_start = anchor_date
        
        # 4. Hesaplamayı Başlat
        current_pointer = anchor_date
        time_mode_hours = {'1_1': 9.0, '1_2': 4.5, '1_3': 3.0, '1_4': 2.25}
        
        for line in self.line_ids.sorted('sequence'):
            dur = time_mode_hours.get(line.time_mode or '1_1', 9.0)
            start, end = calculate_next_slot(current_pointer, dur)
            
            if line.date_start != start:
                line.date_start = start
            if line.date_finished != end:
                line.date_finished = end
                
            current_pointer = end

    @api.onchange('line_ids')
    def _onchange_line_ids_resequence(self):
        """Satır değişince normal resequence çağır"""
        self.resequence_lines()

    @api.onchange('date_start')
    def _onchange_date_start_resequence(self):
        """
        Başlangıç tarihi değişince (elle veya wizard tarafından ileri atılınca),
        satırları yeni tarihe göre zorla güncelle.
        """
        if self.date_start:
            self.resequence_lines(force_start_date=self.date_start)

