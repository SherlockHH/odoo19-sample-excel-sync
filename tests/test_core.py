import importlib.util
import io
import sys
import unittest
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook, load_workbook
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Load the pure package without importing the Odoo add-on entry point.
spec = importlib.util.spec_from_file_location(
    'sync_core', ROOT / 'sample_excel_sync/core/__init__.py',
    submodule_search_locations=[str(ROOT / 'sample_excel_sync/core')],
)
core = importlib.util.module_from_spec(spec)
sys.modules['sync_core'] = core
spec.loader.exec_module(core)
from sync_core.comparison import compare_rows, resolve_changes
from sync_core.workbook import build_workbook, parse_workbook


def sample(key='opaque-row-one', **changes):
    row = dict(key=key, factory='Demo Factory', model='DEMO-001',
               factory_model='FM-001', quantity=2, sample_color='Silver',
               remarks='Chrome handle', factory_ready_date='2026-11-14',
               factory_comment='', product_description='500 W blender with glass jar')
    row.update(changes)
    return row


def edited_file(raw, edit):
    book = load_workbook(io.BytesIO(raw))
    edit(book)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class ComparisonTests(unittest.TestCase):
    def test_only_changed_field_is_proposed(self):
        base = sample()
        current = sample(sample_color='Matt Black')
        incoming = sample(factory_ready_date='2026-11-18')
        changes = compare_rows([base], [current], [incoming])
        self.assertEqual([(c['field'], c['kind']) for c in changes],
                         [('factory_ready_date', 'update')])

    def test_true_conflict_requires_a_choice(self):
        changes = compare_rows([sample()], [sample(sample_color='Black')],
                               [sample(sample_color='White')])
        self.assertEqual(changes[0]['kind'], 'conflict')
        with self.assertRaises(ValueError):
            resolve_changes(changes, {})
        self.assertEqual(resolve_changes(changes, {changes[0]['id']: 'apply'}),
                         {'opaque-row-one': {'sample_color': 'White'}})

    def test_clear_ignored_unless_explicit(self):
        changes = compare_rows([sample()], [sample()], [sample(remarks='')])
        self.assertEqual(changes[0]['kind'], 'clear')
        self.assertEqual(resolve_changes(changes, {}), {})
        self.assertEqual(resolve_changes(changes, {changes[0]['id']: 'apply'}),
                         {'opaque-row-one': {'remarks': ''}})

    def test_repeated_import_is_noop(self):
        incoming = sample(factory_comment='Ready')
        self.assertEqual(compare_rows([sample()], [incoming], [incoming]), [])

    def test_missing_row_is_not_a_deletion(self):
        self.assertEqual(compare_rows([sample()], [sample()], []), [])

    def test_duplicate_and_foreign_keys_rejected(self):
        for rows in [[sample(), sample()], [sample(key='foreign')]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                compare_rows([sample()], [sample()], rows)

    def test_readonly_column_change_rejected(self):
        with self.assertRaises(ValueError):
            compare_rows([sample()], [sample()], [sample(model='OTHER')])

    def test_unknown_decision_rejected(self):
        with self.assertRaises(ValueError):
            resolve_changes([], {'forged': 'apply'})

    def test_cancelled_changed_row_rejected(self):
        base = sample(state='Cancelled')
        with self.assertRaises(ValueError):
            compare_rows([base], [base], [sample(state='Cancelled', remarks='x')])

    def test_empty_model_and_quantity_are_valid(self):
        row = sample(model='', quantity='')
        self.assertEqual(len(compare_rows([row], [row],
                                         [dict(row, factory_comment='Ready')])), 1)

    def test_excel_line_ending_normalization_is_not_a_change(self):
        base = sample(factory_comment='Line one\r\nLine two', factory='Demo\r\nFactory')
        incoming = sample(factory_comment='Line one\nLine two', factory='Demo\nFactory')
        self.assertEqual(compare_rows([base], [base], [incoming]), [])


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.rows = [sample(), sample(key='opaque-two', model='DEMO-002')]
        self.raw = build_workbook('SMP-DEMO', 'opaque-export', self.rows)

    def test_roundtrip_preserves_editable_and_identity_values(self):
        token, rows = parse_workbook(self.raw)
        self.assertEqual(token, 'opaque-export')
        self.assertEqual(rows, self.rows)

    def test_date_edit_roundtrip(self):
        raw = edited_file(self.raw, lambda w: setattr(w['Samples']['I5'], 'value',
                                                    date(2026, 11, 18)))
        self.assertEqual(parse_workbook(raw)[1][0]['factory_ready_date'], '2026-11-18')

    def test_empty_fields_are_true_blank_cells(self):
        raw = build_workbook('SMP-DEMO', 'export', [sample(sample_color='', factory_model='')])
        book = load_workbook(io.BytesIO(raw))
        for address in ('D5', 'G5', 'J5'):
            with self.subTest(address=address):
                self.assertIsNone(book['Samples'][address].value)

    def test_whole_row_sort_keeps_identity(self):
        def edit(book):
            sheet = book['Samples']
            first = [c.value for c in sheet[5]]
            second = [c.value for c in sheet[6]]
            for col, value in enumerate(second, 1):
                sheet.cell(5, col, value)
            for col, value in enumerate(first, 1):
                sheet.cell(6, col, value)
        _, rows = parse_workbook(edited_file(self.raw, edit))
        self.assertEqual([r['key'] for r in rows], ['opaque-two', 'opaque-row-one'])

    def test_formula_like_feedback_exported_as_literal_text(self):
        for text in ['=HYPERLINK("https://invalid.example","x")', '+SUM(1,1)',
                     '@SUM(1,1)', '-1+2']:
            raw = build_workbook('SMP-DEMO', 'export', [sample(factory_comment=text)])
            w = load_workbook(io.BytesIO(raw))
            self.assertEqual(w['Samples']['J5'].data_type, 's')
            self.assertEqual(parse_workbook(raw)[1][0]['factory_comment'], text)

    def test_incoming_formula_is_rejected(self):
        raw = edited_file(self.raw, lambda w: setattr(w['Samples']['J5'], 'value', '=1+1'))
        with self.assertRaises(ValueError):
            parse_workbook(raw)

    def test_invalid_dates_are_not_silently_interpreted(self):
        for value in ['TBC', '18/11/2026', 46335, '2026-02-30', 0, False]:
            def edit(book):
                book['Samples']['I5'] = value
                book['Samples']['I5'].number_format = 'General'
            raw = edited_file(self.raw, edit)
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_workbook(raw)

    def test_table_includes_hidden_row_key(self):
        w = load_workbook(io.BytesIO(self.raw))
        self.assertEqual(w['Samples'].tables['SampleLines'].ref, 'A4:K6')
        self.assertTrue(w['Samples'].column_dimensions['K'].hidden)
        self.assertEqual(w['_sync'].sheet_state, 'veryHidden')

    def test_exact_ten_visible_columns(self):
        sheet = load_workbook(io.BytesIO(self.raw))['Samples']
        self.assertEqual([sheet.cell(4, c).value for c in range(1, 11)], [
            'Malex Model', 'Photo', 'Product Description', 'Factory Model', 'Factory',
            'Sample Qty', 'Color', 'Remarks', 'Sample Ready Date', 'Factory Feedback'])
        self.assertEqual(sheet.freeze_panes, 'C5')

    def test_changed_description_is_not_importable(self):
        edited = edited_file(self.raw, lambda w: setattr(w['Samples']['C5'], 'value', 'Changed specification'))
        _, rows = parse_workbook(edited)
        with self.assertRaises(ValueError):
            compare_rows(self.rows, self.rows, rows)

    def test_schema_is_available_to_importer(self):
        token, rows, schema = parse_workbook(self.raw, include_schema=True)
        self.assertEqual(schema, 'sample-excel-sync/2')
        self.assertEqual(token, 'opaque-export')
        self.assertEqual(rows, self.rows)

    def test_legacy_layout_remains_readable(self):
        book = Workbook()
        sheet = book.active
        sheet.title = 'Samples'
        headers = ['Factory', 'Malex Model', 'Factory Model', 'Photo', 'Sample Qty',
                   'Color & Finish', 'Other Sample Requirements', 'Sample Ready Date',
                   'Factory Feedback', 'Plug / Logo (Reference)', 'Line Status', 'Record Key']
        for col, header in enumerate(headers, 1):
            sheet.cell(4, col, header)
        values = ['Demo Factory', 'DEMO-001', 'FM-001', None, 2, 'Silver', 'Chrome handle',
                  '2026-11-14', None, 'Plug: VDE', 'In Progress', 'legacy-key']
        for col, value in enumerate(values, 1):
            sheet.cell(5, col, value)
        meta = book.create_sheet('_sync')
        meta['A1'] = 'sample-excel-sync/1'
        meta['A2'] = 'legacy-export'
        meta.sheet_state = 'veryHidden'
        out = io.BytesIO()
        book.save(out)
        token, rows, schema = parse_workbook(out.getvalue(), include_schema=True)
        self.assertEqual((token, schema), ('legacy-export', 'sample-excel-sync/1'))
        edited = [dict(rows[0], factory_comment='Ready')]
        changes = compare_rows(rows, rows, edited, schema=schema)
        self.assertEqual([c['field'] for c in changes], ['factory_comment'])


    def test_picture_moves_with_cells_and_no_external_relationship(self):
        image = io.BytesIO()
        Image.new('RGB', (32, 32), 'blue').save(image, 'PNG')
        raw = build_workbook('SMP-DEMO', 'export', [sample(image=image.getvalue())])
        with ZipFile(io.BytesIO(raw)) as z:
            drawing = z.read('xl/drawings/drawing1.xml')
            self.assertIn(b'twoCellAnchor', drawing)
            self.assertNotIn(b'TargetMode="External"', b''.join(
                z.read(n) for n in z.namelist() if n.endswith('.rels')))

    def test_non_xlsx_and_embedded_active_content_rejected(self):
        with self.assertRaises(ValueError):
            parse_workbook(b'not a workbook')
        out = io.BytesIO(self.raw)
        with ZipFile(out, 'a', ZIP_DEFLATED) as z:
            z.writestr('xl/vbaProject.bin', b'fake macro')
        with self.assertRaises(ValueError):
            parse_workbook(out.getvalue())

    def test_entities_and_compression_bombs_rejected(self):
        for name, content in [('evil.xml', b'<!DOCTYPE x [<!ENTITY x "y">]><x/>'),
                              ('padding.xml', b'0' * 2_000_000)]:
            out = io.BytesIO(self.raw)
            with ZipFile(out, 'a', ZIP_DEFLATED) as z:
                z.writestr(name, content)
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_workbook(out.getvalue())

    def test_passive_excel_printer_settings_are_accepted(self):
        out = io.BytesIO(self.raw)
        with ZipFile(out, 'a', ZIP_DEFLATED) as z:
            z.writestr('xl/printerSettings/printerSettings1.bin', b'passive print settings')
        self.assertEqual(parse_workbook(out.getvalue())[0], 'opaque-export')

    def test_external_relationship_rejected(self):
        out = io.BytesIO(self.raw)
        with ZipFile(out, 'a', ZIP_DEFLATED) as z:
            z.writestr('xl/_rels/evil.xml.rels',
                       '<Relationships><Relationship TargetMode="External" Target="https://invalid.example"/></Relationships>')
        with self.assertRaises(ValueError):
            parse_workbook(out.getvalue())


class DescriptionTests(unittest.TestCase):
    def test_line_description_has_priority(self):
        from sync_core.description import choose_description
        self.assertEqual(choose_description('Sample-specific features',
                         {'mlx_description_text': 'Master features'}), 'Sample-specific features')

    def test_product_description_fallback_is_plain_text(self):
        from sync_core.description import choose_description
        self.assertEqual(choose_description('', {'description': '<p>500 W</p><p>Glass jar</p>'}),
                         '500 W\nGlass jar')

    def test_packaging_and_certification_fields_are_not_added(self):
        from sync_core.description import choose_description
        self.assertEqual(choose_description(False, {'mlx_description_text': 'Master features',
                         'description_purchase': 'Internal packing', 'certifications': 'GS'}),
                         'Master features')

    def test_less_than_feature_text_is_preserved(self):
        from sync_core.description import choose_description
        self.assertEqual(choose_description('Brewing time: <10 MINS\nTemperature: >75℃', {}),
                         'Brewing time: <10 MINS\nTemperature: >75℃')



if __name__ == '__main__':
    unittest.main()
