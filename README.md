# ClearLedger — Track A submission

Repair of the ClearLedger invoice register for the Mystri applicant assessment.
Six seeded defects were investigated, reproduced and fixed, each with a regression
test written before the fix, plus one improvement beyond the required repairs.

- **Submitted by:** Akshay · Track A
- **Full write-up:** [HANDOVER.md](HANDOVER.md)
- **Intended behaviour (supplied):** [BUSINESS_RULES.md](BUSINESS_RULES.md)
- **Original task brief (supplied, unchanged):** [TRACK_A_BRIEF.md](TRACK_A_BRIEF.md)

Python 3.10+ only. No third-party dependencies were added.

## Quick start

```text
python -m unittest discover -s tests -v     # 34 tests
python restore_fixture.py --replace         # load the owner's existing register
python app.py                               # http://127.0.0.1:8787
```

Use `py` instead of `python` on Windows if needed. Stop the server with Ctrl+C.
`restore_fixture.py` must run with the server stopped. For the fresh six-invoice
demo instead, run `python app.py reset-demo` and start the app again.

## What was broken and what changed

| # | Symptom the owner sees | Cause | Fix |
| --- | --- | --- | --- |
| 1 | Payments credited to the wrong customer | `find_invoice` matched any invoice with an equal amount | `ledger/matching.py` matches on customer **and** invoice number only |
| 2 | Totals move again when an import is retried | `insert_invoice` always inserted | Identical rows are skipped; a reused identity with different details is rejected |
| 3 | "Import complete" but no records | One invalid row aborted the whole file | Rows are validated in the insert loop; each rejection carries its CSV line and reason |
| 4 | Open list disagrees with the overview | `status=open` filtered for `paid` | The filter compares against the requested status |
| 5 | Export disagrees with the screen | `int(x * 100) / 100` truncated 19.99 to 19.98 | Money is reported at currency precision and the reported value is formatted |
| 6 | A failed import still says it worked | The page ignored the response | The page checks `response.ok` and shows the real counts, lines and reasons |

**Improvement — download rejected rows.** A partial import also returns a
`rejected_csv` field: the failed rows in their original columns plus `line` and
`reason`. The page offers it as a download, so the owner corrects that small file
and re-imports, which is safe because fix 2 skips the rows that already landed.

Public routes and response fields from `BUSINESS_RULES.md` are unchanged; the only
addition is the `rejected_csv` field on import responses.

## Verify it

```text
python -m unittest discover -s tests -v      # 34 tests pass
python scripts/changed_input_demo.py         # changed-input case, see HANDOVER.md
```

The same tests against the untouched starter commit fail 18 times:

```text
mkdir ..\clearledger-before
git archive 0843232 | tar -x -C ..\clearledger-before
xcopy /E /I tests ..\clearledger-before\tests
cd ..\clearledger-before
python -m unittest discover -s tests
```

`tests/test_existing_register.py` covers the supplied register: it checks every
identity, amount, due date and payment allocation against
`fixtures/expected-records.json`, imports a new invoice and payment, reopens the
database as a restart would, and re-checks both old and new records. It works on a
temporary copy, so `fixtures/` is never modified.

## Repository map

| Path | Contents |
| --- | --- |
| `app.py` | Startup and the `reset-demo` command |
| `ledger/` | Validation, storage, importing, matching, reporting, HTTP routes |
| `web/` | Browser interface (plain HTML, CSS, JavaScript) |
| `tests/test_smoke.py` | Supplied smoke checks |
| `tests/test_regression.py` | One reproduction per defect, plus the improvement |
| `tests/test_http_api.py` | The public routes over real HTTP |
| `tests/test_existing_register.py` | The owner's register survives imports and a restart |
| `scripts/changed_input_demo.py` | The changed-input case from the handover |
| `fixtures/`, `samples/` | Supplied data, unchanged |

Commit history runs one defect per commit, starting from the untouched starter at
`0843232`, so each fix can be read next to the test that proves it.
