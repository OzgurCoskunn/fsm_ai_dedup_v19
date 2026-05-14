# -*- coding: utf-8 -*-
from odoo import models, fields


class AIDedupLog(models.Model):
    _name = 'ai.dedup.log'
    _description = 'AI Dedup Log'
    _order = 'create_date desc'

    endpoint = fields.Char(string='Endpoint')
    partner_type = fields.Char(string='Partner Type')
    parent_id = fields.Many2one('res.partner', string='Parent Partner')
    candidate_ids = fields.Many2many('res.partner', string='Candidates')
    matched_id = fields.Many2one('res.partner', string='Matched Partner')
    confidence = fields.Integer(string='Confidence %')
    threshold = fields.Integer(string='Threshold %')
    decision = fields.Selection([
        ('normalize_match', 'Normalize ile bulundu'),
        ('ai_match', 'AI ile eslesti'),
        ('ai_low_confidence', 'AI bulamadi (dusuk confidence)'),
        ('ai_no_match', 'AI esleme yok dedi'),
        ('ai_skipped_no_candidates', 'Aday yok'),
        ('ai_disabled', 'AI kapali'),
        ('ai_error', 'AI hata'),
        ('manual_test', 'Manuel test (wizard)'),
        ('new_created', 'Yeni partner olusturuldu'),
    ], string='Decision')
    reason = fields.Text(string='Reason')
    model_used = fields.Char(string='LLM Model')
    tokens_in = fields.Integer(string='Tokens In')
    tokens_out = fields.Integer(string='Tokens Out')
    input_payload = fields.Text(string='Input (JSON)')
    raw_response = fields.Text(string='Raw LLM Response')
