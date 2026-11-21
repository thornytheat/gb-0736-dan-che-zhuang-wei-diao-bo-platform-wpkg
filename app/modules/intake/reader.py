import csv
from io import StringIO

from app.config import MAX_INPUT_BYTES, MAX_RECORDS
from app.errors import DomainError


def records(raw, fields):
    if len(raw) > MAX_INPUT_BYTES:
        raise DomainError('BODY_TOO_LARGE', 413)
    if not raw:
        raise DomainError('EMPTY_FILE')
    try:
        text = raw.decode('utf-8-sig')
        encoding = 'UTF-8 BOM' if raw.startswith(b'\xef\xbb\xbf') else 'UTF-8'
    except UnicodeDecodeError:
        try:
            text = raw.decode('gb18030')
            encoding = 'GB18030'
        except UnicodeDecodeError:
            raise DomainError('BAD_ENCODING') from None
    if not text.strip():
        raise DomainError('BLANK_FILE')
    reader = csv.reader(StringIO(text, newline=''), strict=True)
    try:
        header = [cell.strip() for cell in next(reader)]
        if set(header) != set(fields) or len(header) != len(fields):
            raise DomainError('BAD_HEADER', line=1, required=list(fields))
        result = []
        line = reader.line_num + 1
        for row in reader:
            if len(result) >= MAX_RECORDS:
                raise DomainError('TOO_MANY_ROWS')
            cells = [cell.strip() for cell in row]
            code = None
            if not any(cells):
                code = 'BLANK_ROW'
            elif cells == header:
                code = 'REPEATED_HEADER'
            elif len(row) != len(header):
                code = 'COLUMN_COUNT'
            result.append({'line': line, 'raw': row, 'cells': dict(zip(header, cells)) if not code else {}, 'code': code})
            line = reader.line_num + 1
    except csv.Error:
        raise DomainError('BAD_CSV', line=reader.line_num) from None
    if not result:
        raise DomainError('HEADER_ONLY')
    return result, encoding
