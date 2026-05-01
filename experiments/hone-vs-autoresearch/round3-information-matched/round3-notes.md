# Round 3 information-matched drone notes

All lanes start from the same Round 2 heldout winner: Hone H05, validation aggregate 1.0026100374804507 on seeds 31-40.

Round 3 split:
- train scorer: levels 0-3, seeds 41-50
- heldout validation: levels 0-3, seeds 51-60
- budget: 100 meaningful optimization scorer calls/iterations per lane

What transferred from Round 2:
- H05 had lower train than AR04/AR05 but much better heldout validation.
- AR04/AR05 reached ~1.148 train by obstacle/offset tuning but validated below 0.89, so be suspicious of aggressive train-only obstacle-radius/offset changes.
- Robust L0/L1 completion and improved L2 transfer matter more than tiny train gains.
- L3 remains the hard bottleneck; current best usually only gets about 0.025 on L3. Do not wreck L0/L1/L2 chasing L3 unless scorer evidence is strong.

Useful search directions:
- Preserve the H05 controller structure and robust timing unless a scorer trace clearly indicates otherwise.
- Try small, localized changes to path timing, approach/exit staging, gate correction windows, obstacle avoidance thresholds, and vertical/liftoff staging.
- Prefer changes that improve L2 without making L0/L1 slower or unstable.
- Avoid hardcoding train/validation seed numbers or level-specific seed hacks.
