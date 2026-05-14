# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fsm_ai_dedup_enabled = fields.Boolean(
        string='AI Dedup Etkin',
        config_parameter='fsm_ai_dedup.enabled',
        default=False,
    )
    fsm_ai_dedup_api_key = fields.Char(
        string='OpenRouter API Key',
        config_parameter='fsm_ai_dedup.openrouter_api_key',
    )
    fsm_ai_dedup_model = fields.Char(
        string='OpenRouter Model',
        config_parameter='fsm_ai_dedup.openrouter_model',
        default='openai/gpt-4o-mini',
        help='Ornek: openai/gpt-4o-mini, anthropic/claude-haiku-4-5, '
             'google/gemini-2.5-flash, meta-llama/llama-3.3-70b-instruct',
    )
    fsm_ai_dedup_threshold = fields.Integer(
        string='Eslesme Guven Esigi (%)',
        config_parameter='fsm_ai_dedup.confidence_threshold',
        default=90,
    )
    fsm_ai_dedup_timeout = fields.Integer(
        string='API Timeout (saniye)',
        config_parameter='fsm_ai_dedup.timeout',
        default=15,
    )
    fsm_ai_dedup_max_candidates = fields.Integer(
        string='Maks. Aday Sayisi',
        config_parameter='fsm_ai_dedup.max_candidates',
        default=20,
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
