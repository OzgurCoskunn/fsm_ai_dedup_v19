# -*- coding: utf-8 -*-
import json
import time
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
        # Timeout default 800ms (spec)
        timeout_ms = int(param.get_param('fsm_ai_dedup.timeout_ms', '800') or 800)
        return {
            'enabled': param.get_param('fsm_ai_dedup.ai_enabled', 'False') == 'True',
            'api_key': param.get_param('fsm_ai_dedup.openrouter_api_key', ''),
            'model': param.get_param(
                'fsm_ai_dedup.openrouter_model',
                'anthropic/claude-haiku-4-5',
            ),
            'timeout_seconds': timeout_ms / 1000.0,
        }

    @api.model
    def is_configured(self):
        cfg = self._get_config()
        return bool(cfg['api_key'])

    @api.model
    def test_connection(self):
        cfg = self._get_config()
        if not cfg['api_key']:
            return {'ok': False, 'message': _('OpenRouter API key not configured.')}
        # Test cagrisinda timeout'u biraz uzatalim (tek seferlik)
        result = self._call(
            system_prompt="JSON cevap veren bir asistansin.",
            user_prompt='JSON: {"status":"ok"}',
            max_tokens=40,
            timeout_override=10.0,
        )
        if not result:
            return {'ok': False, 'message': _('API request failed - check logs.')}
        return {
            'ok': True,
            'message': _('Connection OK. Response: %s') % json.dumps(result.get('parsed', {}), ensure_ascii=False),
        }

    @api.model
    def _call(self, system_prompt, user_prompt, temperature=0.0,
              max_tokens=400, timeout_override=None):
        """Donus: dict {parsed, raw, usage, model_used, latency_ms} veya None.

        timeout_override: saniye cinsinden (default config'ten alir, 0.8s).
        """
        cfg = self._get_config()
        if not cfg['api_key']:
            _logger.warning("OpenRouter API key not configured")
            return None

        timeout = timeout_override if timeout_override else cfg['timeout_seconds']

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
        t0 = time.time()
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            latency_ms = int((time.time() - t0) * 1000)
            resp.raise_for_status()
            data = resp.json()
            content = data['choices'][0]['message']['content']
            return {
                'parsed': json.loads(content),
                'raw': content,
                'usage': data.get('usage', {}),
                'model_used': data.get('model', cfg['model']),
                'latency_ms': latency_ms,
            }
        except requests.Timeout:
            latency_ms = int((time.time() - t0) * 1000)
            _logger.warning("OpenRouter timeout after %dms", latency_ms)
            return None
        except requests.RequestException as e:
            _logger.error("OpenRouter request failed: %s", e)
            return None
        except (KeyError, json.JSONDecodeError, ValueError) as e:
            _logger.error("OpenRouter response parse error: %s", e)
            return None

    @api.model
    def call_llm(self, system_prompt, user_prompt, **kw):
        return self._call(system_prompt, user_prompt, **kw)
