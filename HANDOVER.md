# Handover

- Name: Akshay
- Email used for this application: akkies445@gmail.com
- Chosen track: A — Repair the register
- Why this track (one or two sentences): I work day to day on a Flask/React application doing backend APIs, frontend integration and QA, so investigating a small ledger and proving the repairs with tests is the work I am strongest at and can explain line by line.
- Approximate total time, including setup and handover: about 4 hours

## Run and verify

Python 3.10+ only; no third-party dependencies added.

```text
cd Mystri_TrackA
python -m unittest discover -s tests -v          # 34 tests, all passing
python restore_fixture.py --replace              # owner's existing register (app stopped)
python app.py                                    # http://127.0.0.1:8787
```

Failing-before / passing-after, using the untouched starter commit:

```text
git archive 0843232 | tar -x -C ../clearledger-before   # starter code
cp -r tests ../clearledger-before/                      # my tests against it
cd ../clearledger-before && python -m unittest discover -s tests
# observed: Ran 34 tests, FAILED (failures=12, errors=6)
```

Changed-input case (details below):

```text
python - <<'PY'
from ledger import storage, reporting, importing
import tempfile; from pathlib import Path
db = storage.connect(Path(tempfile.mkdtemp())/'d.sqlite3'); storage.seed(db)
importing.import_csv(db, 'payment_id,customer_id,invoice_number,amount\nPAY-201,MAPLE,INV-200,1250.00\n', 'payments')
print([(r['customer_id'], r['invoice_number'], r['paid']) for r in reporting.invoices(db)
       if r['invoice_number'] in ('INV-100','INV-200')])
PY
```

## What I delivered

Six reproducible defects, fixed worst-first, each with a regression test written before the fix.

| # | Defect | Fix | Commit |
| --- | --- | --- | --- |
| 1 | Payments attached to any invoice with an equal amount, ignoring customer and invoice number | `ledger/matching.py` matches on identity only | `c810b01` |
| 2 | Re-importing an invoice inserted a duplicate; reused identities were never rejected | `insert_invoice` skips identical rows, rejects changed ones | `f410345` |
| 3 | One invalid row failed the whole file, with no line numbers | validation moved into the insert loop; line from `reader.line_num` | `95615f9` |
| 4 | `status=open` returned paid invoices | filter compares against the requested status | `be19aa1` |
| 5 | Export truncated money (19.99 exported as 19.98) | report at currency precision, format the reported value | `7844790` |
| 6 | The page said "Import complete" even for a 400 | checks `response.ok`, shows real counts and rejected lines | `b195ec1` |

**Improvement (`205d149`): download rejected rows.** A partial import now also returns `rejected_csv` — the failed rows in the original column order plus `line` and `reason` — and the page offers it as a download. The owner corrects that small file and re-imports the whole file; defect 2's fix makes that safe, because rows that already landed are skipped rather than duplicated. `tests/test_regression.py::RejectedRowsDownloadTests` covers the round trip (2 imported + 1 rejected, then 1 imported + 2 skipped, 9 invoices, no totals moved twice).

## Evidence and limits

**Failing-before / passing-after.** My tests against the starter commit: `FAILED (failures=12, errors=6)`. Against the repair: `Ran 34 tests ... OK`. Command above.

**Existing register** (`tests/test_existing_register.py`, runs on a temp copy; `fixtures/` is unmodified). Opening the supplied register gives 9 invoices, 7 open, outstanding 3698.19, `KEEP-U1` unmatched, and every customer, invoice id, identity, amount, due date and payment allocation matches `fixtures/expected-records.json`. It then imports a new invoice and payment, reopens the database as a restart would, and re-checks the originals plus the new records (10 invoices, 8 open, 3822.69). I changed no schema, so no migration was needed.

**Changed-input case.** I re-imported `PAY-201 MAPLE,INV-200,1250.00`, whose amount also equals HARBOR/INV-100. Before running I expected the starter to credit HARBOR/INV-100 and the repair to credit MAPLE/INV-200, with the same overview total either way. Observed exactly that: starter `HARBOR/INV-100 paid=1250.00`, repaired `MAPLE/INV-200 paid=1250.00`, outstanding 1959.99 in both. That is why the defect survived: the summary looks right while the money sits on another customer.

**My own additional cases** beyond reproductions: an overpayment (150.00 against a 100.00 invoice must show −50.00, count as paid, and reduce outstanding by 100.00, not 150.00); the same invoice number under two customers staying separate; an all-invalid file returning counts instead of an error; and an every-row comparison of the CSV export against the API so a future rounding drift is caught, not just 19.99.

**Tested vs assumed.** Everything above is tested in Python. The browser changes (defect 6 and the download button) I verified by hand in the browser, plus `tests/test_http_api.py` pinning the JSON the page consumes; there is no automated DOM test.

**Known limits and next steps.** Money is still stored as SQLite `REAL` and rounded at the reporting boundary; correct for two-decimal inputs, but storing integer paise with a migration would be the durable fix and is my next step. `(customer_id, invoice_number)` uniqueness is enforced in code, not by a database constraint, so a second writer could still insert a duplicate; concurrent writers are out of scope here. Unmatched payments are not re-matched when their invoice arrives later, which the rules put out of scope but is the first thing I would raise with the owner. Questions I would ask in a real project: should a reused invoice identity with a *higher* amount be an amendment rather than a rejection, and who is allowed to correct a misallocated payment after the fact?

## Tools and judgment

I used Claude (Opus 5) in Cowork as a pair, alongside `python -m unittest`, sqlite3 and the browser.

1. **Suggestion:** fix the open/paid filter first, since it is a one-line change. **My decision:** I did it fourth. A wrong filter is visible and annoying; a payment landing on another customer's invoice is silent and moves money, so that went first. **Check:** the changed-input case above showed the overview total is identical either way, which confirmed the matching bug was the one a user could not catch by eye.
2. **Suggestion:** number the rejected rows with `enumerate(rows, 2)`, as the starter did. **My decision:** rejected, and used `csv.DictReader.line_num`. **Check:** `enumerate` counts parsed rows, so a blank line mid-file shifts every later line number and points the owner at the wrong row; `line_num` is the real file position.
3. **Suggestion:** for the export, format with `f"{value:.2f}"`. **My decision:** kept it, but also rounded `amount`, `paid` and `balance` inside `reporting.invoices`. **Check:** formatting only the CSV would have left the API returning `-10.000000000000002` while the CSV said `-10.00`; the rule is that the CSV agrees with the same record on screen, so the rounding belongs where both read from. The every-row comparison test enforces it.
