# -*- coding: utf-8 -*-
"""Manuel test wizard'i: bir partner girisi yap, mevcut adaylarla AI esletir."""
import json

from odoo import models, fields, api


class AIDedupTestWizard(models.TransientModel):
    _name = 'ai.dedup.test.wizard'
    _description = 'AI Dedup Manuel Test'

    parent_id = fields.Many2one(
        'res.partner', string='Ana Firma (parent)',
        domain=[('parent_id', '=', False)], required=True,
    )
    partner_type = fields.Selection([
        ('contact', 'Kontak'),
        ('invoice', 'Fatura Adresi'),
        ('delivery', 'Sevk Adresi'),
        ('other', 'Diger Adres'),
    ], default='contact', required=True)
    test_name = fields.Char(string='Yeni Isim', required=True)
    test_street = fields.Char(string='Yeni Adres')
    test_mobile = fields.Char(string='Telefon / Mobil')
    test_email = fields.Char(string='Email')

    candidates_count = fields.Integer(string='Aday Sayisi', readonly=True)
    matched_partner_id = fields.Many2one('res.partner', string='Eslesen Partner', readonly=True)
    confidence = fields.Integer(string='Confidence (%)', readonly=True)
    threshold = fields.Integer(string='Threshold (%)', readonly=True)
    reason = fields.Text(string='AI Aciklamasi', readonly=True)
    candidates_text = fields.Text(string='Adaylar (LLM cagrisinda gonderilen)', readonly=True)
    raw_response = fields.Text(string='Raw LLM Response', readonly=True)
    model_used = fields.Char(string='Model', readonly=True)
    tokens_in = fields.Integer(string='Tokens In', readonly=True)
    tokens_out = fields.Integer(string='Tokens Out', readonly=True)

    def action_run_match(self):
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        domain = [
            ('parent_id', '=', self.parent_id.id),
            ('type', '=', self.partner_type),
        ]
        if self.partner_type == 'contact':
            domain.append(('is_company', '=', False))

        candidates = Partner.search(domain)

        new_vals = {
            'name': self.test_name,
            'street': self.test_street,
            'mobile': self.test_mobile,
            'email': self.test_email,
        }

        result = self.env['partner.ai.matcher'].sudo().find_match(new_vals, candidates)

        candidates_dump = "\n".join([
            "[%s] %s | %s | %s | %s" % (
                p.id, p.name or '-', p.street or '-',
                p.mobile or p.phone or '-', p.email or '-',
            )
            for p in candidates[:30]
        ]) or "Aday yok"

        cfg = self.env['openrouter.service'].sudo()._get_config()
        tokens = result.get('tokens') or {}

        self.write({
            'candidates_count': len(candidates),
            'matched_partner_id': result['matched'].id if result['matched'] else False,
            'confidence': result['confidence'],
            'threshold': cfg['confidence_threshold'],
            'reason': result['reason'],
            'candidates_text': candidates_dump,
            'raw_response': result.get('raw'),
            'model_used': result.get('model_used'),
            'tokens_in': tokens.get('prompt_tokens', 0),
            'tokens_out': tokens.get('completion_tokens', 0),
        })

        # Logla
        self.env['ai.dedup.log'].sudo().create({
            'endpoint': 'manual_wizard',
            'partner_type': self.partner_type,
            'parent_id': self.parent_id.id,
            'candidate_ids': [(6, 0, candidates.ids)],
            'matched_id': result['matched'].id if result['matched'] else False,
            'confidence': result['confidence'],
            'threshold': cfg['confidence_threshold'],
            'decision': 'manual_test',
            'reason': result['reason'],
            'model_used': result.get('model_used'),
            'tokens_in': tokens.get('prompt_tokens', 0),
            'tokens_out': tokens.get('completion_tokens', 0),
            'input_payload': json.dumps(new_vals, ensure_ascii=False, default=str),
            'raw_response': result.get('raw'),
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ai.dedup.test.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
