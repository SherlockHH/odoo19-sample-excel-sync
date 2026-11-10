{
    'name': 'Sample Excel Export & Update',
    'summary': 'Export sample lines and preview four-field Excel updates',
    'version': '19.0.1.2.0',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'depends': ['sample_management_mlx', 'project', 'mail'],
    'external_dependencies': {'python': ['xlsxwriter', 'openpyxl', 'PIL', 'defusedxml']},
    'data': ['security/ir.model.access.csv', 'views/wizard_views.xml',
             'views/sample_request_views.xml'],
    'installable': True,
    'application': False,
}
