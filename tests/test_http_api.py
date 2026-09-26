"""End-to-end checks over the real HTTP routes listed in BUSINESS_RULES.md.

These pin the response shapes the browser page depends on, including the 400
that the page must report as a failure rather than a completed import.
Run with: python -m unittest discover -s tests -v
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from ledger import storage
from ledger.http_app import make_server

ROOT = Path(__file__).resolve().parent.parent


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'demo.sqlite3'
        db = storage.connect(self.db_path)
        storage.seed(db)
        db.close()
        self.server = make_server(self.db_path, ROOT / 'web', 0)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as response:
            return response.status, response.read().decode('utf-8'), response.headers

    def post_csv(self, kind, body):
        request = urllib.request.Request(
            f'{self.base}/api/import?kind={kind}', data=body.encode('utf-8'),
            headers={'Content-Type': 'text/csv'}, method='POST')
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode('utf-8'))

    def test_overview_shape(self):
        status, body, _ = self.get('/api/overview')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(set(data), {'summary', 'invoices', 'unmatched_payments'})
        self.assertEqual(set(data['summary']), {'invoice_count', 'open_count', 'outstanding'})
        self.assertEqual(data['summary']['outstanding'], 3209.99)
        self.assertIsInstance(data['invoices'][0]['amount'], (int, float))

    def test_invoice_status_filters_and_invalid_status(self):
        for wanted in ('open', 'paid'):
            _, body, _ = self.get(f'/api/invoices?status={wanted}')
            self.assertEqual({r['status'] for r in json.loads(body)}, {wanted})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get('/api/invoices?status=overdue')
        self.assertEqual(caught.exception.code, 400)
        self.assertIn('error', json.loads(caught.exception.read().decode('utf-8')))

    def test_export_is_csv_and_matches_the_api(self):
        status, body, headers = self.get('/api/export')
        self.assertEqual(status, 200)
        self.assertIn('text/csv', headers['Content-Type'])
        self.assertTrue(body.startswith('customer_id,invoice_number,amount,paid,balance,status'))
        _, invoices, _ = self.get('/api/invoices?status=all')
        for record in json.loads(invoices):
            self.assertIn(
                f"{record['customer_id']},{record['invoice_number']},{record['amount']:.2f},",
                body)

    def test_partial_import_returns_200_with_counts_and_line_numbers(self):
        status, body = self.post_csv('invoices', (ROOT / 'samples' / 'invoices-mixed.csv').read_text())
        self.assertEqual(status, 200)
        self.assertEqual((body['imported'], body['skipped'], body['rejected']), (2, 0, 1))
        self.assertEqual([e['line'] for e in body['errors']], [3])
        self.assertIn('NORTH,INV-302,not-a-number', body['rejected_csv'])

    def test_bad_header_returns_400_with_an_error_message(self):
        status, body = self.post_csv('invoices', (ROOT / 'samples' / 'wrong-header.csv').read_text())
        self.assertEqual(status, 400)
        self.assertIn('error', body)
        self.assertNotIn('imported', body)


if __name__ == '__main__':
    unittest.main()
