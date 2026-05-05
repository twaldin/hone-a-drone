# Round 2 Information-Matched 5v5 Summary

Seed controller for all lanes: Round 1 validation winner E04 (`seed-e04`).
Train split: seeds 21-30. Heldout validation split: seeds 31-40.
Budget: 100 optimization scorer calls/iterations per lane, plus baseline for autoresearch logs.
Agent/model: `pi + openai-codex/gpt-5.5`.

## Results

| Pair | AR train best | AR validation | Hone train best | Hone validation | Validation winner |
|---|---:|---:|---:|---:|---|
| 01 | 1.216669777888 | 0.921012963363 | 1.0950 | 0.947117529452 | Hone |
| 02 | 1.0957 | 0.880405237514 | 1.1168 | 0.907648692050 | Hone |
| 03 | 1.099400000000 | 0.951041348368 | 1.0970 | 0.953267948164 | Hone |
| 04 | 1.147500000000 | 0.882529910848 | 1.0973 | 0.953354057445 | Hone |
| 05 | 1.148480032332 | 0.889795730381 | 1.0891 | 1.002610037480 | Hone |

## Headline

Hone won all five Round 2 heldout validation pairs:

```text
Hone 5 - 0 Autoresearch
```

Autoresearch had the strongest training scores in pairs 01, 03, 04, and 05, but those gains did not transfer to heldout validation. The clearest overfit examples are AR04/AR05: both reached ~1.148 train and validated below 0.89, while Hone H04/H05 validated at 0.953 and 1.003 respectively.

Best Round 2 heldout controller by validation:

```text
H05 / Hone final-form: 1.0026100374804507
```

## Validation logs

- `ar03-validation-31-40.txt` / `h03-validation-31-40.txt`
- `ar04-validation-31-40.txt` / `h04-validation-31-40.txt`
- `ar05-validation-31-40.txt` / `h05-validation-31-40.txt`
- Pair 01 and Pair 02 summaries are in this directory as earlier round2 summaries.

## Clean controller copies

- `outputs/autoresearch-r2-info-03-clean/`
- `outputs/hone-r2-info-03-clean/`
- `outputs/autoresearch-r2-info-04-clean/`
- `outputs/hone-r2-info-04-clean/`
- `outputs/autoresearch-r2-info-05-clean/`
- `outputs/hone-r2-info-05-clean/`
