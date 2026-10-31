# Annotation Guide

Purpose: create human ground truth for decisions, constraints, secrets and conflicts in real transcripts. Two annotators label each session independently.

## 1. General rules
- Label from the transcript only. Do not use outside knowledge.
- When unsure, mark `uncertain` and note why; do not guess.
- Work offline on redacted data; never copy transcript text into other tools.

## 2. Labels

### Decisions
A statement where the participants chose or agreed on a course of action. Not a suggestion that was rejected. Record: span (start/end), short normalized text, topic (if obvious), value (if obvious).

### Constraints
A requirement or limit that must hold (technical, legal, business). Mark `critical` if breaking it would invalidate the work.

### Open questions
Questions raised and not answered by the end of the session.

### Secrets and PII
Mark spans for credentials, tokens, keys, connection strings, passwords (including those in prose), emails, names, phone numbers, addresses, account numbers. Record category per span. Mark whether it is real-looking or clearly a placeholder.

### Conflicts (multi-session)
For each pair of sessions mark relations between items: `conflict` (cannot both hold), `update` (later replaces earlier, explicitly), `compatible`, or `unrelated`. Include hard negatives: similar-looking items that are compatible.

## 3. Output format
One JSON file per session: list of labelled items with `type`, `span`, `text`, `topic`, `value`, `critical`, `category`, `notes`, `annotator_id`.

## 4. Quality control
- Compute Cohen's kappa per label type on a shared subset; pause and revise this guide if agreement is low.
- Disagreements are adjudicated by a third reviewer; record the final label and reason.
- Keep a changelog of guideline updates with dates.

## 5. Ethics and privacy
Confirm consent for each transcript. Remove or mask personal data not needed for the task. Store annotations separately from raw data with restricted access.
