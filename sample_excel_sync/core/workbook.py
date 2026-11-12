import io
import re
import textwrap
from datetime import date, datetime
from zipfile import BadZipFile, ZipFile

import openpyxl
import xlsxwriter
from defusedxml.ElementTree import fromstring
from PIL import Image, UnidentifiedImageError
from xlsxwriter.image import Image as DrawingImage

from .constants import (COLUMNS, EDITABLE, IMAGE_KEYS, LAYOUTS,
                        MAX_EXPANDED, MAX_FILE, MAX_ROWS, MAX_TEXT, SCHEMA)


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


def _thumbnail(raw, size=(110, 110), preserve_original=False):
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('An image is too large. Use a smaller sample image.')
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.width * img.height > 16_000_000:
                raise ValueError('An image has too many pixels.')
            if preserve_original and img.format in ('PNG', 'JPEG'):
                return raw
            if not preserve_original:
                img.thumbnail(size)
            out = io.BytesIO()
            img.convert('RGB').save(out, format='PNG')
            return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid sample image.') from exc


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
    # Eleven visible columns; yellow only on the four editable fields.
    title = book.add_format({'font_name': 'Calibri', 'bold': True, 'font_size': 16,
                             'font_color': '#000000'})
    body = {'font_name': 'Calibri', 'font_size': 11,
            'font_color': '#000000', 'text_wrap': True, 'valign': 'vcenter',
            'align': 'center', 'border': 1, 'border_color': '#D5DBE1', 'bg_color': '#FFFFFF'}
    plain = book.add_format(body)
    description_format = book.add_format({**body, 'align': 'left'})
    editable = book.add_format({**body, 'align': 'left', 'bg_color': '#FFF2CC'})
    date_format = book.add_format({**body, 'num_format': 'yyyy-mm-dd', 'bg_color': '#FFF2CC'})
    header = book.add_format({'font_name': 'Calibri', 'bold': True, 'font_size': 12,
                              'font_color': '#243746', 'bg_color': '#E5EBF1',
                              'border': 1, 'border_color': '#D5DBE1', 'text_wrap': True,
                              'align': 'center', 'valign': 'vcenter'})
    note = book.add_format({'font_name': 'Calibri', 'font_size': 10, 'font_color': '#333333'})
    sheet.hide_gridlines(2)
    sheet.set_row(0, 26)
    sheet.set_row(1, 18)
    sheet.set_row(2, 18)
    sheet.write_string(0, 0, 'Sample Request', title)
    sheet.write_string(1, 0, str(request_name), note)
    sheet.write_string(2, 0, 'Editable fields are pale yellow: Color, Remarks, Sample Ready Date and Factory Feedback.', note)
    widths = [28, 21, 22, 20, 62, 12, 28, 42, 36, 20, 42, 40]
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width, None, {'hidden': col == len(COLUMNS) - 1})
    sheet.set_row(3, 36)
    for index, row in enumerate(rows, 4):
        wrapped_lines = max(sum(max(1, len(textwrap.wrap(part, width=int(widths[col]) - 2)))
                                for part in str(row.get(key) or '').split('\n'))
                            for col, (key, _) in enumerate(COLUMNS)
                            if key in ('product_description', 'remarks', 'factory_comment'))
        row_height = min(409, max(100, wrapped_lines * 13 + 12))
        pictures = {}
        for key in IMAGE_KEYS:
            value = row.get(key)
            if value:
                size = (240, 180) if key == 'remark_image' else (110, 110)
                data = _thumbnail(value, size, preserve_original=True)
                picture = DrawingImage(io.BytesIO(data))
                width, height = picture.width, picture.height
                scale = min(1, size[0] / width, size[1] / height)
                pictures[key] = (data, width * scale, height * scale,
                                 scale * picture.x_dpi / 96, scale * picture.y_dpi / 96)
                row_height = max(row_height, (height * scale + 12) * 0.75)
        sheet.set_row(index, row_height)
        for col, (key, _) in enumerate(COLUMNS):
            value = row.get(key)
            if key in IMAGE_KEYS:
                sheet.write_blank(index, col, None, plain)
                if key in pictures:
                    data, width, height, x_scale, y_scale = pictures[key]
                    sheet.insert_image(index, col, key + '.png', {
                        'image_data': io.BytesIO(data), 'object_position': 1,
                        'x_scale': x_scale, 'y_scale': y_scale,
                        'x_offset': max(5, (int(widths[col] * 7 + 5) - width) // 2),
                        'y_offset': max(5, (int(row_height * 4 / 3) - height) // 2),
                        'description': ('Remark photo: ' if key == 'remark_image' else 'Product: ') + (row.get('model') or 'Sample'),
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
                fmt = editable if key in EDITABLE else description_format if key == 'product_description' else plain
                text = _text(value)
                if text:
                    sheet.write_string(index, col, text, fmt)
                else:
                    sheet.write_blank(index, col, None, fmt)
    sheet.add_table(3, 0, 3 + len(rows), len(COLUMNS) - 1, {
        'name': 'SampleLines', 'style': None, 'banded_rows': False,
        'columns': [{'header': label, 'header_format': header} for _, label in COLUMNS],
    })
    date_col = next(col for col, (key, _) in enumerate(COLUMNS) if key == 'factory_ready_date')
    sheet.data_validation(4, date_col, 3 + len(rows), date_col, {
        'validate': 'date', 'criteria': 'between', 'minimum': date(1900, 1, 1),
        'maximum': date(2200, 12, 31), 'ignore_blank': True,
        'error_title': 'Use a date', 'error_message': 'Enter a date. Put TBC in Factory Feedback.',
    })
    sheet.freeze_panes(4, 4)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(3)
    sheet.print_area(0, 0, 3 + len(rows), len(COLUMNS) - 2)
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


def parse_workbook(raw, *, include_schema=False):
    _check_archive(raw)
    try:
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=False,
                                     keep_links=False)
        try:
            if set(book.sheetnames) != {'Samples', '_sync'}:
                raise ValueError('Use a workbook exported by Sample Excel Sync.')
            meta = book['_sync']
            schema = meta['A1'].value
            if schema not in LAYOUTS:
                raise ValueError('Unsupported workbook version. Export a fresh file.')
            columns = LAYOUTS[schema]
            token = _text(meta['A2'].value)
            if not token:
                raise ValueError('Missing export identifier.')
            sheet = book['Samples']
            if sheet.max_row > MAX_ROWS + 4 or sheet.max_column > len(columns):
                raise ValueError('Workbook has too many rows or columns.')
            headers = [sheet.cell(4, c).value for c in range(1, len(columns) + 1)]
            if headers != [label for _, label in columns]:
                raise ValueError('Column headers were changed. Export a fresh file.')
            rows = []
            for cells in sheet.iter_rows(min_row=5, max_col=len(columns)):
                if not any(c.value is not None for c in cells):
                    continue
                row = {}
                for cell, (key, _) in zip(cells, columns):
                    if cell.data_type in ('f', 'e'):
                        raise ValueError('Formulas and error cells cannot be imported.')
                    if key in IMAGE_KEYS:
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
            return (token, rows, schema) if include_schema else (token, rows)
        finally:
            book.close()
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(str(exc)) from exc
    except Exception as exc:
        raise ValueError('Cannot read this workbook. Export a fresh XLSX file.') from exc
