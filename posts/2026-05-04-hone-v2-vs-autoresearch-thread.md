ran hone v2 against autoresearch across 3 information-matched rounds of drone controller optimization. both got the same scorer, seed split, model, and 100 iterations per lane. here's how it went 🧵

—

setup: 5 lanes per round, 100 iterations each, pi + gpt-5.5 as the mutator. hone does global frontier search; autoresearch runs a local edit-and-score loop. validation on fresh heldout seeds neither approach saw during training. the round winner seeds the next round — each round starts from a live champion.

—

round 1: AR wins. best single heldout controller: AR E04, validation 1.0244. AR E04 seeds round 2.

—

round 2 (seeded from E04): hone sweeps 5-0 pairwise. AR overfit hard — AR04/AR05 hit ~1.148 on training and fell below 0.89 on heldout. hone's equivalent lanes: trained 1.097/1.089, validated 0.953/1.003. best single: hone H05, 1.0026.

—

round 3 (seeded from H05): AR comes back, 3-2 pairwise. but the best individual score in the whole experiment came from hone — H01 trained to 0.933 and validated at 1.0453. AR wins more lanes; hone found the peak.

—

combined R2+R3 (10 lanes): AR 9.500 vs hone 9.462. AR 0.038 ahead. hone has more variance, hit the biggest highs in 2 of 3 rounds after v1; AR is more consistent lane to lane. neither has a clear edge.

—

L3 challenges are still hard for both. the gains here are in L1/L2 space.

next step is probably hone outer frontier + autoresearch-style workers doing local search inside the frontier nodes.

—

full controllers + logs: github.com/twaldin/hone-a-drone
