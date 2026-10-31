# Benchmark Pre-registration Template

Commit this file, filled in, **before** running any sealed-set evaluation. Do not edit after the first sealed run; add dated amendments instead.

## 1. Metadata
- Study ID:
- Date committed:
- Authors:
- Tool version / git commit:
- Sealed-set manifest hash:

## 2. Research questions and hypotheses
For each, state the direction in advance.

| ID | Question | Hypothesis | Primary metric |
|---|---|---|---|
| H1 | | | |

## 3. Data
- Corpus sources and consent basis:
- Number of sessions/tasks (dev / sealed):
- Inclusion and exclusion rules:
- Annotation procedure and annotator agreement threshold:

## 4. Conditions and baselines
List every condition (no context, raw transcript, naive summary, each competitor with version and config, this tool, human note). Attach configs.

## 5. Models and settings
Downstream models (name, version, parameters), number of repeats, seeds.

## 6. Metrics
Primary and secondary metrics, how each is computed, and how failures/timeouts are counted.

## 7. Statistical analysis plan
- Tests used (e.g. McNemar, Wilcoxon):
- Confidence interval method:
- Multiple-comparison correction:
- Power analysis (assumed effect size, resulting n):
- Stopping rule:
- Handling of missing or invalid runs:

## 8. Claim wording
For each hypothesis: the exact sentence that will be published if supported, and the sentence if not supported.

## 9. Deviations
Dated amendments only.
