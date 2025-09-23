# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re  # Regex için eklendi

_logger = logging.getLogger(__name__)


class StockLotCustom(models.Model):
    _inherit = 'stock.lot'

    @api.model
    def _get_next_serial(self, company, product):
        """Return the next serial number to be attributed to the product."""
        if product.tracking != "none":
            last_serial = self.env['stock.lot'].search(
                ['|', ('company_id', '=', company.id), ('company_id', '=', False)],
                limit=1, order='id DESC')
            if last_serial:
                return self.env['stock.lot'].generate_lot_names(last_serial.name, 2)[1]['lot_name']
        return False