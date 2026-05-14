# -*- coding: utf-8 -*-
import json
import logging
import requests

from odoo import models, api, _

_logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterService(models.AbstractModel):
    _name = 'openrouter.service'
    _description = 'OpenRouter LLM caller'

    @api.model
    def _get_config(self):
        param = self.env['ir.config_parameter'].sudo()
        return {
            'enabled': param.get_param('fsm_ai_dedup.enabled', 'False') == 'True',
            'api_key': param.get_param('fsm_ai_dedup.openrouter_api_key', ''),
            'model': param.get_param('fsm_ai_dedup.openrouter_model', 'openai/gpt-4o-mini'),
            'confidence_threshold': int(
                param.get_param('fsm_ai_dedup.confidence_threshold', '90') or 90
            ),
            'timeout': int(param.get_param('fsm_ai_dedup.timeout', '15') or 15),
            'max_candidates': int(param.get_param('fsm_ai_dedup.max_candidates', '20') or 20),
        }

    @api.model
    def is_enabled(self):
        cfg = self._get_config()
        return bool(cfg['enabled'] and cfg['api_key'])

    @api.model
    def test_connection(self):
        cfg = self._get_config()
        if not cfg['api_key']:
            return {'ok': False, 'message': _('OpenRouter API key not configured.')}
        result = self._call(
            system_prompt="Sen kisaca JSON cevap veren bir asistansin.",
            user_prompt='JSON: {"status":"ok","model":"<your model name>"}',
            max_tokens=80,
        )
        if not result:
            return {'ok': False, 'message': _('API request failed - check logs.')}
        return {
            'ok': True,
            'message': _('Connection OK. Response: %s') % json.dumps(result, ensure_ascii=False),
        }

    @api.model
    def _call(self, system_prompt, user_prompt, temperature=0.0, max_tokens=500):
        cfg = self._get_config()
        if not cfg['api_key']:
            _logger.warning("OpenRouter API key not configured")
            return None

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        headers = {
            'Authorization': 'Bearer %s' % cfg['api_key'],
            'Content-Type': 'application/json',
            'HTTP-Referer': base_url or 'https://odoo.local',
            'X-Title': 'FSM Partner Dedup',
        }
        payload = {
            'model': cfg['model'],
            'temperature': temperature,
            'max_tokens': max_tokens,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        }
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=cfg['timeout'],
            )
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content']
            return {
                'parsed': json.loads(content),
                'raw': content,
                'usage': data.get('usage', {}),
                'model_used': data.get('model', cfg['model']),
            }
        except requests.RequestException as e:
            _logger.error("OpenRouter request failed: %s", e)
            return None
        except (KeyError, json.JSONDecodeError, ValueError) as e:
            _logger.error("OpenRouter response parse error: %s", e)
            return None

    @api.model
    def call_llm(self, system_prompt, user_prompt, **kw):
        return self._call(system_prompt, user_prompt, **kw)
