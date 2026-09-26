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

**Improvement (`205d149`): download rejected rows.** A partial import also returns `rejected_csv` — the failed rows in their original columns plus `line` and `reason` — and the page offers it as a download. The owner fixes that small file and re-imports the whole file, which is safe because defect 2's fix skips rows that already landed. `RejectedRowsDownloadTests` covers the round trip: 2 imported + 1 rejected, then 1 imported + 2 skipped, 9 invoices, no total moved twice.

## Evidence and limits

**Failing-before / passing-after.** My tests on the starter commit: `FAILED (failures=12, errors=6)`. On the repair: `Ran 34 tests ... OK`.

**Existing register** (`tests/test_existing_register.py`, on a temp copy; `fixtures/` unmodified). The supplied register opens with 9 invoices, 7 open, outstanding 3698.19, `KEEP-U1` unmatched, and every id, identity, amount, due date and allocation matching `expected-records.json`. It then imports a new invoice and payment, reopens the database as a restart would, and re-checks originals and new records (10 invoices, 8 open, 3822.69). No schema change, so no migration.

**Changed-input case.** I imported `PAY-201,MAPLE,INV-200,1250.00`, whose amount also equals HARBOR/INV-100. I expected the starter to credit HARBOR/INV-100, the repair to credit MAPLE/INV-200, and the overview total to be identical either way. Observed exactly that (1959.99 in both). That is why the defect survived: the summary looks right while the money sits on another customer.

**Cases I designed:** an overpayment (150.00 on a 100.00 invoice → −50.00, paid, outstanding down by 100.00 not 150.00); one invoice number under two customers staying separate; an all-invalid file returning counts, not an error; and an every-row comparison of export against API, so future rounding drift is caught too.

**Tested vs assumed.** All of the above is tested in Python. The browser changes I checked by hand, with `tests/test_http_api.py` pinning the JSON the page consumes; there is no automated DOM test.

**Limits and next steps.** Money is still stored as `REAL` and rounded at the reporting boundary — correct for two-decimal inputs, but storing integer paise with a migration is the durable fix and my next step. Invoice identity is enforced in code, not by a database constraint, so a concurrent writer could still duplicate (out of scope here). Unmatched payments are not re-matched when their invoice later arrives; the rules exclude it, but it is the first thing I would raise with the owner, along with whether a reused identity with a higher amount should be an amendment rather than a rejection.

## Tools and judgment

Claude (Opus 5) in Cowork, with `python -m unittest`, sqlite3 and the browser.

1. **Suggested:** fix the open/paid filter first, as it is one line. **Decided:** did it fourth — a wrong filter is visible, a payment landing on another customer is silent and moves money. **Checked:** the changed-input case showed the overview total is identical either way, confirming users could not catch that one by eye.
2. **Suggested:** number rejected rows with `enumerate(rows, 2)`, as the starter did. **Decided:** rejected; used `DictReader.line_num`. **Checked:** `enumerate` counts parsed rows, so one blank line shifts every later number and points the owner at the wrong row.
3. **Suggested:** format the export with `f"{value:.2f}"`. **Decided:** kept, but also rounded `amount`, `paid` and `balance` in `reporting.invoices`. **Checked:** formatting only the CSV would leave the API returning `-10.000000000000002` while the CSV said `-10.00`; the rule is that both agree, so the rounding belongs where both read from.
