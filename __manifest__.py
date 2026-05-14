{
    'name': 'FSM AI Dedup (v19)',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Partner duplikasyon engelleme - OpenRouter AI ile adres eslestirme (Odoo 19)',
    'description': (
        'OpenRouter uzerinden LLM ile partner/adres karsilastirma yapan modul. '
        'Settings ekraninda API key + model + threshold tanimlanir; "AI Dedup" '
        'menusunden manuel test wizardi ile bir partneri mevcut adaylarla '
        'karsilastirir. fsm_api modulu kuruluysa ek olarak `_get_partner` ve '
        '`_get_merchant` akislarinda otomatik fallback yapilir (opsiyonel).'
    ),
    'depends': ['base', 'base_setup', 'contacts', 'fsm_api'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/res_config_settings_views.xml',
        'views/ai_dedup_log_views.xml',
        'wizards/ai_dedup_test_wizard_views.xml',
    ],
    'external_dependencies': {'python': ['requests']},
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
