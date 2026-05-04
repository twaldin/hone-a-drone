## hone v2 vs autoresearch: three rounds, split result

I wanted to know whether Hone's frontier-based search or an autoresearch-style local edit loop produces better drone controllers, so I ran three rounds of head-to-head benchmarks using identical scorer, seed split, model, and 100 iterations per lane.

Each round had five lanes. Within each lane both Hone and Autoresearch got the same seed controller, the same training seeds, the same mutation model (pi + gpt-5.5), and 100 iterations. Fresh heldout seeds — never seen during training — picked the winners. The competition ran in product mode: the validation winner of each round seeded the next. Round 1 winner AR E04 seeded Round 2; Round 2 winner Hone H05 seeded Round 3.

| Round | Best single winner | Heldout validation | Pairwise |
|---|---|---|---|
| R1 | AR E04 | 1.024435755505 | — |
| R2 | Hone H05 | 1.0026100374804507 | Hone 5-0 |
| R3 | Hone H01 | 1.0452952657513928 | AR 3-2 |

Round 2 was the cleaner result. Autoresearch reached training scores around 1.148 in lanes 04 and 05 and validated at 0.883 and 0.890 — overfit on both. Hone's equivalent lanes trained to 1.097 and 1.089 and validated at 0.953 and 1.003. The overfit was consistent across all five AR lanes; Hone improved on heldout in every one.

Round 3 reversed the pairwise count. AR won lanes 02, 03, and 05 with heldout validation scores of 0.983, 0.965, and 1.036. Hone's losses in those lanes scored 0.935, 0.788, and 0.915 — the 0.788 in lane 03 is a real miss. But Hone H01 trained to only 0.933 on the training split and validated at 1.0453, the highest individual score across all three rounds.

Over R2 and R3 combined, the 10-lane heldout validation sums are AR 9.500 vs Hone 9.462 — AR ahead by 0.038. Hone hit bigger peaks in two of three post-v1 rounds; AR was more consistent across lanes.

One thing worth stating plainly: L3 challenges — the hardest tier in the benchmark — are still reliably hard for both methods. The gains in all three rounds are concentrated in L1 and L2 space. Don't read this as a solved problem.

The natural next step is combining both. Hone's outer frontier search to identify strong regions of controller space, with bounded autoresearch-style workers doing numeric local search inside those regions. Running them in isolation was the right way to measure each; the ceiling is probably higher if they're stacked.

Full controllers and run logs: github.com/twaldin/hone-a-drone.
