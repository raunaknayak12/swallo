# Benchmarks and Evaluation Plan

**Status:** Draft v0.1. No benchmark has been run. Every number in future publications must come from a recorded run.

## 1. Principles

1. **Grounded over planted.** Headline results use messy, real, human-labelled data. Planted fixtures remain as regression tests, not headlines.
2. **Pre-registered.** Hypotheses, metrics, analysis and claim wording are committed before sealed-set runs (`templates/PREREGISTRATION.md`).
3. **Sealed test set.** Split before development; commit a hash of the file list; run once at the end.
4. **Reproducible.** Pinned versions, fixed seeds, environment manifest, raw logs published.
5. **Honest scope.** Each result states what it shows and what it does not.
6. **Any outcome is publishable**, including no difference.

## 2. Corpus governance

- Sources: the author's sanitized sessions, consenting volunteers, and public datasets after license and privacy review.
- Include coding sessions and multi-session scenarios with real requirement changes.
- Before storage: scanner pass plus manual redaction audit; record consent.
- Ground truth: two annotators label decisions, constraints, secrets and conflicts independently (`templates/ANNOTATION_GUIDE.md`); report agreement (Cohen's kappa) and adjudicate disagreements.
- Split: development set and sealed test set; sealed set access-controlled; publish hash manifests and derived metrics, not transcripts.

## 3. Phases

### Phase 1: safety, speed, consistency (free, deterministic)

| Test | Method | Metrics |
|---|---|---|
| Secret redaction | Run this tool, gitleaks and trufflehog on the same real transcripts; score against human labels; scan store, log, temp files and errors | Recall, precision per category; misses listed |
| PII redaction | Compare with Presidio on the same set | Per-entity recall and precision |
| Injection handling | Payload fixtures through render; fence-breakout fuzz | Escape rate (target zero) |
| Latency and throughput | Save/load/merge over the real size distribution, cold and warm | p50/p95, memory, hardware manifest |
| Setup friction | Fresh container, steps and minutes to first handoff, vs competitors where installable | Minutes, step count |
| Determinism | Repeat saves/renders; merge in both orders | Byte-identical rate; order invariance |
| Staleness | Temp git repos with change, rename, delete, no-change cases | Warning precision/recall |
| Evasion variants | Seeded secrets transformed (split literals, base64, hex, URL-encoded, reversed, zero-width) and run through redaction, plus decode-bomb inputs | Recall per transform; time and memory under decode bombs |
| Guard behavior | 500-call save loop, identical-payload dedupe, quota fill with CLI saves still working, breaker persistence across restarts, TTL safety | Store growth, response codes, recovery time |
| Stale policy | Unrelated commit, modified/renamed/deleted referenced file, rebase, acknowledgment expiry | Block precision and recall (no false blocks on unrelated commits) |

### Phase 2: fidelity

- Fact fidelity: share of human-labelled decisions/constraints present in the packet (and in competitors' outputs).
- Unsupported items: packet items not supported by the transcript (provenance spans enable checking; human spot-check a sample).
- Conflict handling: labelled real conflicts versus updates versus hard negatives; precision and recall with counts.

### Phase 3: does the next agent do better?

Design: take a real session, cut it at a point, and have a downstream agent continue using only the handoff.

Conditions (same tasks, same downstream model, same seeds):
1. No context
2. Full raw transcript
3. Naive "summarize this chat" prompt
4. Each competitor tool, configured per its own documentation
5. This tool
6. Human-written handoff note (gold reference)

Task types:
- **Question tasks:** questions answerable only from earlier context, graded against the human key.
- **Coding continuation tasks:** a task that needs an earlier constraint, decided by an existing test suite (no model judge). SWE-bench-style tasks may supplement.

Metrics: pass rate, constraint violations, turns to green, input tokens, wall time, cost. Always report tokens next to success.

Statistics: paired tests (McNemar for pass/fail; Wilcoxon for continuous), bootstrap confidence intervals, effect sizes, multiple-comparison correction, a power analysis before running, repeats to measure model variance, blind grading if any judge is used. Use at least two downstream models. Small differences need many tasks.

### Phase 4: fair competitor comparison

Compare only on scenarios both tools support; publish configs and versions; invite maintainers to review configs; pin model versions; date all results; schedule re-runs.

### Phase 5: human study

Within-subject, counterbalanced order, with and without the tool; measure completion time, correctness and a standard usability scale; informed consent; careful data handling.

## 4. Extra dimension: capture method

Report fidelity and downstream results split by `capture_method` (`export`, `paste`, `connector`, `ide-agent`).

## 5. `swallo bench` and results format

`swallo bench run [--phase N] [--seed S]` writes `results.json`:

```json
{
  "tool_version": "0.x.y",
  "schema_version": "0.1",
  "git_commit": "...",
  "seed": 1234,
  "environment": {"os": "...", "python": "...", "cpu": "...", "memory_gb": 0},
  "models": [{"name": "...", "version": "...", "settings": {}}],
  "fixtures": {"manifest_sha256": "...", "count": 0, "split": "dev|sealed"},
  "results": [{"test": "redaction_recall", "n": 0, "value": 0.0, "ci": [0.0, 0.0]}],
  "logs": "raw/"
}
```

`swallo bench verify results.json` checks the manifest hashes and recomputes deterministic results. Phase 3 results are re-run by volunteers on their own setups and submitted as files.

## 6. Cost control for Phase 3

Run a pilot to estimate cost (tasks x conditions x repeats x tokens). Use local models for bulk runs and a hosted model for a smaller confirmation. Check free-tier limits before relying on them. Accept volunteer-contributed runs on their own subscriptions.

## 7. Claims policy

| Evidence | Claim allowed |
|---|---|
| Phase 1, sealed set | "Redacts X% of labelled secrets versus Y% for gitleaks", latency numbers, determinism |
| Phase 2 | "Preserves N% of human-labelled decisions" |
| Phase 3, CI excludes zero, sealed set, at least two models | "Improves task success over [named tool] on these tasks" |
| Phase 5 | "Developers finished faster/with fewer errors in this study" |

"Better than other tools" requires Phase 3 and Phase 4. Without them, do not say it.

## 8. Threats to validity

- Models, competitors and vendor formats change quickly; results are dated.
- The author's own sessions may not represent others; volunteer data and held-out sets mitigate this.
- Rule-based conflict detection scores depend on fixture difficulty; publish hard negatives.
- Approximate token counts for non-OpenAI models.
- Local small models are noisy and may not predict hosted-model behavior.
- A reproducible result is not automatically a valid one; external review and contributed fixtures are part of the design.
