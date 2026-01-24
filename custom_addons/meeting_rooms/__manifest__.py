{
    'name': "Meeting Rooms",

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
    'depends': ['base', 'calendar', 'mail', 'contacts'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/view.xml',
        'static/src/html/index.xml',
    ],

}
