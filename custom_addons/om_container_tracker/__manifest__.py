{
    'name': 'Container Tracker Integration',
    'version': '1.0',
    'summary': 'Track Container Position via TimeToCargo API',
    'author': 'Taufik Hidayat',
    'depends': ['stock', 'website', 'sale'], # Kita butuh modul stock (inventory)
    'data': [
        'security/ir.model.access.csv',
        'data/container.tracking.status.csv',
        'views/tracking_status_views.xml',
        'views/sale_order_views.xml',
        'views/tracking_template.xml',
    ],
    'installable': True,
    'application': False,
}