# -*- coding: utf-8 -*-
# from odoo import http


# class Yuz18(http.Controller):
#     @http.route('/yuz18/yuz18', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/yuz18/yuz18/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('yuz18.listing', {
#             'root': '/yuz18/yuz18',
#             'objects': http.request.env['yuz18.yuz18'].search([]),
#         })

#     @http.route('/yuz18/yuz18/objects/<model("yuz18.yuz18"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('yuz18.object', {
#             'object': obj
#         })

