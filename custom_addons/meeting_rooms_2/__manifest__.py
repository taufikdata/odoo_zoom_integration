{
    'name': "Meeting System ROOM TZ",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'tag': """
        Long tag of module's purpose
    """,

    'author': "Alam",
    'website': "https://www.alamkamajana.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'calendar', 'mail', 'contacts', 'website'],

    'external_dependencies': {
        'python': ['requests', 'pytz', 'urllib3'],
    },

    # always loaded
    'data': [
        'security/meeting_security.xml',
        'security/ir.model.access.csv',
        'views/view.xml',
        'views/virtual_room.xml',
        'views/meeting_event_view.xml',
        'views/booking_link_view.xml',
        'views/meeting_rooms_ext_view.xml',
        'static/src/html/index.xml',
        # 'data/data_sync.xml',
        'data/cron_job.xml',
        'views/portal_templates.xml',
    ],

}
