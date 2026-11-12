import importlib.util
import io
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree.ElementTree import fromstring

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


def v2_file(rows, token='opaque-export'):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Samples'
    columns = [('model', 'Malex Model'), ('image', 'Photo'),
               ('product_description', 'Product Description'), ('factory_model', 'Factory Model'),
               ('factory', 'Factory'), ('quantity', 'Sample Qty'), ('sample_color', 'Color'),
               ('remarks', 'Remarks'), ('factory_ready_date', 'Sample Ready Date'),
               ('factory_comment', 'Factory Feedback'), ('key', 'Record Key')]
    for col, (key, header) in enumerate(columns, 1):
        sheet.cell(4, col, header)
        for row, values in enumerate(rows, 5):
            sheet.cell(row, col, values.get(key))
    meta = book.create_sheet('_sync')
    meta['A1'], meta['A2'] = 'sample-excel-sync/2', token
    meta.sheet_state = 'veryHidden'
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
        raw = edited_file(self.raw, lambda w: setattr(w['Samples']['J5'], 'value',
                                                    date(2026, 11, 18)))
        self.assertEqual(parse_workbook(raw)[1][0]['factory_ready_date'], '2026-11-18')

    def test_empty_fields_are_true_blank_cells(self):
        raw = build_workbook('SMP-DEMO', 'export', [sample(sample_color='', factory_model='')])
        book = load_workbook(io.BytesIO(raw))
        for address in ('C5', 'G5', 'K5'):
            with self.subTest(address=address):
                self.assertIsNone(book['Samples'][address].value)

    def test_whole_row_sort_keeps_identity(self):
        def edit(book):
            sheet = book['Samples']
            first = [c.value for c in sheet[5]]
            second = [c.value for c in sheet[6]]
            for col, value in enumerate(second, 1):
                sheet.cell(5, col).value = value
            for col, value in enumerate(first, 1):
                sheet.cell(6, col).value = value
        _, rows = parse_workbook(edited_file(self.raw, edit))
        self.assertEqual([r['key'] for r in rows], ['opaque-two', 'opaque-row-one'])

    def test_formula_like_feedback_exported_as_literal_text(self):
        for text in ['=HYPERLINK("https://invalid.example","x")', '+SUM(1,1)',
                     '@SUM(1,1)', '-1+2']:
            raw = build_workbook('SMP-DEMO', 'export', [sample(factory_comment=text)])
            w = load_workbook(io.BytesIO(raw))
            self.assertEqual(w['Samples']['K5'].data_type, 's')
            self.assertEqual(parse_workbook(raw)[1][0]['factory_comment'], text)

    def test_incoming_formula_is_rejected(self):
        raw = edited_file(self.raw, lambda w: setattr(w['Samples']['K5'], 'value', '=1+1'))
        with self.assertRaises(ValueError):
            parse_workbook(raw)

    def test_invalid_dates_are_not_silently_interpreted(self):
        for value in ['TBC', '18/11/2026', 46335, '2026-02-30', 0, False]:
            def edit(book):
                book['Samples']['J5'] = value
                book['Samples']['J5'].number_format = 'General'
            raw = edited_file(self.raw, edit)
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_workbook(raw)

    def test_table_includes_hidden_row_key(self):
        w = load_workbook(io.BytesIO(self.raw))
        self.assertEqual(w['Samples'].tables['SampleLines'].ref, 'A4:L6')
        self.assertTrue(w['Samples'].column_dimensions['L'].hidden)
        self.assertEqual(w['_sync'].sheet_state, 'veryHidden')

    def test_factory_first_layout_with_separate_remark_photo(self):
        sheet = load_workbook(io.BytesIO(self.raw))['Samples']
        self.assertEqual([sheet.cell(4, c).value for c in range(1, 12)], [
            'Factory', 'Malex Model No', 'Factory Model No', 'Photo', 'Product Description',
            'Sample Qty', 'Color', 'Remarks', 'Remark Photo', 'Sample Ready Date', 'Factory Feedback'])
        self.assertEqual(sheet.freeze_panes, 'E5')
        self.assertEqual([sheet.cell(5, c).fill.fgColor.rgb for c in range(1, 12)],
                         ['FFFFFFFF'] * 6 + ['FFFFF2CC'] * 2 + ['FFFFFFFF'] + ['FFFFF2CC'] * 2)

    def test_product_and_remark_photos_are_separate_proportional_anchors(self):
        photo = io.BytesIO()
        Image.new('RGB', (400, 200), 'green').save(photo, 'PNG')
        row = sample(image=photo.getvalue(), remark_image=photo.getvalue())
        raw = build_workbook('SMP-DEMO', 'export', [row, sample(key='no-remark')])
        sheet = load_workbook(io.BytesIO(raw))['Samples']
        self.assertEqual(len(sheet._images), 2)
        self.assertEqual([p.anchor._from.col for p in sheet._images], [3, 8])
        self.assertEqual([p.anchor._from.row for p in sheet._images], [4, 4])
        self.assertTrue(all(p.width == p.height * 2 for p in sheet._images))
        self.assertEqual(parse_workbook(raw)[1], [sample(), sample(key='no-remark')])

    def test_product_photo_retains_full_resolution_and_original_bytes(self):
        photo = io.BytesIO()
        Image.new('RGB', (1200, 800), 'green').save(photo, 'JPEG', quality=95)
        original = photo.getvalue()
        raw = build_workbook('SMP-DEMO', 'export', [sample(image=original)])
        sheet = load_workbook(io.BytesIO(raw))['Samples']
        self.assertEqual((sheet._images[0].width, sheet._images[0].height), (1200, 800))
        with ZipFile(io.BytesIO(raw)) as archive:
            self.assertIn(original, [archive.read(n) for n in archive.namelist() if n.startswith('xl/media/')])

    def test_combined_image_data_rejected_before_building_archive(self):
        photo = io.BytesIO()
        Image.new('RGB', (32, 32), 'green').save(photo, 'PNG')
        original = photo.getvalue()
        with patch('sync_core.workbook.MAX_IMAGE_DATA', len(original) * 2 - 1, create=True):
            with self.assertRaisesRegex(ValueError, 'Image data exceeds'):
                build_workbook('SMP-DEMO', 'export', [sample(image=original, remark_image=original)])

    def test_previous_ten_column_file_still_imports(self):
        raw = v2_file(self.rows)
        edited = edited_file(raw, lambda w: setattr(w['Samples']['J5'], 'value', 'V2 return'))
        _, rows, schema = parse_workbook(edited, include_schema=True)
        self.assertEqual(schema, 'sample-excel-sync/2')
        updates = resolve_changes(compare_rows(self.rows, self.rows, rows, schema=schema), {})
        self.assertEqual(updates, {'opaque-row-one': {'factory_comment': 'V2 return'}})

    def test_remark_photo_display_size_is_independent_of_source_dpi(self):
        for dpi in (72, 300):
            photo = io.BytesIO()
            Image.new('RGB', (400, 200), 'green').save(photo, 'PNG', dpi=(dpi, dpi))
            original = photo.getvalue()
            raw = build_workbook('SMP-DEMO', 'export', [sample(remark_image=original)])
            with ZipFile(io.BytesIO(raw)) as archive:
                root = fromstring(archive.read('xl/drawings/drawing1.xml'))
                extent = root.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}ext')
                with self.subTest(dpi=dpi):
                    self.assertAlmostEqual(int(extent.attrib['cx']) / 9525, 240, delta=0.02)
                    self.assertAlmostEqual(int(extent.attrib['cy']) / 9525, 120, delta=0.02)
                    self.assertIn(original, [archive.read(n) for n in archive.namelist() if n.startswith('xl/media/')])

    def test_changed_description_is_not_importable(self):
        edited = edited_file(self.raw, lambda w: setattr(w['Samples']['E5'], 'value', 'Changed specification'))
        _, rows = parse_workbook(edited)
        with self.assertRaises(ValueError):
            compare_rows(self.rows, self.rows, rows)

    def test_schema_is_available_to_importer(self):
        token, rows, schema = parse_workbook(self.raw, include_schema=True)
        self.assertEqual(schema, 'sample-excel-sync/3')
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


class ProductImageTests(unittest.TestCase):
    def choose(self, line, images):
        from sync_core.images import choose_product_image
        return choose_product_image(line, images)

    def test_related_thumbnail_uses_full_product_image(self):
        self.assertEqual(self.choose(b'thumbnail', {'image_128': b'thumbnail', 'image_1920': b'original'}), b'original')

    def test_api_string_and_orm_bytes_match_the_same_thumbnail(self):
        self.assertEqual(self.choose('thumbnail', {'image_128': b'thumbnail', 'image_1920': b'original'}), b'original')

    def test_distinct_sample_specific_photo_is_preserved(self):
        self.assertEqual(self.choose(b'custom-sample', {'image_128': b'thumbnail', 'image_1920': b'original'}), b'custom-sample')

    def test_absent_sample_photo_uses_largest_available_master(self):
        self.assertEqual(self.choose(False, {'image_1920': False, 'image_1024': b'large', 'image_256': b'small'}), b'large')

    def test_no_photos_remains_blank(self):
        self.assertFalse(self.choose(False, {}))



if __name__ == '__main__':
    unittest.main()
