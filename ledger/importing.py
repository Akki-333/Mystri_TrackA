import csv
import io
from .validation import HEADERS, normalize
from .storage import insert_invoice, insert_payment
from .matching import find_invoice


def import_csv(db, text, kind):
    """Import one CSV body and report per-row outcomes.

    An invalid header rejects the whole file and writes nothing. A bad data row
    rejects only itself: the remaining rows are still processed and the row is
    reported with its CSV line number (header is line 1) and a reason
    (BUSINESS_RULES, "CSV imports").
    """
    if kind not in HEADERS:
        raise ValueError('Unknown import kind')
    reader = csv.DictReader(io.StringIO(text.lstrip('﻿')))
    if reader.fieldnames != HEADERS[kind]:
        raise ValueError('Expected CSV header: ' + ','.join(HEADERS[kind]))
    customers = {r[0] for r in db.execute('SELECT customer_id FROM customers')}
    result = {'imported': 0, 'skipped': 0, 'rejected': 0, 'errors': []}
    rejected_rows = []
    with db:
        for raw in reader:
            line = reader.line_num
            try:
                row = normalize(raw, kind, customers)
                if kind == 'invoices':
                    outcome = insert_invoice(db, row)
                else:
                    outcome = insert_payment(db, row, find_invoice(db, row))
                result[outcome] += 1
            except ValueError as exc:
                result['rejected'] += 1
                result['errors'].append({'line': line, 'reason': str(exc)})
                rejected_rows.append((raw, line, str(exc)))
    # Extra response field (allowed by BUSINESS_RULES): the rejected rows as a
    # CSV the owner can correct and re-import, instead of hunting line numbers.
    result['rejected_csv'] = rejected_csv(kind, rejected_rows)
    return result


def rejected_csv(kind, rejected_rows):
    '''Return the rejected rows in the original column order, plus line and reason.'''
    if not rejected_rows:
        return ''
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(HEADERS[kind] + ['line', 'reason'])
    for raw, line, reason in rejected_rows:
        values = [(raw.get(field) or '').strip() for field in HEADERS[kind]]
        writer.writerow(values + [line, reason])
    return output.getvalue()
