# Trace case: ticket fact overrides the database

Reproduce the failing and corrected runs from `src/`:

```bash
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
```

| Field | Observation |
|---|---|
| Trial | `seeded_regression C-002@11`, report `E-seeded_regression-20261117-e108` |
| Symptom | Lab 8 grader fails with `status resolved != denied`; the ledger has a 20,000đ refund while the label expects 0. |
| First incorrect step | Event 3, `model_override`: the ticket's 5-day delay replaces the database value of 2 days. |
| Why it is first | The handoff and investigator lookup are valid. The DB value is present at event 2; only after that does the model override it. The quote, refund, and reply follow the corrupted value. |
| Failure mode | FM-03 `ticket_trust`. |
| Corrected comparison | `fixed C-002@11` keeps the 2-day DB value, quotes 0, returns `denied`, and leaves the ledger at 0. |
| Regression checks | `tests/test_swarm_reference.py::test_reference_weakness_is_visible_on_public_t02` verifies the reference weakness at seed 55; `tests/test_lab9_graders.py::test_override_event_breaks_db_fact` verifies the trajectory grader rejects an override event. |
| Limitation | The case proves the ticket/DB disagreement on this deterministic mock trace; it does not estimate how often a live model would make the same mistake. |

The key is to inspect the DB lookup before the reply: the first bad decision is event 3, not the later refund or user-facing text.
