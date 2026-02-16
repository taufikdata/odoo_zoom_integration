{
    'name': 'Container Tracker Integration',
    'version': '1.0',
    'summary': 'Track Container Position via TimeToCargo API',
    'author': 'Taufik Hidayat',
    'depends': ['stock', 'website', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/api_credentials.xml',
        'data/container.tracking.status.csv',
        'views/tracking_status_views.xml',
        # 'views/sale_order_views.xml',
        'views/tracking_template.xml',
        'views/audit_views.xml',
    ],
    'installable': True,
    'application': False,
}