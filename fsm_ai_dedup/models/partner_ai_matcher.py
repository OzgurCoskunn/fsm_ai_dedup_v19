# -*- coding: utf-8 -*-
"""LLM ile partner/adres eslestirme servisi (Odoo 19)."""
import logging

from odoo import models, api

_logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Sen bir Turkiye adres karsilastirma uzmanisin. "
    "Sana bir 'yeni adres' ve ayni bolgedeki 'aday adresler' verilecek. "
    "Yeni adresin adaylardan biriyle AYNI fiziksel yer olup olmadigini belirle.\n\n"
    "Kurallar:\n"
    "- Yazim farklari (Cd./Caddesi, No:1/No 1, D:1/Daire 1) AYNI saymali.\n"
    "- Buyuk/kucuk harf, Turkce karakter ve noktalama AYNI saymali.\n"
    "- Telefon format farklari (+90/0 onek, bosluk, tire) AYNI saymali.\n"
    "- Ayni binada farkli daire AYNI yer DEGILDIR.\n"
    "- Ayni caddede farkli numara AYNI yer DEGILDIR.\n"
    "- Suheli durumda 'ayni degil' de.\n\n"
    "Sadece JSON yanit ver, ek aciklama yazma:\n"
    '{"match_id": <aday_id veya null>, "confidence": <0-100>, "reason": "<kisa Turkce>"}'
)


class PartnerAIMatcher(models.AbstractModel):
    _name = 'partner.ai.matcher'
    _description = 'AI-powered partner address matching'

    @api.model
    def find_match(self, new_partner_vals, candidates):
        """Args:
            new_partner_vals: dict (name/street/mobile/phone/email/vat/district_name/town_name)
            candidates: res.partner recordset
        Returns:
            dict {matched, confidence, reason, model_used, tokens, raw}
        """
        empty = {
            'matched': None, 'confidence': 0, 'reason': '',
            'model_used': None, 'tokens': {}, 'raw': None,
        }
        if not candidates:
            empty['reason'] = 'Aday yok'
            return empty

        openrouter = self.env['openrouter.service']
        cfg = openrouter._get_config()
        if not cfg['api_key'] or not cfg['enabled']:
            empty['reason'] = 'AI dedup disabled'
            return empty

        candidate_lines = []
        for p in candidates[:cfg['max_candidates']]:
            district_name = p.country_id.name if not hasattr(p, 'district_id') else (
                p.district_id.name if p.district_id else '-'
            )
            town_name = '-'
            try:
                town_name = p.town_id.name if p.town_id else '-'
            except Exception:
                town_name = '-'
            try:
                district_name = p.district_id.name if p.district_id else '-'
            except Exception:
                pass
            candidate_lines.append(
                "[%s] isim=%s | adres=%s %s | mahalle=%s | ilce=%s | tel=%s | email=%s" % (
                    p.id,
                    (p.name or '-')[:100],
                    (p.street or '-')[:80],
                    (p.street2 or '')[:80],
                    district_name,
                    town_name,
                    p.mobile or p.phone or '-',
                    (p.email or '-')[:60],
                )
            )
        candidate_text = "\n".join(candidate_lines)

        new_summary = (
            "YENI ADRES (henuz olusturulmadi):\n"
            "isim: %s\n"
            "adres: %s\n"
            "mahalle: %s\n"
            "ilce: %s\n"
            "telefon: %s\n"
            "email: %s\n"
        ) % (
            new_partner_vals.get('name', '-'),
            new_partner_vals.get('street') or new_partner_vals.get('street2', '-'),
            new_partner_vals.get('district_name', '-'),
            new_partner_vals.get('town_name', '-'),
            new_partner_vals.get('mobile') or new_partner_vals.get('phone', '-'),
            new_partner_vals.get('email', '-'),
        )

        user_prompt = (
            "%s\nADAYLAR:\n%s\n\n"
            "Yeni adres adaylardan biriyle AYNI fiziksel yer mi? "
            "Sadece JSON yanit ver."
        ) % (new_summary, candidate_text)

        result = openrouter.call_llm(SYSTEM_PROMPT, user_prompt)
        if not result:
            empty['reason'] = 'AI did not respond'
            return empty

        parsed = result.get('parsed') or {}
        match_id = parsed.get('match_id')
        try:
            confidence = int(parsed.get('confidence', 0) or 0)
        except (TypeError, ValueError):
            confidence = 0
        reason = parsed.get('reason', '') or ''
        model_used = result.get('model_used')
        tokens = result.get('usage', {})

        if match_id and int(match_id) not in candidates.ids:
            _logger.warning(
                "AI returned id=%s NOT in candidates %s", match_id, candidates.ids,
            )
            return {
                'matched': None, 'confidence': 0,
                'reason': 'AI hallucinated id=%s' % match_id,
                'model_used': model_used, 'tokens': tokens, 'raw': result.get('raw'),
            }

        matched = candidates.browse(int(match_id)) if match_id else None
        return {
            'matched': matched if (matched and matched.exists()) else None,
            'confidence': confidence,
            'reason': reason,
            'model_used': model_used,
            'tokens': tokens,
            'raw': result.get('raw'),
        }
