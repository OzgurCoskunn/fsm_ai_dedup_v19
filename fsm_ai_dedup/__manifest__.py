{
    'name': 'FSM AI Dedup (v19)',
    'version': '19.0.2.0.0',
    'category': 'Tools',
    'summary': 'Partner duplikasyon engelleme - LLM adres karsilastirma (Odoo 19)',
    'description': (
        'fsm_api endpointleri (createWorkorder / createSaleOrder / approveSaleOrder) '
        'partner uretirken once yapisal arama yapilir, bulunan adaylar OpenRouter '
        'uzerinden bir LLM ile adres karsilastirmasi yapilarak dogrulanir. '
        'Toggle ile aciilip kapatilabilir. KVKK: LLM yalniz adres metnini gorur.'
    ),
    'depends': ['base', 'base_setup', 'contacts', 'fsm_api'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/res_config_settings_views.xml',
        'views/partner_dedup_log_views.xml',
    ],
    'external_dependencies': {'python': ['requests']},
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
