# -*- coding: utf-8 -*-
from odoo import models, fields


class PartnerDedupLog(models.Model):
    _name = 'partner.dedup.log'
    _description = 'Partner Dedup AI Decision Log'
    _order = 'create_date desc'

    # Baglam
    context_label = fields.Char(
        string='Context',
        help='Hangi akistan cagrildi (ornegin "createWorkorder/service")',
    )

    # Girdi (KVKK: sadece adres)
    incoming_street = fields.Char(string='Incoming Street')
    incoming_district = fields.Char(string='Incoming District')
    incoming_town = fields.Char(string='Incoming Town')

    # Adaylar
    candidate_count = fields.Integer(string='Candidate Count')
    candidate_partner_ids = fields.Many2many(
        'res.partner',
        relation='partner_dedup_log_candidate_rel',
        column1='log_id', column2='partner_id',
        string='Candidates',
    )

    # AI cevabi
    matched_partner_id = fields.Many2one('res.partner', string='Matched Partner')
    confidence = fields.Char(string='Confidence', help='high / low')
    decision = fields.Selection([
        ('match', 'AI eslesme buldu'),
        ('no_match', 'AI eslesme yok dedi'),
        ('low_confidence', 'AI emin degil (low confidence)'),
        ('hallucination', 'AI gecersiz aday indexi dondurdu'),
        ('invalid_response', 'AI gecersiz format dondurdu'),
        ('error_or_timeout', 'LLM timeout veya hata'),
        ('partner_gone', 'Eslesen partner kaybolmus'),
        ('manual_test', 'Manuel wizard testi'),
    ], string='Decision')
    reason = fields.Text(string='Reason')

    # Telemetri
    model_used = fields.Char(string='LLM Model')
    tokens_in = fields.Integer(string='Tokens In')
    tokens_out = fields.Integer(string='Tokens Out')
    latency_ms = fields.Integer(string='Latency (ms)')

    # Debug
    raw_response = fields.Text(string='Raw LLM Response')
