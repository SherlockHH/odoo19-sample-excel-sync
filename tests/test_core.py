import importlib.util
import io
import sys
import unittest
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import load_workbook
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
               factory_comment='', reference='Plug: VDE', state='In Progress')
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
        raw = edited_file(self.raw, lambda w: setattr(w['Samples']['H5'], 'value',
                                                    date(2026, 11, 18)))
        self.assertEqual(parse_workbook(raw)[1][0]['factory_ready_date'], '2026-11-18')

    def test_empty_fields_are_true_blank_cells(self):
        raw = build_workbook('SMP-DEMO', 'export', [sample(sample_color='', factory_model='')])
        book = load_workbook(io.BytesIO(raw))
        for address in ('C5', 'F5', 'I5'):
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
            self.assertEqual(w['Samples']['I5'].data_type, 's')
            self.assertEqual(parse_workbook(raw)[1][0]['factory_comment'], text)

    def test_incoming_formula_is_rejected(self):
        raw = edited_file(self.raw, lambda w: setattr(w['Samples']['I5'], 'value', '=1+1'))
        with self.assertRaises(ValueError):
            parse_workbook(raw)

    def test_invalid_dates_are_not_silently_interpreted(self):
        for value in ['TBC', '18/11/2026', 46335, '2026-02-30', 0, False]:
            def edit(book):
                book['Samples']['H5'] = value
                book['Samples']['H5'].number_format = 'General'
            raw = edited_file(self.raw, edit)
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_workbook(raw)

    def test_table_includes_hidden_row_key(self):
        w = load_workbook(io.BytesIO(self.raw))
        self.assertEqual(w['Samples'].tables['SampleLines'].ref, 'A4:L6')
        self.assertTrue(w['Samples'].column_dimensions['L'].hidden)
        self.assertEqual(w['_sync'].sheet_state, 'veryHidden')

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


if __name__ == '__main__':
    unittest.main()
