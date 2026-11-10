import io
import re
from datetime import date, datetime
from zipfile import BadZipFile, ZipFile

import openpyxl
import xlsxwriter
from defusedxml.ElementTree import fromstring
from PIL import Image, UnidentifiedImageError

from .constants import COLUMNS, MAX_EXPANDED, MAX_FILE, MAX_ROWS, MAX_TEXT, SCHEMA


def _text(value):
    if value is None or value is False:
        return ''
    if not isinstance(value, str):
        raise ValueError('Text columns must contain text, not numbers or formulas.')
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    if len(value) > MAX_TEXT:
        raise ValueError(f'A text cell exceeds {MAX_TEXT} characters.')
    return value


def _date(value):
    if value is None or value == '':
        return ''
    if isinstance(value, datetime):
        if value.time() != datetime.min.time():
            raise ValueError('Sample Ready Date must not include a time.')
        value = value.date()
    if isinstance(value, date):
        result = value
    elif isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        result = date.fromisoformat(value)
    else:
        raise ValueError('Sample Ready Date must be a date or YYYY-MM-DD; use Feedback for TBC.')
    if not 1900 <= result.year <= 2200:
        raise ValueError('Sample Ready Date must be between 1900 and 2200.')
    return result.isoformat()


def _thumbnail(raw):
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('An image is too large. Use a smaller product image.')
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.width * img.height > 16_000_000:
                raise ValueError('An image has too many pixels.')
            img.thumbnail((110, 100))
            out = io.BytesIO()
            img.convert('RGB').save(out, format='PNG')
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid product image.') from exc


def build_workbook(request_name, batch_token, rows):
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError(f'Export requires between 1 and {MAX_ROWS} sample lines.')
    out = io.BytesIO()
    book = xlsxwriter.Workbook(out, {'in_memory': True, 'strings_to_formulas': False,
                                   'strings_to_urls': False})
    sheet = book.add_worksheet('Samples')
    meta = book.add_worksheet('_sync')
    meta.very_hidden()
    meta.write_string(0, 0, SCHEMA)
    meta.write_string(1, 0, batch_token)
    title = book.add_format({'bold': True, 'font_size': 18, 'font_color': '#17324D'})
    plain = book.add_format({'text_wrap': True, 'valign': 'top', 'font_size': 11})
    editable = book.add_format({'text_wrap': True, 'valign': 'top', 'font_size': 11,
                               'bg_color': '#EFF6FF'})
    date_format = book.add_format({'num_format': 'yyyy-mm-dd', 'valign': 'top',
                                  'bg_color': '#EFF6FF', 'font_size': 11})
    sheet.write_string(0, 0, 'Sample Request', title)
    sheet.write_string(1, 0, str(request_name), plain)
    sheet.write_string(2, 0, 'Edit blue columns. Leave a date blank until confirmed. Sort the full table.', plain)
    widths = [24, 21, 22, 18, 12, 28, 45, 19, 45, 25, 20, 40]
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width, plain, {'hidden': col == 11})
    sheet.set_row(3, 34)
    for index, row in enumerate(rows, 4):
        sheet.set_row(index, 90)
        for col, (key, _) in enumerate(COLUMNS):
            value = row.get(key)
            if key == 'image':
                if value:
                    thumb = _thumbnail(value)
                    sheet.insert_image(index, col, 'product.png', {
                        'image_data': io.BytesIO(thumb), 'object_position': 1,
                        'x_offset': 5, 'y_offset': 5, 'description': row.get('model') or 'Product',
                    })
            elif key == 'quantity' and isinstance(value, (int, float)) and not isinstance(value, bool):
                sheet.write_number(index, col, value, plain)
            elif key == 'factory_ready_date':
                normalized = _date(value)
                if normalized:
                    sheet.write_datetime(index, col, datetime.fromisoformat(normalized), date_format)
                else:
                    sheet.write_blank(index, col, None, date_format)
            else:
                fmt = editable if key in ('sample_color', 'remarks', 'factory_comment') else plain
                sheet.write_string(index, col, _text(value), fmt)
    sheet.add_table(3, 0, 3 + len(rows), 11, {
        'name': 'SampleLines', 'style': 'Table Style Light 9',
        'columns': [{'header': label} for _, label in COLUMNS],
    })
    sheet.data_validation(4, 7, 3 + len(rows), 7, {
        'validate': 'date', 'criteria': 'between', 'minimum': date(1900, 1, 1),
        'maximum': date(2200, 12, 31), 'ignore_blank': True,
        'error_title': 'Use a date', 'error_message': 'Enter a date. Put TBC in Factory Feedback.',
    })
    sheet.freeze_panes(4, 2)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(3)
    sheet.print_area(0, 0, 3 + len(rows), 10)
    book.close()
    raw = out.getvalue()
    if len(raw) > MAX_FILE:
        raise ValueError('Workbook exceeds the 8 MB limit. Export one factory at a time.')
    return raw


def _check_archive(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_FILE:
        raise ValueError('Upload an XLSX file no larger than 8 MB.')
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 4096 or len({i.filename for i in infos}) != len(infos):
                raise ValueError('Invalid workbook archive.')
            if sum(i.file_size for i in infos) > MAX_EXPANDED:
                raise ValueError('Workbook expands beyond the safety limit.')
            for info in infos:
                name = info.filename.lower()
                if (info.flag_bits & 1 or info.file_size > 20 * 1024 * 1024
                        or info.file_size > max(100_000, info.compress_size * 250)):
                    raise ValueError('Encrypted or excessively compressed workbook.')
                if 'vbaproject' in name or any(p in name for p in
                                               ('externallinks/', 'activex/', 'embeddings/')):
                    raise ValueError('Macros and embedded active content are not accepted.')
                if name.endswith(('.xml', '.rels')):
                    content = archive.read(info)
                    if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
                        raise ValueError('XML entities are not accepted.')
                    if name.endswith('.rels'):
                        root = fromstring(content)
                        if any(e.attrib.get('TargetMode', '').lower() == 'external' for e in root):
                            raise ValueError('External workbook links are not accepted.')
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError('Invalid XLSX file.') from exc


def parse_workbook(raw):
    _check_archive(raw)
    try:
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False,
                                     keep_links=False)
        try:
            if set(book.sheetnames) != {'Samples', '_sync'}:
                raise ValueError('Use a workbook exported by Sample Excel Sync.')
            meta = book['_sync']
            if meta['A1'].value != SCHEMA:
                raise ValueError('Unsupported workbook version. Export a fresh file.')
            token = _text(meta['A2'].value)
            if not token:
                raise ValueError('Missing export identifier.')
            sheet = book['Samples']
            if sheet.max_row > MAX_ROWS + 4 or sheet.max_column > len(COLUMNS):
                raise ValueError('Workbook has too many rows or columns.')
            headers = [sheet.cell(4, c).value for c in range(1, 13)]
            if headers != [label for _, label in COLUMNS]:
                raise ValueError('Column headers were changed. Export a fresh file.')
            rows = []
            for cells in sheet.iter_rows(min_row=5, max_col=12):
                if not any(c.value is not None for c in cells):
                    continue
                row = {}
                for cell, (key, _) in zip(cells, COLUMNS):
                    if cell.data_type in ('f', 'e'):
                        raise ValueError('Formulas and error cells cannot be imported.')
                    if key == 'image':
                        continue
                    if key == 'factory_ready_date':
                        row[key] = _date(cell.value)
                    elif key == 'quantity':
                        value = cell.value
                        if value is not None and not isinstance(value, (str, int, float)):
                            raise ValueError('Invalid quantity cell.')
                        row[key] = '' if value is None else value
                    else:
                        row[key] = _text(cell.value)
                rows.append(row)
            return token, rows
        finally:
            book.close()
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(str(exc)) from exc
    except Exception as exc:
        raise ValueError('Cannot read this workbook. Export a fresh XLSX file.') from exc
