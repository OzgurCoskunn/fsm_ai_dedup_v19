# -*- coding: utf-8 -*-
"""Partner dedup AI tie-breaker.

KVKK NOTU:
- LLM'e sadece adres metni gonderilir (street + street2 + district name + town name).
- Isim, telefon, e-posta, VAT GONDERILMEZ.
- Toggle kapaliysa AI cagrisi yapilmaz.
- Hata/timeout durumunda False doner; cagiran 'yeni kayit ac' diyebilir.

Kullanim ornegi (mesela `_get_merchant` icinde):

    candidates = partner.search([...])   # mevcut arama
    if env['partner.dedup.ai'].is_enabled() and candidates:
        matched = env['partner.dedup.ai'].verify_match(
            incoming_address={
                'street': value.get('street2', ''),
                'district_name': district.name,
                'town_name': town.name,
            },
            candidates=candidates,
            context_label='createWorkorder/service',
        )
        if matched:
            service_partner = matched
        else:
            service_partner = partner.create(value)   # AI hayir dedi
    else:
        # AI kapali — mevcut akis
        if candidates:
            service_partner = candidates[:1]
        else:
            service_partner = partner.create(value)
"""
import json
import logging

from odoo import models, api

_logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Sen bir Turkiye adres karsilastirma uzmanisin. "
    "Yeni gelen bir adres verilecek ve N tane aday adres listelenecek. "
    "Yeni adres adaylardan biriyle AYNI fiziksel yer mi belirle.\n\n"
    "Kurallar:\n"
    "- Yazim farklari (Cd./Caddesi, No:1/No 1, D:1/Daire 1) AYNI saymali.\n"
    "- Buyuk/kucuk harf ve noktalama AYNI saymali.\n"
    "- Bina, kapi, daire numarasi farkli ise AYNI YER DEGIL.\n"
    "- Sokak/cadde farkli ise AYNI YER DEGIL.\n"
    "- Suheli ise 'unsure' de.\n\n"
    "SADECE JSON yanit ver, ek aciklama yazma:\n"
    '{"match_index": <0..N-1 veya null>, "confidence": "high|low"}\n'
    "- match_index null -> hicbiri eslesmiyor (veya emin degilsin)\n"
    "- confidence low -> emin degilsin (cagiran tarafta yeni kayit acilir)"
)


class PartnerDedupAI(models.AbstractModel):
    _name = 'partner.dedup.ai'
    _description = 'Partner Dedup AI Tie-breaker'

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    @api.model
    def is_enabled(self):
        """AI dedup acik mi? Hem toggle hem API key gerekli."""
        param = self.env['ir.config_parameter'].sudo()
        enabled = param.get_param('fsm_ai_dedup.ai_enabled', 'False') == 'True'
        if not enabled:
            return False
        api_key = param.get_param('fsm_ai_dedup.openrouter_api_key', '')
        return bool(api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def verify_match(self, incoming_address, candidates, context_label=None):
        """Adaylardan biri yeni adresle ayni mi diye AI'a sor.

        Args:
            incoming_address: dict {street, street2, district_name, town_name}
                              KVKK: bu fonksiyona PII gondermeyin.
            candidates: res.partner recordset (en fazla 20 onerilir)
            context_label: log icin etiket (ornegin "createWorkorder/service")

        Returns:
            res.partner record (eslesen aday) veya False
            False donerse cagiran taraf "yeni kayit ac" demelidir.
        """
        Log = self.env['partner.dedup.log'].sudo()
        Partner = self.env['res.partner'].sudo()

        # 0. Toggle / aday kontrolu
        if not self.is_enabled():
            return False
        if not candidates:
            return False

        # Adaylari sadelestir
        candidate_list = []
        for idx, p in enumerate(candidates[:20]):
            district_name = p.district_id.name if p.district_id else ''
            town_name = p.town_id.name if p.town_id else ''
            # Adres metni: oncelikle street2, yoksa street (orijinal kodda
            # adres genelde street2'de tutulur)
            street_text = (p.street2 or p.street or '').strip()
            candidate_list.append({
                'index': idx,
                'id': p.id,
                'street': street_text,
                'district': district_name,
                'town': town_name,
            })

        # KVKK: PII'yi loglara da yazma — sadece adres
        incoming_clean = {
            'street': (incoming_address.get('street') or '').strip(),
            'district': (incoming_address.get('district_name') or '').strip(),
            'town': (incoming_address.get('town_name') or '').strip(),
        }

        # Prompt insa et
        user_prompt = self._build_prompt(incoming_clean, candidate_list)

        # LLM cagrisi
        result = self.env['openrouter.service'].sudo().call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=120,
        )

        log_vals = {
            'context_label': context_label or '',
            'incoming_street': incoming_clean['street'],
            'incoming_district': incoming_clean['district'],
            'incoming_town': incoming_clean['town'],
            'candidate_count': len(candidate_list),
            'candidate_partner_ids': [(6, 0, candidates.ids[:20])],
        }

        if not result:
            # Timeout / hata -> safer: False
            log_vals.update({
                'decision': 'error_or_timeout',
                'reason': 'LLM yanit vermedi (timeout veya hata)',
            })
            Log.create(log_vals)
            return False

        parsed = result.get('parsed') or {}
        match_idx = parsed.get('match_index')
        confidence = parsed.get('confidence', 'low')

        log_vals.update({
            'model_used': result.get('model_used'),
            'tokens_in': (result.get('usage') or {}).get('prompt_tokens', 0),
            'tokens_out': (result.get('usage') or {}).get('completion_tokens', 0),
            'latency_ms': result.get('latency_ms', 0),
            'raw_response': result.get('raw'),
            'confidence': str(confidence),
        })

        # Low confidence veya null -> False
        if match_idx is None:
            log_vals.update({'decision': 'no_match', 'reason': 'AI hicbir aday eslesmiyor dedi'})
            Log.create(log_vals)
            return False

        if confidence != 'high':
            log_vals.update({
                'decision': 'low_confidence',
                'reason': 'AI emin degil (confidence=%s) - yeni kayit acilacak' % confidence,
            })
            Log.create(log_vals)
            return False

        # Halusinasyon korumasi: index gecerli mi?
        try:
            match_idx = int(match_idx)
        except (TypeError, ValueError):
            log_vals.update({
                'decision': 'invalid_response',
                'reason': 'AI gecersiz match_index dondurdu: %s' % match_idx,
            })
            Log.create(log_vals)
            return False

        if match_idx < 0 or match_idx >= len(candidate_list):
            log_vals.update({
                'decision': 'hallucination',
                'reason': 'AI gecersiz aday indexi dondurdu: %d (aday sayisi=%d)' % (
                    match_idx, len(candidate_list),
                ),
            })
            Log.create(log_vals)
            return False

        matched_id = candidate_list[match_idx]['id']
        matched = Partner.browse(matched_id)
        if not matched.exists():
            log_vals.update({
                'decision': 'partner_gone',
                'reason': 'Eslesen partner bulunamadi (silinmis olabilir)',
            })
            Log.create(log_vals)
            return False

        log_vals.update({
            'decision': 'match',
            'matched_partner_id': matched.id,
            'reason': 'AI yuksek guvenle eslesti',
        })
        Log.create(log_vals)
        return matched

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _build_prompt(self, incoming, candidates):
        lines = []
        lines.append('YENI ADRES:')
        lines.append('  street: %s' % (incoming.get('street') or '-'))
        lines.append('  district (mahalle): %s' % (incoming.get('district') or '-'))
        lines.append('  town (ilce): %s' % (incoming.get('town') or '-'))
        lines.append('')
        lines.append('ADAYLAR:')
        for c in candidates:
            lines.append('  [%d] street=%s | district=%s | town=%s' % (
                c['index'],
                c.get('street') or '-',
                c.get('district') or '-',
                c.get('town') or '-',
            ))
        lines.append('')
        lines.append('Soru: yeni adres adaylardan biriyle AYNI fiziksel yer mi?')
        lines.append('Sadece JSON yanit ver.')
        return '\n'.join(lines)
