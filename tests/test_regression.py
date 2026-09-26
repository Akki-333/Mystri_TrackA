"""Regression checks for the defects found during the investigation.

Each test below fails against the starter code and passes after the matching fix.
Run with: python -m unittest discover -s tests -v
"""
import tempfile
import unittest
from pathlib import Path

from ledger import importing, reporting, storage


class LedgerTestCase(unittest.TestCase):
    """A fresh seeded demo database per test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = storage.connect(Path(self.tmp.name) / 'demo.sqlite3')
        storage.seed(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def invoice(self, invoice_number, customer_id=None):
        rows = [r for r in reporting.invoices(self.db)
                if r['invoice_number'] == invoice_number
                and (customer_id is None or r['customer_id'] == customer_id)]
        self.assertEqual(len(rows), 1, f'expected exactly one {invoice_number}')
        return rows[0]

    def import_csv(self, kind, *lines):
        header = {'invoices': 'customer_id,invoice_number,amount,due_date',
                  'payments': 'payment_id,customer_id,invoice_number,amount'}[kind]
        text = '\n'.join([header, *lines]) + '\n'
        return importing.import_csv(self.db, text, kind)


class PaymentMatchingTests(LedgerTestCase):
    """BUSINESS_RULES: a payment attaches only on the same customer AND invoice number."""

    def test_payment_does_not_attach_to_a_different_invoice_with_the_same_amount(self):
        # NORTH/INV-300 is 19.99. A HARBOR/INV-100 payment of 19.99 must not touch it.
        result = self.import_csv('payments', 'PAY-AMB,HARBOR,INV-100,19.99')
        self.assertEqual(result['imported'], 1)
        self.assertAlmostEqual(self.invoice('INV-100')['paid'], 19.99, places=2)
        self.assertAlmostEqual(self.invoice('INV-300')['paid'], 10.00, places=2)

    def test_payment_for_the_same_number_under_another_customer_stays_unmatched(self):
        # MAPLE has no INV-100; the amount equals HARBOR/INV-100 exactly.
        result = self.import_csv('payments', 'PAY-XCUST,MAPLE,INV-100,1250.00')
        self.assertEqual(result['imported'], 1)
        self.assertAlmostEqual(self.invoice('INV-100', 'HARBOR')['paid'], 0.00, places=2)
        unmatched = reporting.overview(self.db)['unmatched_payments']
        self.assertEqual([p['payment_id'] for p in unmatched], ['PAY-XCUST'])

    def test_payment_without_any_matching_invoice_is_kept_unmatched(self):
        result = self.import_csv('payments', 'PAY-404,HARBOR,INV-NOT-FOUND,50.00')
        self.assertEqual(result['imported'], 1)
        overview = reporting.overview(self.db)
        self.assertEqual([p['payment_id'] for p in overview['unmatched_payments']], ['PAY-404'])
        self.assertEqual(overview['summary']['outstanding'], 3209.99)


if __name__ == '__main__':
    unittest.main()
