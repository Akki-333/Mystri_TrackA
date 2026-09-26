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


class InvoiceReimportTests(LedgerTestCase):
    """BUSINESS_RULES: identical re-import skips; reused identity with different details rejects."""

    ROW = 'HARBOR,DUP-1,10.00,2026-09-09'

    def test_identical_invoice_reimport_is_skipped_and_totals_do_not_move(self):
        self.assertEqual(self.import_csv('invoices', self.ROW)['imported'], 1)
        before = reporting.overview(self.db)['summary']
        again = self.import_csv('invoices', self.ROW)
        self.assertEqual((again['imported'], again['skipped'], again['rejected']), (0, 1, 0))
        rows = [r for r in reporting.invoices(self.db) if r['invoice_number'] == 'DUP-1']
        self.assertEqual(len(rows), 1)
        self.assertEqual(reporting.overview(self.db)['summary'], before)

    def test_same_identity_with_different_details_is_rejected_and_original_kept(self):
        self.import_csv('invoices', self.ROW)
        result = self.import_csv('invoices', 'HARBOR,DUP-1,99.00,2026-09-09')
        self.assertEqual((result['imported'], result['skipped'], result['rejected']), (0, 0, 1))
        self.assertEqual([e['line'] for e in result['errors']], [2])
        kept = self.invoice('DUP-1')
        self.assertAlmostEqual(kept['amount'], 10.00, places=2)

    def test_same_invoice_number_under_a_different_customer_is_a_separate_invoice(self):
        result = self.import_csv('invoices', self.ROW, 'MAPLE,DUP-1,42.00,2026-09-09')
        self.assertEqual(result['imported'], 2)
        self.assertAlmostEqual(self.invoice('DUP-1', 'HARBOR')['amount'], 10.00, places=2)
        self.assertAlmostEqual(self.invoice('DUP-1', 'MAPLE')['amount'], 42.00, places=2)


class RowLevelRejectionTests(LedgerTestCase):
    """BUSINESS_RULES: an invalid data row rejects only that row, with its CSV line number."""

    def test_one_invalid_row_does_not_stop_the_valid_rows(self):
        result = self.import_csv(
            'invoices',
            'HARBOR,INV-103,84.00,2026-09-12',
            'NORTH,INV-302,not-a-number,2026-09-12',
            'MAPLE,INV-203,100.00,2026-09-13')
        self.assertEqual((result['imported'], result['skipped'], result['rejected']), (2, 0, 1))
        self.assertEqual([e['line'] for e in result['errors']], [3])
        self.assertTrue(result['errors'][0]['reason'])
        numbers = {r['invoice_number'] for r in reporting.invoices(self.db)}
        self.assertIn('INV-103', numbers)
        self.assertIn('INV-203', numbers)
        self.assertNotIn('INV-302', numbers)

    def test_every_row_invalid_still_reports_counts_instead_of_failing(self):
        result = self.import_csv('invoices',
                                 'HARBOR,INV-901,-5.00,2026-09-12',
                                 'GHOST,INV-902,10.00,2026-09-12',
                                 'HARBOR,INV-903,10.00,12-09-2026')
        self.assertEqual((result['imported'], result['skipped'], result['rejected']), (0, 0, 3))
        self.assertEqual([e['line'] for e in result['errors']], [2, 3, 4])

    def test_valid_header_with_no_rows_is_a_successful_empty_import(self):
        result = self.import_csv('invoices')
        self.assertEqual((result['imported'], result['skipped'], result['rejected']), (0, 0, 0))
        self.assertEqual(result['errors'], [])

    def test_invalid_header_rejects_the_whole_file_and_writes_nothing(self):
        before = reporting.overview(self.db)['summary']
        with self.assertRaises(ValueError):
            importing.import_csv(self.db, 'customer,invoice,value\nHARBOR,INV-110,50.00\n', 'invoices')
        self.assertEqual(reporting.overview(self.db)['summary'], before)

    def test_payment_rows_are_also_rejected_individually(self):
        result = self.import_csv('payments',
                                 'PAY-201,MAPLE,INV-200,1250.00',
                                 'PAY-BAD,MAPLE,INV-200,twelve',
                                 'PAY-301,NORTH,INV-300,9.99')
        self.assertEqual((result['imported'], result['skipped'], result['rejected']), (2, 0, 1))
        self.assertEqual([e['line'] for e in result['errors']], [3])


class StatusFilterTests(LedgerTestCase):
    """BUSINESS_RULES: open means a positive balance, paid means zero or negative."""

    def test_open_filter_returns_only_open_invoices_and_agrees_with_the_overview(self):
        open_rows = reporting.invoices(self.db, 'open')
        self.assertTrue(open_rows)
        self.assertEqual({r['status'] for r in open_rows}, {'open'})
        self.assertEqual(len(open_rows), reporting.overview(self.db)['summary']['open_count'])

    def test_paid_filter_returns_only_paid_invoices_and_all_is_the_union(self):
        paid_rows = reporting.invoices(self.db, 'paid')
        self.assertTrue(paid_rows)
        self.assertEqual({r['status'] for r in paid_rows}, {'paid'})
        self.assertEqual(len(reporting.invoices(self.db, 'all')),
                         len(paid_rows) + len(reporting.invoices(self.db, 'open')))

    def test_an_overpaid_invoice_is_paid_and_does_not_reduce_other_outstanding(self):
        # INV-301 is 100.00 and unpaid; pay 150.00 against it.
        outstanding_before = reporting.overview(self.db)['summary']['outstanding']
        self.import_csv('payments', 'PAY-OVER,NORTH,INV-301,150.00')
        invoice = self.invoice('INV-301')
        self.assertEqual(invoice['status'], 'paid')
        self.assertAlmostEqual(invoice['balance'], -50.00, places=2)
        self.assertNotIn('INV-301', {r['invoice_number'] for r in reporting.invoices(self.db, 'open')})
        summary = reporting.overview(self.db)['summary']
        self.assertAlmostEqual(summary['outstanding'], outstanding_before - 100.00, places=2)

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            reporting.invoices(self.db, 'overdue')


class ExportAgreementTests(LedgerTestCase):
    """BUSINESS_RULES: exported money must be accurate to two places and agree with the screen."""

    def export_rows(self):
        import csv as _csv
        import io as _io
        return list(_csv.DictReader(_io.StringIO(reporting.export_csv(self.db))))

    def test_export_keeps_the_exact_cents_of_a_19_99_invoice(self):
        row = next(r for r in self.export_rows() if r['invoice_number'] == 'INV-300')
        self.assertEqual(row['amount'], '19.99')
        self.assertEqual(row['paid'], '10.00')
        self.assertEqual(row['balance'], '9.99')

    def test_every_exported_row_agrees_with_the_same_record_on_screen(self):
        screen = {(r['customer_id'], r['invoice_number']): r for r in reporting.invoices(self.db)}
        for row in self.export_rows():
            record = screen[(row['customer_id'], row['invoice_number'])]
            for field in ('amount', 'paid', 'balance'):
                self.assertEqual(row[field], f"{record[field]:.2f}",
                                 f"{row['invoice_number']} {field} disagrees with the screen")
            self.assertEqual(row['status'], record['status'])

    def test_cents_survive_a_partial_payment(self):
        self.import_csv('invoices', 'HARBOR,CENT-1,0.10,2026-09-20')
        self.import_csv('payments', 'PAY-CENT,HARBOR,CENT-1,0.07')
        self.assertAlmostEqual(self.invoice('CENT-1')['balance'], 0.03, places=2)
        row = next(r for r in self.export_rows() if r['invoice_number'] == 'CENT-1')
        self.assertEqual((row['amount'], row['paid'], row['balance']), ('0.10', '0.07', '0.03'))


class RejectedRowsDownloadTests(LedgerTestCase):
    """Improvement: an import returns its rejected rows as a correctable CSV."""

    MIXED = ('HARBOR,INV-103,84.00,2026-09-12',
             'NORTH,INV-302,not-a-number,2026-09-12',
             'MAPLE,INV-203,100.00,2026-09-13')

    def test_rejected_rows_come_back_as_csv_with_the_reason(self):
        result = self.import_csv('invoices', *self.MIXED)
        lines = result['rejected_csv'].strip().splitlines()
        self.assertEqual(lines[0], 'customer_id,invoice_number,amount,due_date,line,reason')
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith('NORTH,INV-302,not-a-number,2026-09-12,3,'))

    def test_a_clean_import_returns_no_rejected_csv(self):
        result = self.import_csv('invoices', 'HARBOR,INV-104,12.00,2026-09-14')
        self.assertEqual(result['rejected'], 0)
        self.assertEqual(result['rejected_csv'], '')

    def test_correcting_the_downloaded_rows_and_reimporting_the_file_is_safe(self):
        # The corrected file can be re-imported whole: the fixed row imports,
        # the rows that already landed are skipped, and no total moves twice.
        first = self.import_csv('invoices', *self.MIXED)
        self.assertEqual((first['imported'], first['rejected']), (2, 1))
        corrected = ('HARBOR,INV-103,84.00,2026-09-12',
                     'NORTH,INV-302,55.00,2026-09-12',
                     'MAPLE,INV-203,100.00,2026-09-13')
        second = self.import_csv('invoices', *corrected)
        self.assertEqual((second['imported'], second['skipped'], second['rejected']), (1, 2, 0))
        self.assertAlmostEqual(self.invoice('INV-302')['amount'], 55.00, places=2)
        self.assertEqual(len(reporting.invoices(self.db)), 9)


if __name__ == '__main__':
    unittest.main()
