# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fsm_ai_dedup_enabled = fields.Boolean(
        string='AI Dedup Etkin',
        config_parameter='fsm_ai_dedup.ai_enabled',
        default=False,
        help='Kapaliyken AI cagrisi yapilmaz; sistem normal akisla devam eder. '
             'Acikken partner create eden API metodlari adayi AI ile dogrular.',
    )
    fsm_ai_dedup_api_key = fields.Char(
        string='OpenRouter API Key',
        config_parameter='fsm_ai_dedup.openrouter_api_key',
    )
    fsm_ai_dedup_model = fields.Char(
        string='OpenRouter Model',
        config_parameter='fsm_ai_dedup.openrouter_model',
        default='anthropic/claude-haiku-4-5',
        help='Ornek: anthropic/claude-haiku-4-5 (onerilen), '
             'openai/gpt-4o-mini, google/gemini-2.5-flash',
    )
    fsm_ai_dedup_timeout_ms = fields.Integer(
        string='API Timeout (ms)',
        config_parameter='fsm_ai_dedup.timeout_ms',
        default=800,
        help='Bu sureden uzun cevaplar timeout sayilir ve yeni kayit acilir.',
    )

    def action_test_openrouter_connection(self):
        self.ensure_one()
        result = self.env['openrouter.service'].test_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'OpenRouter Test',
                'message': result['message'],
                'type': 'success' if result['ok'] else 'danger',
                'sticky': True,
            },
        }
