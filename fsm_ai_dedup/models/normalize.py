# -*- coding: utf-8 -*-
"""Deterministik normalize yardimcilari.

Hem eslestirme arama domain'inde, hem stored compute alanlarinda,
hem de KVKK uyumlu LLM prompt'unda ayni mantik kullanilir.

KVKK NOTU:
- `address_key` fonksiyonu PII icermez (isim/telefon/email yok).
- Sadece adres metni + ilce/mahalle uretir.
- LLM'e bu fonksiyonun ciktisi gonderilir.
"""


def digits_only(value):
    if not value:
        return ''
    result = ''
    for ch in str(value):
        if ch.isdigit():
            result += ch
    return result


def norm_phone(value):
    """+90 532-555 11 11 -> 5325551111
    Kural: rakam-only, son 10 hane (yoksa False).
    """
    digits = digits_only(value)
    if len(digits) >= 10:
        return digits[-10:]
    return False


def norm_vat(value):
    """TR 5205906683 -> 5205906683
    Kural: rakam-only, son 11 hane.
    """
    d = digits_only(value)
    if not d:
        return False
    if len(d) > 11:
        return d[-11:]
    return d


def norm_text(value):
    """'  ABC  Ticaret  Ltd. ' -> 'abc ticaret ltd.'
    strip + lowercase + tek bosluk.
    """
    if not value:
        return False
    s = str(value).strip().lower()
    if not s:
        return False
    return ' '.join(s.split()) or False


def norm_email(value):
    """ALI@MAIL.COM -> ali@mail.com
    Placeholder '_@00.zz' yok sayilir.
    """
    if not value:
        return False
    e = str(value).strip().lower()
    if not e or e == '_@00.zz':
        return False
    return e


def address_key(street=None, street2=None, district_name=None, town_name=None):
    """KVKK uyumlu adres anahtari.

    LLM cagrisinda kullanilan tek girdi. PII icermez (isim/telefon/email yok).
    Cikti: 'street | street2 | district | town' normalize edilmis hali.
    """
    parts = []
    for v in (street, street2, district_name, town_name):
        n = norm_text(v)
        if n:
            parts.append(n)
    return ' | '.join(parts) or ''


def address_signature(street=None, street2=None, district_id=None, town_id=None, state_id=None):
    """Cache hash anahtari icin kullanilir.

    KVKK uyumlu (sadece adres + bolge ID'leri).
    """
    parts = [
        norm_text(street) or '',
        norm_text(street2) or '',
        str(district_id or 0),
        str(town_id or 0),
        str(state_id or 0),
    ]
    return '|'.join(parts)
