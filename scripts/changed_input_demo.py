"""Changed-input demonstration for the payment-matching defect.

A payment for MAPLE / INV-200 of 1250.00 is imported. That amount also equals
HARBOR / INV-100, so the starter code credits the wrong customer while the
overview total stays the same. Run from the track folder:

    python scripts/changed_input_demo.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ledger import importing, reporting, storage  # noqa: E402

PAYMENT = ('payment_id,customer_id,invoice_number,amount\n'
           'PAY-201,MAPLE,INV-200,1250.00\n')


def main():
    db = storage.connect(Path(tempfile.mkdtemp()) / 'demo.sqlite3')
    storage.seed(db)
    result = importing.import_csv(db, PAYMENT, 'payments')
    print(f"import: imported={result['imported']} "
          f"skipped={result['skipped']} rejected={result['rejected']}")
    for row in reporting.invoices(db):
        if row['invoice_number'] in ('INV-100', 'INV-200'):
            print(f"  {row['customer_id']}/{row['invoice_number']} "
                  f"paid={row['paid']:.2f} balance={row['balance']:.2f} {row['status']}")
    print(f"  outstanding: {reporting.overview(db)['summary']['outstanding']:.2f}")
    db.close()


if __name__ == '__main__':
    main()
