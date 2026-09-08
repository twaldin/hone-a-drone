# ROADMAP — Dynamic Pointing

This is the historical dynamic-pointing proposal, not an implemented scheduler or a current status report. The initial v1 plan evolved a single file, `controllers/planner.py`, to validate the hone→grader→mutator loop on a proxy sim before adding scheduling machinery. Later experiment records live in [experiments/hone-vs-autoresearch/](experiments/hone-vs-autoresearch/) and [posts/](posts/); the committed legacy demo still targets the planner, while the grader also accepts a controller directory.

The progression and decision rules below are preserved as design research. No `hone-a-drone diagnose` command or autonomous rotation scheduler is tracked here. The current simulator-observation adapters also do not expose the proposed vision-dropout diagnosis.

## The core risk when pointing at multiple modules

Modules aren't independent. If you evolve `planner.py` to be more aggressive, the attitude controller may not keep up, and the next round of eval will score the planner as crash-heavy — but the planner isn't the problem, the downstream module is. If you don't rotate, you end up conservatizing a fine planner to compensate for a broken module, which is backwards.

Two hard rules whenever the mutation target rotates:
1. **Freeze the previous module at its best checkpoint, not revert.** The whole stack has been improving together; don't throw that away.
2. **When a rotation doesn't produce the expected gain, the first question is "is this module actually the bottleneck, or is something else making it look bad?"** That's what the diagnose step below is ultimately protecting against.

## Progression (in order of when to build)

### Level 0 — Manual rotation
You eyeball `runs/*.csv`, notice 80% of crashes are vision-dropout in fast turns, manually point the next `hone run` at `gate_detector.py`. Five minutes of human judgment per rotation, highest leverage per hour of engineering work.

### Level 1 — Bottleneck-diagnosis wrapper (`hone-a-drone diagnose`)
Small script that reads the last run's per-rollout logs and classifies failure modes:
- crashed-on-approach
- overshot-gate
- vision-dropout
- control-loop-timeout

Each failure mode maps to a module. Prints `bottleneck: gate_detector (62% of failures)` and suggests the hone command. Still human-in-the-loop but removes the eyeballing step.

### Level 2 — Multi-module hone via GEPA's scope selection
The original GEPA-backed hone design proposed multi-artifact optimization: pass `{"planner": planner_code, "state_estimator": state_code, ...}` and select which artifact to mutate using Pareto reasoning. It referenced hone's `custom_candidate_proposer` hook. Preserve this as a design direction, not a current hone API recipe; the upstream CLI and architecture have since changed (see [README.md](README.md#setup-and-command-status)).

### Level 3 — Autonomous rotation meta-loop
`diagnose` becomes the scheduler: run N iterations on the current bottleneck, read results, pick next module, repeat. Walk away for a weekend, come back to a rotated, more-mutated stack. Full rotations are expensive, so every sub-loop needs to be well-tuned before this is worth it.

## When to start caring

The original sequencing rule still captures the tradeoff: establish a working single-module baseline and measurable improvement on the proxy sim before investing in rotation machinery. The dated experiment records document subsequent work; deciding whether those results justify a scheduler is separate from documenting what is implemented.
