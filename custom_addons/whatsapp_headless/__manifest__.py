{
    'name': 'WhatsApp Headless MVP',
    'version': '1.0',
    'summary': 'Headless Backend for WhatsApp Chat History & CRM Integration',
    'author': 'Taufik',
    'depends': [
        'base',
        'contacts'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/wa_history_view.xml',
    ],
    'external_dependencies': {
        'python': [],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}