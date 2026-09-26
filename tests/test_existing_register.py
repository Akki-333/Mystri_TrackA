"""The owner's existing register must survive the repair, new imports and a restart.

Works on a temporary copy of fixtures/existing-register.sqlite3; the supplied
fixture is never modified. Run with: python -m unittest discover -s tests -v
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ledger import importing, reporting, storage

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'fixtures' / 'existing-register.sqlite3'
EXPECTED = json.loads((ROOT / 'fixtures' / 'expected-records.json').read_text())


class ExistingRegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'clearledger.sqlite3'
        shutil.copy2(FIXTURE, self.path)
        self.db = self.open_app()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def open_app(self):
        """Open the register the way app.py does on startup."""
        db = storage.connect(self.path)
        storage.seed(db)  # must not overwrite or duplicate an existing register
        return db

    def restart(self):
        self.db.close()
        self.db = self.open_app()

    def assert_original_records_intact(self):
        customers = {r['customer_id']: r['name']
                     for r in self.db.execute('SELECT customer_id, name FROM customers')}
        for expected in EXPECTED['customers']:
            self.assertEqual(customers.get(expected['customer_id']), expected['name'])

        invoices = {r['id']: r for r in reporting.invoices(self.db)}
        for expected in EXPECTED['invoices']:
            found = invoices.get(expected['id'])
            self.assertIsNotNone(found, f"invoice id {expected['id']} is missing")
            self.assertEqual(found['customer_id'], expected['customer_id'])
            self.assertEqual(found['invoice_number'], expected['invoice_number'])
            self.assertEqual(f"{found['amount']:.2f}", expected['amount'])
            self.assertEqual(found['due_date'], expected['due_date'])

        payments = {r['payment_id']: r for r in self.db.execute('SELECT * FROM payments')}
        for expected in EXPECTED['payments']:
            found = payments.get(expected['payment_id'])
            self.assertIsNotNone(found, f"payment {expected['payment_id']} is missing")
            self.assertEqual(found['customer_id'], expected['customer_id'])
            self.assertEqual(found['invoice_number'], expected['invoice_number'])
            self.assertEqual(f"{found['amount']:.2f}", expected['amount'])
            self.assertEqual(found['invoice_id'], expected['invoice_id'],
                             f"{expected['payment_id']} is allocated to the wrong invoice")

    def test_supplied_register_opens_with_its_documented_totals(self):
        self.assert_original_records_intact()
        summary = reporting.overview(self.db)['summary']
        self.assertEqual(summary['invoice_count'], 9)
        self.assertEqual(summary['open_count'], 7)
        self.assertEqual(summary['outstanding'], 3698.19)
        unmatched = reporting.overview(self.db)['unmatched_payments']
        self.assertEqual([p['payment_id'] for p in unmatched], ['KEEP-U1'])

    def test_new_imports_work_and_both_old_and_new_records_survive_a_restart(self):
        invoice_result = importing.import_csv(
            self.db,
            'customer_id,invoice_number,amount,due_date\nMAPLE,NEW-800,200.00,2026-09-25\n',
            'invoices')
        payment_result = importing.import_csv(
            self.db,
            'payment_id,customer_id,invoice_number,amount\nNEW-P1,MAPLE,NEW-800,75.50\n',
            'payments')
        self.assertEqual(invoice_result['imported'], 1)
        self.assertEqual(payment_result['imported'], 1)

        self.restart()

        self.assert_original_records_intact()
        added = next(r for r in reporting.invoices(self.db) if r['invoice_number'] == 'NEW-800')
        self.assertAlmostEqual(added['paid'], 75.50, places=2)
        self.assertAlmostEqual(added['balance'], 124.50, places=2)
        summary = reporting.overview(self.db)['summary']
        self.assertEqual(summary['invoice_count'], 10)
        self.assertEqual(summary['open_count'], 8)
        self.assertAlmostEqual(summary['outstanding'], 3698.19 + 124.50, places=2)

    def test_the_unmatched_payment_stays_unmatched_after_a_restart(self):
        self.restart()
        unmatched = reporting.overview(self.db)['unmatched_payments']
        self.assertEqual([p['payment_id'] for p in unmatched], ['KEEP-U1'])
        self.assertAlmostEqual(unmatched[0]['amount'], 33.33, places=2)


if __name__ == '__main__':
    unittest.main()
