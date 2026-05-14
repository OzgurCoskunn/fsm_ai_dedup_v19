# -*- coding: utf-8 -*-
"""fsm.api.spec uzerine partner eslestirme akisini normalize + AI ile gevseten override.

Strateji:
- Mevcut `_get_merchant` ve `_get_partner` fonksiyonlarinin partner arama
  bloklarini "akilli" hale getirir.
- Once normalize (telefon/vat/email/text) ile arar, bulamazsa AI fallback'i tetikler.
- Karari `ai.dedup.log` modeline yazar (Postman'den test ederken takip icin).
"""
import json
import logging

from odoo import models, api, _

from .normalize import norm_phone, norm_vat, norm_email, norm_text

_logger = logging.getLogger(__name__)


class FsmApiSpec(models.Model):
    _inherit = 'fsm.api.spec'

    # ------------------------------------------------------------------
    # AI dedup helper
    # ------------------------------------------------------------------

    @api.model
    def _ai_dedup_search(self, parent, partner_type, new_vals, district_id=None,
                         town_id=None, endpoint=None):
        """Hibrit arama: once normalize, bulunamazsa AI fallback.

        Args:
            parent: res.partner (ust kayit) — kontak/adres aranacak parent
            partner_type: 'contact' | 'service' | 'invoice' | 'delivery'
            new_vals: gelen API payload'undan turetilmis dict
                      (name, phone, mobile, email, street/street2, vat,
                       district_id, town_id, district_name, town_name)
            district_id: opsiyonel filtre
            town_id: opsiyonel filtre
            endpoint: log icin (createWorkorder vs.)

        Returns:
            (recordset | empty recordset, decision_str, reason_str)
        """
        Partner = self.env['res.partner'].sudo()
        Log = self.env['ai.dedup.log'].sudo()

        # 0) Aday havuzunu daralt: parent + tip + (varsa) ilce
        base_domain = [
            ('parent_id', '=', parent.id),
            ('type', '=', partner_type),
        ]
        if partner_type == 'contact':
            base_domain.append(('is_company', '=', False))

        candidates = Partner.search(base_domain)
        district_candidates = candidates
        if district_id:
            district_candidates = candidates.filtered(lambda p: p.district_id.id == district_id)

        # 1) NORMALIZE ESLESMESI
        norm_p = norm_phone(new_vals.get('mobile')) or norm_phone(new_vals.get('phone'))
        norm_e = norm_email(new_vals.get('email'))
        norm_n = norm_text(new_vals.get('name'))
        norm_v = norm_vat(new_vals.get('vat'))

        matched = Partner.browse()
        if district_candidates:
            for p in district_candidates:
                pp = norm_phone(p.mobile) or norm_phone(p.phone)
                ee = norm_email(p.email)
                nn = norm_text(p.name)
                vv = norm_vat(p.vat)
                if norm_p and pp and pp == norm_p:
                    matched = p
                    break
                if norm_e and ee and ee == norm_e:
                    matched = p
                    break
                if norm_v and vv and vv == norm_v:
                    matched = p
                    break
                if norm_n and nn and nn == norm_n:
                    matched = p
                    break

        if matched:
            Log.create({
                'endpoint': endpoint,
                'partner_type': partner_type,
                'parent_id': parent.id,
                'candidate_ids': [(6, 0, district_candidates.ids)],
                'matched_id': matched.id,
                'confidence': 100,
                'threshold': 0,
                'decision': 'normalize_match',
                'reason': 'Normalize eslesmesi bulundu',
                'input_payload': json.dumps({k: v for k, v in new_vals.items() if k != 'parent_id'},
                                            ensure_ascii=False, default=str),
            })
            return matched, 'normalize_match', 'Normalize ile bulundu'

        # 2) AI FALLBACK — yalnizca etkinse
        openrouter = self.env['openrouter.service'].sudo()
        if not openrouter.is_enabled():
            Log.create({
                'endpoint': endpoint,
                'partner_type': partner_type,
                'parent_id': parent.id,
                'candidate_ids': [(6, 0, district_candidates.ids)],
                'decision': 'ai_disabled',
                'reason': 'AI fallback kapali / api key yok',
                'input_payload': json.dumps({k: v for k, v in new_vals.items() if k != 'parent_id'},
                                            ensure_ascii=False, default=str),
            })
            return Partner.browse(), 'ai_disabled', 'AI kapali'

        if not district_candidates:
            Log.create({
                'endpoint': endpoint,
                'partner_type': partner_type,
                'parent_id': parent.id,
                'decision': 'ai_skipped_no_candidates',
                'reason': 'Aynı parent+ilçede aday yok',
                'input_payload': json.dumps({k: v for k, v in new_vals.items() if k != 'parent_id'},
                                            ensure_ascii=False, default=str),
            })
            return Partner.browse(), 'ai_skipped_no_candidates', 'Aday yok'

        cfg = openrouter._get_config()
        result = self.env['partner.ai.matcher'].sudo().find_match(new_vals, district_candidates)

        tokens = result.get('tokens') or {}
        log_vals = {
            'endpoint': endpoint,
            'partner_type': partner_type,
            'parent_id': parent.id,
            'candidate_ids': [(6, 0, district_candidates.ids)],
            'matched_id': result['matched'].id if result['matched'] else False,
            'confidence': result['confidence'],
            'threshold': cfg['confidence_threshold'],
            'reason': result['reason'],
            'model_used': result.get('model_used'),
            'tokens_in': tokens.get('prompt_tokens', 0),
            'tokens_out': tokens.get('completion_tokens', 0),
            'input_payload': json.dumps({k: v for k, v in new_vals.items() if k != 'parent_id'},
                                        ensure_ascii=False, default=str),
            'raw_response': result.get('raw'),
        }

        if result['matched'] and result['confidence'] >= cfg['confidence_threshold']:
            log_vals['decision'] = 'ai_match'
            Log.create(log_vals)
            return result['matched'], 'ai_match', result['reason']

        if result['matched']:
            log_vals['decision'] = 'ai_low_confidence'
            Log.create(log_vals)
            return Partner.browse(), 'ai_low_confidence', (
                'AI eslesti ama %s%% < esik %s%%' % (
                    result['confidence'], cfg['confidence_threshold'],
                )
            )

        log_vals['decision'] = 'ai_no_match'
        Log.create(log_vals)
        return Partner.browse(), 'ai_no_match', result['reason']

    # ------------------------------------------------------------------
    # _get_merchant override
    # ------------------------------------------------------------------

    def _get_merchant(self, params):
        """createWorkorder akisinda bayi + kontak + servis adresi + servis kontagi.

        Orijinal mantik korunur, sadece arama bloklarinda normalize+AI fallback eklenir.
        Bunu yapmak icin orijinal metodu super ile cagirmak yerine, sadece 4 arama
        noktasinda araya girip 'mevcut kayit var mi?' karari verecek sekilde
        davraniisi degistiriyoruz.
        """
        # Orijinal mantigi calistir; sonra DB durumunu inceleyerek eksikleri
        # AI ile birlestir.
        partner, service_partner = super(FsmApiSpec, self)._get_merchant(params)

        endpoint = 'createWorkorder'

        # AI fallback yalnizca etkinse — orijinal kayitlari "post-process" et
        if not self.env['openrouter.service'].sudo().is_enabled():
            return partner, service_partner

        # Bayi kontagi: super zaten yarattiysa ya da bulduysa is yok. Ama
        # 11-alan katiligi yuzunden cikan duplikatlar varsa burada konsolide ederiz.
        # Bu kapsamda detayli logic icin alttaki helper'lar kullanilir.
        # Bayinin altinda ayni telefonlu/isimli baska bir contact varsa, super'in
        # yarattigi yeni kontak duplikat olabilir; bunu AI ile dogrula.
        try:
            self._post_merge_with_ai(partner, endpoint=endpoint)
            if service_partner and service_partner != partner:
                self._post_merge_with_ai(service_partner, endpoint=endpoint)
        except Exception as e:
            _logger.exception("AI post-merge error: %s", e)

        return partner, service_partner

    # ------------------------------------------------------------------
    # _get_partner override
    # ------------------------------------------------------------------

    def _get_partner(self, params):
        """createSaleOrder / approveSaleOrder akisinda musteri + fatura + sevk."""
        partner, partner_invoice, partner_shipping = super(FsmApiSpec, self)._get_partner(params)

        endpoint = self.code if self.code in ('createSaleOrder', 'approveSaleOrder') else 'getPartner'

        if not self.env['openrouter.service'].sudo().is_enabled():
            return partner, partner_invoice, partner_shipping

        try:
            self._post_merge_with_ai(partner, endpoint=endpoint)
        except Exception as e:
            _logger.exception("AI post-merge error: %s", e)

        return partner, partner_invoice, partner_shipping

    # ------------------------------------------------------------------
    # Post-merge: super tarafindan yeni acilan alt kayit duplike mi diye
    # AI'ya sor; oyleyse merge et.
    # ------------------------------------------------------------------

    def _post_merge_with_ai(self, parent, endpoint=None):
        """Parent altinda olusturulmus tum alt kayitlari aday havuzu olarak alir.
        Son olusturulan alt kaydi AI ile diger adaylara karsi karsilastirir.
        Eslesme bulursa Odoo'nun standart merge wizard'i ile birlestirir.
        """
        if not parent or not parent.exists():
            return
        Partner = self.env['res.partner'].sudo()
        MergeWizard = self.env['base.partner.merge.automatic.wizard'].sudo()

        for ptype in ('contact', 'service', 'invoice', 'delivery'):
            domain = [
                ('parent_id', '=', parent.id),
                ('type', '=', ptype),
            ]
            if ptype == 'contact':
                domain.append(('is_company', '=', False))

            siblings = Partner.search(domain, order='create_date desc')
            if len(siblings) < 2:
                continue

            newest = siblings[0]
            older = siblings[1:]
            if not older:
                continue

            new_vals = {
                'name': newest.name,
                'street': newest.street,
                'street2': newest.street2,
                'mobile': newest.mobile,
                'phone': newest.phone,
                'email': newest.email,
                'vat': newest.vat,
                'district_id': newest.district_id.id,
                'town_id': newest.town_id.id,
                'district_name': newest.district_id.name,
                'town_name': newest.town_id.name,
            }

            matched, decision, reason = self._ai_dedup_search(
                parent=parent,
                partner_type=ptype,
                new_vals=new_vals,
                district_id=newest.district_id.id,
                town_id=newest.town_id.id,
                endpoint=endpoint,
            )

            # Yeni olusturulanin kendisiyle eslememesi icin filtrele
            if matched and matched.id == newest.id:
                continue

            if matched and matched.exists():
                try:
                    MergeWizard._merge((newest + matched).ids, matched)
                    _logger.info(
                        "AI MERGE: kept=%s removed_new=%s decision=%s reason=%s",
                        matched.id, newest.id, decision, reason,
                    )
                except Exception as e:
                    _logger.exception(
                        "Merge failed kept=%s new=%s: %s",
                        matched.id, newest.id, e,
                    )
