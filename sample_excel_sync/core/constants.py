EDITABLE = ('sample_color', 'remarks', 'factory_ready_date', 'factory_comment')
READONLY = ('model', 'product_description', 'factory_model', 'factory', 'quantity')
LEGACY_READONLY = ('factory', 'model', 'factory_model', 'quantity', 'reference', 'state')
LABELS = {
    'sample_color': 'Color', 'remarks': 'Remarks',
    'factory_ready_date': 'Sample Ready Date', 'factory_comment': 'Factory Feedback',
}
COLUMNS = (
    ('factory', 'Factory'), ('model', 'Malex Model No'), ('factory_model', 'Factory Model No'),
    ('image', 'Photo'), ('product_description', 'Product Description'), ('quantity', 'Sample Qty'),
    ('sample_color', LABELS['sample_color']), ('remarks', LABELS['remarks']),
    ('remark_image', 'Remark Photo'), ('factory_ready_date', LABELS['factory_ready_date']),
    ('factory_comment', LABELS['factory_comment']), ('key', 'Record Key'),
)
V2_COLUMNS = (
    ('model', 'Malex Model'), ('image', 'Photo'), ('product_description', 'Product Description'),
    ('factory_model', 'Factory Model'), ('factory', 'Factory'), ('quantity', 'Sample Qty'),
    *((name, LABELS[name]) for name in EDITABLE), ('key', 'Record Key'),
)
SCHEMA = 'sample-excel-sync/3'
V2_SCHEMA = 'sample-excel-sync/2'
LEGACY_SCHEMA = 'sample-excel-sync/1'
LEGACY_COLUMNS = (
    ('factory', 'Factory'), ('model', 'Malex Model'), ('factory_model', 'Factory Model'),
    ('image', 'Photo'), ('quantity', 'Sample Qty'), ('sample_color', 'Color & Finish'),
    ('remarks', 'Other Sample Requirements'), ('factory_ready_date', 'Sample Ready Date'),
    ('factory_comment', 'Factory Feedback'), ('reference', 'Plug / Logo (Reference)'),
    ('state', 'Line Status'), ('key', 'Record Key'),
)
LAYOUTS = {SCHEMA: COLUMNS, V2_SCHEMA: V2_COLUMNS, LEGACY_SCHEMA: LEGACY_COLUMNS}
IMAGE_KEYS = ('image', 'remark_image')
MAX_ROWS = 2000
MAX_TEXT = 8000
MAX_FILE = 8 * 1024 * 1024
MAX_IMAGE_DATA = 16 * 1024 * 1024
MAX_EXPANDED = 48 * 1024 * 1024
