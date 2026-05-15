# -*- coding: utf-8 -*-
"""fsm.api.spec uzerine partner eslestirme akisina AI hook eklenir.

YAKLASIM:
- Orijinal `_get_merchant` ve `_get_partner` yeniden yazildi (super CAGIRILMIYOR).
- Her partner uretim noktasinda once yapisal arama (parent + lokasyon)
  yapilir, candidates AI'a dogrulatilir; AI yoksa / hayir derse yeni kayit acilir.
- AI toggle kapaliysa: ilk adayi al, yoksa yarat (mevcut Odoo davranisina yakin).

KVKK:
- `partner.dedup.ai` LLM'e sadece adres metnini gonderir.
- Bu modul ona sadece `incoming_address` dict'i atar (street + district + town).
- PII (name/phone/email/vat) AI'a gonderilmez.
"""
import logging

from odoo import models, api, _
from odoo.addons.fsm_api.response import (
    Response400, Response404, Response422,
)

_logger = logging.getLogger(__name__)


class FsmApiSpecService(models.Model):
    _inherit = 'fsm.api.spec.service'

    # ------------------------------------------------------------------
    # AI HOOK -- her partner uretim noktasinda kullanilir
    # ------------------------------------------------------------------

    @api.model
    def _ai_pick_or_create(self, candidates, incoming_address,
                           create_vals, context_label):
        """Aday seti uzerinde AI dogrulamasi yap; sonuca gore karar ver.

        Args:
            candidates: res.partner recordset
            incoming_address: dict {street, district_name, town_name}
                              KVKK: PII iceremez!
            create_vals: yeni kayit gerekirse kullanilacak dict
            context_label: log icin etiket

        Returns:
            res.partner (mevcut veya yeni acilmis).
        """
        Partner = self.env['res.partner'].sudo()
        AI = self.env['partner.dedup.ai'].sudo()

        if AI.is_enabled() and candidates:
            matched = AI.verify_match(
                incoming_address=incoming_address,
                candidates=candidates,
                context_label=context_label,
            )
            if matched and matched.exists():
                matched.write(create_vals)
                return matched
            return Partner.create(create_vals)

        # AI kapali -> klasik Odoo davranisi
        if candidates:
            cand = candidates[:1]
            cand.write(create_vals)
            return cand
        return Partner.create(create_vals)

    # ------------------------------------------------------------------
    # _get_merchant - createWorkorder
    # ------------------------------------------------------------------

    def _get_merchant(self, params):
        if not params:
            raise Response404('C1404', _('Data is missing.'))

        country = self.env['res.country'].sudo().search([('code', '=', 'TR')])
        if not country:
            raise Response404('C1404', _('Country is missing.'))

        if not getattr(params, 'taxNumber', None):
            raise Response422('C1422', [{
                'field': 'taxNumber',
                'issue': _('Field is missing.'),
            }])

        Partner = self.env['res.partner'].sudo()
        proxy = self.env.context.get('proxy', {})

        value = {}
        contact_value = {}
        service_value = {}
        service_contact_value = {}
        district = None
        district_service = None
        town = None
        town_service = None

        if getattr(params, 'name', None):
            value.update({'name': params.get('name', False)})
        if getattr(params, 'tableName', None):
            value.update({'table_name': params.get('tableName', False)})
        if getattr(params, 'taxOffice', None) and 'tax_office_id' in Partner._fields:
            tax_office_name = params.get('taxOffice', '').split(' ', 1)[0]
            tax_office = self.env['account.tax.office'].sudo().search(
                [('name', 'ilike', '%s%%' % tax_office_name)], limit=1)
            if tax_office:
                value.update({'tax_office_id': tax_office.id})

        address_primary = getattr(params, 'primaryAddress', object())
        address_service = getattr(params, 'serviceAddress', None)

        # ---- BAYI value build ----
        if getattr(address_primary, 'contactName', None):
            contact_value.update({
                'is_company': False,
                'type': 'contact',
                'name': address_primary.get('contactName', False),
            })

        if getattr(address_primary, 'phoneNumber', None):
            value.update({'phone': address_primary.get('phoneNumber', False)})
        elif getattr(address_primary, 'phoneNumber1', None):
            value.update({'phone': address_primary.get('phoneNumber1', False)})
        if getattr(address_primary, 'phoneNumber2', None) and 'phone2' in Partner._fields:
            value.update({'phone2': address_primary.get('phoneNumber2', False)})
        if getattr(address_primary, 'mobileNumber', None):
            value.update({'mobile': address_primary.get('mobileNumber', False)})
        elif getattr(address_primary, 'mobile', None):
            value.update({'mobile': address_primary.get('mobile', False)})
        if getattr(address_primary, 'email', None):
            email = address_primary.get('email', False)
            if email != '_@00.zz':
                value.update({'email': email})
        if getattr(address_primary, 'mersisNumber', None):
            value.update({'company_registry': address_primary.get('mersisNumber', False)})
        if getattr(address_primary, 'tradeRegistrationNumber', None) and 'trade_reg_number' in Partner._fields:
            value.update({'trade_reg_number': address_primary.get('tradeRegistrationNumber', False)})

        if getattr(address_primary, 'city', None):
            name = address_primary.get('city', {}).get('name', 0)
            code = address_primary.get('city', {}).get('id', 0)
            codes = proxy.get('cities', {})
            code = str(code)
            if code:
                if code in codes:
                    code = codes[code]
                code = code.zfill(2)
                city = self.env['res.country.state'].sudo().search(
                    [('country_id', '=', country.id), ('code', '=', code)], limit=1)
            else:
                city = self.env['res.country.state'].sudo().search(
                    [('country_id', '=', country.id), ('name', '=', name)], limit=1)
            if not city:
                raise Response404('C1404', _('City cannot be found.'))
            elif not codes and city.name != name:
                raise Response400('C1400', _('City name is not matched.'))
            value.update({'state_id': city.id, 'country_id': country.id})

        if getattr(address_primary, 'town', None):
            name = address_primary.get('town', {}).get('name', 0)
            code = address_primary.get('town', {}).get('id', 0)
            codes = proxy.get('towns', {})
            code = str(code)
            if code:
                if code in codes:
                    code = codes[code]
                code = code.zfill(2)
                town = self.env['res.country.town'].sudo().search(
                    [('state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
            else:
                town = self.env['res.country.town'].sudo().search(
                    [('state_id.country_id', '=', country.id), ('name', '=', name)], limit=1)
            if not town:
                raise Response404('C1404', _('Town cannot be found.'))
            elif not codes and town.name != name:
                raise Response400('C1400', _('Town name is not matched.'))
            value.update({'town_id': town.id})

        if getattr(address_primary, 'district', None):
            name = address_primary.get('district', {}).get('name', 0)
            code = address_primary.get('district', {}).get('id', 0)
            if code:
                code = str(code).zfill(2)
                district = self.env['res.country.district'].sudo().search(
                    [('town_id.state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
            else:
                district = self.env['res.country.district'].sudo().search(
                    [('town_id.state_id.country_id', '=', country.id), ('name', '=', name)], limit=1)
            if not district:
                district = self.env['res.country.district'].sudo().create(
                    {'town_id': town.id, 'name': name, 'code': code})
            value.update({'district_id': district.id})

        if getattr(address_primary, 'address', None):
            value.update({'street2': address_primary.get('address', False)})
        if getattr(address_primary, 'zipCode', None):
            value.update({'zip': address_primary.get('zipCode', False)})
        if getattr(address_primary, 'latitude', None):
            value.update({'partner_latitude': address_primary.get('latitude', False)})
        if getattr(address_primary, 'longitude', None):
            value.update({'partner_longitude': address_primary.get('longitude', False)})
        if getattr(address_primary, 'uavtCode', None):
            value.update({'uavt_code': address_primary.get('uavtCode', False)})

        # ---- SERVIS ADRESI value build ----
        if getattr(address_service, 'name', None):
            service_value.update({
                'is_company': len(params.get('taxNumber', '')) == 10,
                'type': 'service',
                'name': address_service.get('name', False),
            })
        if getattr(address_service, 'tableName', None):
            service_value.update({'table_name': address_service.get('tableName', False)})
        if getattr(address_service, 'contactName', None):
            service_contact_value.update({
                'is_company': False,
                'type': 'contact',
                'name': address_service.get('contactName', False),
            })

        if getattr(address_service, 'phoneNumber', None):
            service_value.update({'phone': address_service.get('phoneNumber', False)})
        elif getattr(address_service, 'phoneNumber1', None):
            service_value.update({'phone': address_service.get('phoneNumber1', False)})
        if getattr(address_service, 'phoneNumber2', None) and 'phone2' in Partner._fields:
            service_value.update({'phone2': address_service.get('phoneNumber2', False)})
        if getattr(address_service, 'mobileNumber', None):
            service_value.update({'mobile': address_service.get('mobileNumber', False)})
        elif getattr(address_service, 'mobile', None):
            service_value.update({'mobile': address_service.get('mobile', False)})
        if getattr(address_service, 'email', None):
            email = address_service.get('email', False)
            if email != '_@00.zz':
                service_value.update({'email': email})
        if getattr(address_service, 'mersisNumber', None):
            service_value.update({'company_registry': address_service.get('mersisNumber', False)})

        if getattr(address_service, 'city', None):
            name = address_service.get('city', {}).get('name', 0)
            code = address_service.get('city', {}).get('id', 0)
            codes = proxy.get('cities', {})
            code = str(code)
            if code:
                if code in codes:
                    code = codes[code]
                code = code.zfill(2)
                city_s = self.env['res.country.state'].sudo().search(
                    [('country_id', '=', country.id), ('code', '=', code)], limit=1)
            else:
                city_s = self.env['res.country.state'].sudo().search(
                    [('country_id', '=', country.id), ('name', '=', name)], limit=1)
            if not city_s:
                raise Response404('C1404', _('City cannot be found.'))
            elif not codes and city_s.name != name:
                raise Response400('C1400', _('City name is not matched.'))
            service_value.update({'state_id': city_s.id, 'country_id': country.id})

        if getattr(address_service, 'town', None):
            name = address_service.get('town', {}).get('name', 0)
            code = address_service.get('town', {}).get('id', 0)
            codes = proxy.get('towns', {})
            code = str(code)
            if code:
                if code in codes:
                    code = codes[code]
                code = code.zfill(2)
                town_service = self.env['res.country.town'].sudo().search(
                    [('state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
            else:
                town_service = self.env['res.country.town'].sudo().search(
                    [('state_id.country_id', '=', country.id), ('name', '=', name)], limit=1)
            if not town_service:
                raise Response404('C1404', _('Town cannot be found.'))
            elif not codes and town_service.name != name:
                raise Response400('C1400', _('Town name is not matched.'))
            service_value.update({'town_id': town_service.id})

        if getattr(address_service, 'district', None):
            name = address_service.get('district', {}).get('name', 0)
            code = address_service.get('district', {}).get('id', 0)
            if code:
                code = str(code).zfill(2)
                district_service = self.env['res.country.district'].sudo().search(
                    [('town_id.state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
            else:
                district_service = self.env['res.country.district'].sudo().search(
                    [('town_id.state_id.country_id', '=', country.id), ('name', '=', name)], limit=1)
            if not district_service:
                district_service = self.env['res.country.district'].sudo().create(
                    {'town_id': town_service.id, 'name': name, 'code': code})
            service_value.update({'district_id': district_service.id})

        if getattr(address_service, 'address', None):
            service_value.update({'street2': address_service.get('address', False)})
        if getattr(address_service, 'zipCode', None):
            service_value.update({'zip': address_service.get('zipCode', False)})
        if getattr(address_service, 'latitude', None):
            service_value.update({'partner_latitude': address_service.get('latitude', False)})
        if getattr(address_service, 'longitude', None):
            service_value.update({'partner_longitude': address_service.get('longitude', False)})
        if getattr(address_service, 'uavtCode', None):
            service_value.update({'uavt_code': address_service.get('uavtCode', False)})

        # ==================================================================
        # BAYI (ana parent) - vat ile arama
        # ==================================================================
        tax_number = params.get('taxNumber', False)
        partner = tax_number and Partner.search(
            [('vat', 'like', '%%%s' % tax_number)], limit=1)
        if partner:
            partner.write(value)
        else:
            value.update({
                'is_company': len(tax_number) == 10 if tax_number else False,
                'vat': tax_number,
            })
            partner = Partner.create(value)

        # ==================================================================
        # BAYI KONTAGI - sadece isim eslesmesi
        # ==================================================================
        if contact_value:
            cand_c = Partner.search([
                ('type', '=', 'contact'),
                ('is_company', '=', False),
                ('parent_id', '=', partner.id),
                ('name', '=', contact_value['name']),
            ])
            if cand_c:
                cand_c[:1].write(contact_value)
            else:
                contact_value['parent_id'] = partner.id
                Partner.create(contact_value)

        # ==================================================================
        # SERVIS ADRESI - YAPISAL ARAMA + AI HOOK
        # ==================================================================
        service_partner = partner
        if service_value:
            search_domain = [
                ('parent_id', '=', partner.id),
                ('type', '=', 'service'),
            ]
            if service_value.get('state_id'):
                search_domain.append(('state_id', '=', service_value['state_id']))
            if service_value.get('town_id'):
                search_domain.append(('town_id', '=', service_value['town_id']))
            if service_value.get('district_id'):
                search_domain.append(('district_id', '=', service_value['district_id']))
            candidates = Partner.search(search_domain)

            service_value.setdefault('parent_id', partner.id)
            service_partner = self._ai_pick_or_create(
                candidates=candidates,
                incoming_address={
                    'street': service_value.get('street2', '') or '',
                    'district_name': district_service.name if district_service else '',
                    'town_name': town_service.name if town_service else '',
                },
                create_vals=service_value,
                context_label='createWorkorder/service',
            )

            # ==================================================================
            # SERVIS ADRESI KONTAGI - sadece isim eslesmesi
            # ==================================================================
            if service_contact_value:
                cand_sc = Partner.search([
                    ('type', '=', 'contact'),
                    ('is_company', '=', False),
                    ('parent_id', '=', service_partner.id),
                    ('name', '=', service_contact_value['name']),
                ])
                if cand_sc:
                    cand_sc[:1].write(service_contact_value)
                else:
                    service_contact_value['parent_id'] = service_partner.id
                    Partner.create(service_contact_value)

        return partner, service_partner

    # ------------------------------------------------------------------
    # _get_partner - createSaleOrder / approveSaleOrder
    # ------------------------------------------------------------------

    def _get_partner(self, params):
        if not params:
            raise Response404('C1404', _('Data is missing.'))

        country = self.env['res.country'].sudo().search([('code', '=', 'TR')])
        if not country:
            raise Response404('C1404', _('Country is missing.'))

        Partner = self.env['res.partner'].sudo()

        value = {}
        value_invoice = {}
        value_shipping = {}
        district_invoice = None
        district_shipping = None
        town_invoice = None
        town_shipping = None

        if getattr(params, 'isCompany', None):
            value.update({'is_company': params.get('isCompany', False)})
        if getattr(params, 'name', None):
            value.update({'name': params.get('name', False)})
        if getattr(params, 'tableName', None):
            value.update({'table_name': params.get('tableName', False)})
        if getattr(params, 'taxNumber', None):
            value.update({'vat': params.get('taxNumber', False)})
        if getattr(params, 'taxOffice', None) and 'tax_office_id' in Partner._fields:
            tax_office_name = params.get('taxOffice', '').split(' ', 1)[0]
            tax_office = self.env['account.tax.office'].sudo().search(
                [('name', 'ilike', '%s%%' % tax_office_name)], limit=1)
            if tax_office:
                value.update({'tax_office_id': tax_office.id})

        address_invoice = getattr(params, 'billingAddress', None)
        address_delivery = getattr(params, 'shippingAddress', None)

        # Fatura adresi
        if address_invoice:
            if getattr(address_invoice, 'contactName', None):
                value_invoice.update({'name': address_invoice.get('contactName', False)})
            if getattr(address_invoice, 'identityNumber', None):
                value_invoice.update({'vat': address_invoice.get('identityNumber', False)})
            if getattr(address_invoice, 'phoneNumber', None):
                value_invoice.update({'phone': address_invoice.get('phoneNumber', False)})
            if getattr(address_invoice, 'mobile', None):
                value_invoice.update({'mobile': address_invoice.get('mobile', False)})
            if getattr(address_invoice, 'email', None):
                email = address_invoice.get('email', False)
                if email != '_@00.zz':
                    value_invoice.update({'email': email})
            if getattr(address_invoice, 'mersisNumber', None):
                value_invoice.update({'company_registry': address_invoice.get('mersisNumber', False)})
            if getattr(address_invoice, 'tradeRegistrationNumber', None) and 'trade_reg_number' in Partner._fields:
                value_invoice.update({'trade_reg_number': address_invoice.get('tradeRegistrationNumber', False)})
            if getattr(address_invoice, 'city', None):
                name = address_invoice.get('city', {}).get('name', 0)
                code = str(address_invoice.get('city', {}).get('id', 0)).zfill(2)
                city = self.env['res.country.state'].sudo().search(
                    [('country_id', '=', country.id), ('code', '=', code)], limit=1)
                if not city:
                    raise Response404('C1404', _('City cannot be found.'))
                elif city.name != name:
                    raise Response400('C1400', _('City name is not matched.'))
                value_invoice.update({'state_id': city.id, 'country_id': country.id})
            if getattr(address_invoice, 'town', None):
                name = address_invoice.get('town', {}).get('name', 0)
                code = str(address_invoice.get('town', {}).get('id', 0))
                town_invoice = self.env['res.country.town'].sudo().search(
                    [('state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
                if not town_invoice:
                    raise Response404('C1404', _('Town cannot be found.'))
                elif town_invoice.name != name:
                    raise Response400('C1400', _('Town name is not matched.'))
                value_invoice.update({'town_id': town_invoice.id})
            if getattr(address_invoice, 'district', None):
                name = address_invoice.get('district', {}).get('name', 0)
                code = str(address_invoice.get('district', {}).get('id', 0))
                district_invoice = self.env['res.country.district'].sudo().search(
                    [('town_id.state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
                if not district_invoice:
                    district_invoice = self.env['res.country.district'].sudo().create(
                        {'town_id': town_invoice.id, 'name': name, 'code': code})
                value_invoice.update({'district_id': district_invoice.id})
            if getattr(address_invoice, 'address', None):
                value_invoice.update({'street2': address_invoice.get('address', False)})
            if getattr(address_invoice, 'zipCode', None):
                value_invoice.update({'zip': address_invoice.get('zipCode', False)})
            if getattr(address_invoice, 'latitude', None):
                value_invoice.update({'partner_latitude': address_invoice.get('latitude', False)})
            if getattr(address_invoice, 'longitude', None):
                value_invoice.update({'partner_longitude': address_invoice.get('longitude', False)})
            if getattr(address_invoice, 'uavtCode', None):
                value_invoice.update({'uavt_code': address_invoice.get('uavtCode', False)})

        # Sevk adresi
        if address_delivery:
            if getattr(address_delivery, 'contactName', None):
                value_shipping.update({'name': address_delivery.get('contactName', False)})
            if getattr(address_delivery, 'identityNumber', None):
                value_shipping.update({'vat': address_delivery.get('identityNumber', False)})
            if getattr(address_delivery, 'phoneNumber', None):
                value_shipping.update({'phone': address_delivery.get('phoneNumber', False)})
            if getattr(address_delivery, 'mobile', None):
                value_shipping.update({'mobile': address_delivery.get('mobile', False)})
            if getattr(address_delivery, 'email', None):
                email = address_delivery.get('email', False)
                if email != '_@00.zz':
                    value_shipping.update({'email': email})
            if getattr(address_delivery, 'mersisNumber', None):
                value_shipping.update({'company_registry': address_delivery.get('mersisNumber', False)})
            if getattr(address_delivery, 'tradeRegistrationNumber', None) and 'trade_reg_number' in Partner._fields:
                value_shipping.update({'trade_reg_number': address_delivery.get('tradeRegistrationNumber', False)})
            if getattr(address_delivery, 'city', None):
                name = address_delivery.get('city', {}).get('name', 0)
                code = str(address_delivery.get('city', {}).get('id', 0)).zfill(2)
                city = self.env['res.country.state'].sudo().search(
                    [('country_id', '=', country.id), ('code', '=', code)], limit=1)
                if not city:
                    raise Response404('C1404', _('City cannot be found.'))
                elif city.name != name:
                    raise Response400('C1400', _('City name is not matched.'))
                value_shipping.update({'state_id': city.id, 'country_id': country.id})
            if getattr(address_delivery, 'town', None):
                name = address_delivery.get('town', {}).get('name', 0)
                code = str(address_delivery.get('town', {}).get('id', 0))
                town_shipping = self.env['res.country.town'].sudo().search(
                    [('state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
                if not town_shipping:
                    raise Response404('C1404', _('Town cannot be found.'))
                elif town_shipping.name != name:
                    raise Response400('C1400', _('Town name is not matched.'))
                value_shipping.update({'town_id': town_shipping.id})
            if getattr(address_delivery, 'district', None):
                name = address_delivery.get('district', {}).get('name', 0)
                code = str(address_delivery.get('district', {}).get('id', 0))
                district_shipping = self.env['res.country.district'].sudo().search(
                    [('town_id.state_id.country_id', '=', country.id), ('code', '=', code)], limit=1)
                if not district_shipping:
                    district_shipping = self.env['res.country.district'].sudo().create(
                        {'town_id': town_shipping.id, 'name': name, 'code': code})
                value_shipping.update({'district_id': district_shipping.id})
            if getattr(address_delivery, 'address', None):
                value_shipping.update({'street2': address_delivery.get('address', False)})
            if getattr(address_delivery, 'zipCode', None):
                value_shipping.update({'zip': address_delivery.get('zipCode', False)})
            if getattr(address_delivery, 'latitude', None):
                value_shipping.update({'partner_latitude': address_delivery.get('latitude', False)})
            if getattr(address_delivery, 'longitude', None):
                value_shipping.update({'partner_longitude': address_delivery.get('longitude', False)})
            if getattr(address_delivery, 'uavtCode', None):
                value_shipping.update({'uavt_code': address_delivery.get('uavtCode', False)})

        # ==================================================================
        # ANA MUSTERI - vat ile arama
        # ==================================================================
        tax_number = getattr(params, 'taxNumber', None)
        partner = tax_number and Partner.search(
            [('vat', 'like', '%%%s' % tax_number)], limit=1)
        if not partner:
            if tax_number:
                value.update({'vat': tax_number})
            partner = Partner.create(value)
        else:
            partner.write(value)

        # ==================================================================
        # FATURA ADRESI - YAPISAL ARAMA + AI HOOK
        # ==================================================================
        partner_invoice = None
        if value_invoice:
            search_domain = [
                ('parent_id', '=', partner.id),
                ('type', '=', 'invoice'),
            ]
            if value_invoice.get('state_id'):
                search_domain.append(('state_id', '=', value_invoice['state_id']))
            if value_invoice.get('town_id'):
                search_domain.append(('town_id', '=', value_invoice['town_id']))
            if value_invoice.get('district_id'):
                search_domain.append(('district_id', '=', value_invoice['district_id']))
            candidates = Partner.search(search_domain)

            value_invoice['parent_id'] = partner.id
            value_invoice['type'] = 'invoice'
            partner_invoice = self._ai_pick_or_create(
                candidates=candidates,
                incoming_address={
                    'street': value_invoice.get('street2', '') or '',
                    'district_name': district_invoice.name if district_invoice else '',
                    'town_name': town_invoice.name if town_invoice else '',
                },
                create_vals=value_invoice,
                context_label='%s/invoice' % (self.code or 'saleorder'),
            )

        # ==================================================================
        # SEVK ADRESI - YAPISAL ARAMA + AI HOOK
        # ==================================================================
        partner_shipping = None
        if value_shipping:
            search_domain = [
                ('parent_id', '=', partner.id),
                ('type', '=', 'delivery'),
            ]
            if value_shipping.get('state_id'):
                search_domain.append(('state_id', '=', value_shipping['state_id']))
            if value_shipping.get('town_id'):
                search_domain.append(('town_id', '=', value_shipping['town_id']))
            if value_shipping.get('district_id'):
                search_domain.append(('district_id', '=', value_shipping['district_id']))
            candidates = Partner.search(search_domain)

            value_shipping['parent_id'] = partner.id
            value_shipping['type'] = 'delivery'
            partner_shipping = self._ai_pick_or_create(
                candidates=candidates,
                incoming_address={
                    'street': value_shipping.get('street2', '') or '',
                    'district_name': district_shipping.name if district_shipping else '',
                    'town_name': town_shipping.name if town_shipping else '',
                },
                create_vals=value_shipping,
                context_label='%s/delivery' % (self.code or 'saleorder'),
            )

        return partner, partner_invoice, partner_shipping
