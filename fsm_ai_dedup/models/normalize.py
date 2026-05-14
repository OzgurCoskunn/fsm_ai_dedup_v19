# -*- coding: utf-8 -*-
"""Deterministik normalize yardimcilari (Odoo 19 uyumlu)."""


def digits_only(value):
    if not value:
        return ''
    return ''.join(ch for ch in str(value) if ch.isdigit())


def norm_phone(value):
    digits = digits_only(value)
    return digits[-10:] if len(digits) >= 10 else False


def norm_vat(value):
    return digits_only(value) or False


def norm_email(value):
    if not value:
        return False
    e = str(value).strip().lower()
    return e if e and e != '_@00.zz' else False


def norm_text(value):
    if not value:
        return False
    return ' '.join(str(value).strip().lower().split()) or False
