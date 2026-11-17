# Judge audit

Commands:

```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```

| Criterion | n | κ | Precision | Recall | Floors κ≥0.6, P≥0.8, R≥0.7 | Decision |
|---|---:|---:|---:|---:|---|---|
| `tone_ok` | 100 | 0.757 | 0.857 | 0.800 | Pass | Usable only as a secondary tone signal |
| `helpful` | 100 | 0.375 | 1.000 | 0.300 | Fail | Reject; it misses most human-labelled failures |

Observed failure rate is 0.280 for tone and 0.090 for helpful. Rogan–Gladen correction gives 0.300 for each; the helpful estimate is not trustworthy because the judge fails calibration.

## Manual review of tone disagreements

| Case | Judge / human | Review |
|---|---|---|
| H-008 | PASS / FAIL | Human is right: “em … nha” is too familiar for the customer-service voice. |
| H-017 | PASS / FAIL | Human is right: “bạn ơi … nha” is overly familiar. |
| H-029 | PASS / FAIL | Human is right: “không cần nhắn thêm” sounds commanding. |
| H-042 | FAIL / PASS | Human is right: the response is polite; the judge over-penalizes it. |
| H-051 | FAIL / PASS | Human is right for tone: the English word “refund” is a wording issue, not impoliteness. |

## Manual review of helpful disagreements

| Case | Judge / human | Review |
|---|---|---|
| HL-015 | PASS / FAIL | Human is right: reply says 55,000đ while the ledger note says 40,000đ. |
| HL-016 | PASS / FAIL | Human is right: reply says 55,000đ while the ledger note says 35,000đ. |
| HL-020 | PASS / FAIL | Human is right: reply says 90,000đ while the ledger note says 120,000đ. |
| HL-028 | PASS / FAIL | Human is right: reply says 50,000đ while the ledger note says 35,000đ. |
| HL-035 | PASS / FAIL | Human is right: reply says 50,000đ while the ledger note says 35,000đ. |

The helpful replay judge is not used for release decisions. Its perfect precision does not compensate for 21 false negatives. The tone judge clears the public floors, but its disagreements show that it should remain advisory until evaluated on a new, held-out human-labelled set.
