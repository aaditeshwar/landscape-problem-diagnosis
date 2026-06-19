# Evidence card review workflow (low effort)

Review **unique rows** in these CSVs once; changes propagate to all cards sharing the same fingerprint.

## 1. Unique signals — `review_unique_signals.csv`

Each row is a distinct signal **expression + qualitative description + variables + direction** pattern across clusters.

- Sort by `card_count` descending — fix high-impact rows first.
- Edit one `example_card_id` in the signal editor (or raw JSON), then run maintenance scripts to mirror if needed.
- Rows with empty `expression` are qualitative-only follow-up signals — review `qualitative_excerpt`.

## 2. Unique follow-ups — `review_unique_follow_ups.csv`

Each row is a distinct MCQ template: variable + question_mode + choice normalized/effects fingerprint.

- Check `choice_summary` (choice id → effect result). `None` means no explicit `effects.signals` (runtime falls back to prose inference).
- Align `how_answer_updates_diagnosis` prose on the example card with `effects` (prose is display-only; effects are enforced).

### 2b. Propagate reviewed follow-ups

After editing `choice_summary` in the CSV (or the example card JSON):

```powershell
.\.venv\Scripts\python.exe scripts/maintenance/propagate_follow_up_templates.py
.\.venv\Scripts\python.exe scripts/verify/audit_follow_up_effects.py --write-report
.\.venv\Scripts\python.exe scripts/verify/audit_mcq_normalized.py
.\.venv\Scripts\python.exe scripts/reload_evidence_cards.py
```

| Target | What gets updated |
|--------|-------------------|
| `data/evidence_cards/raw/*.json` | All cards sharing each template fingerprint |
| `metadata/reviewed_follow_up_by_fingerprint.json` | 30 canonical MCQ templates |
| Mongo `evidence_cards` | Via reload script |

## 3. Unique policies — `review_unique_policies.csv`

Each row is a distinct `confirmation_policy` JSON shape.

- Compare `note_excerpt` (LLM prose) vs `draft_note` (auto-generated from policy + signals).
- Auto prose lists primary confirms, amplifiers, and follow-up variables — it **does not** capture rich hydrogeological context, confounders, or intervention framing in the LLM note.
- After approving a policy row, update `overall_reasoning_note` manually or keep LLM note as supplemental context and add a one-line “Executable policy: …” prefix.

### 3b. Propagate reviewed policies

After editing `metadata/policy_corrections.json` or approving rows in the policy CSV:

```powershell
.\.venv\Scripts\python.exe scripts/maintenance/apply_policy_corrections.py
.\.venv\Scripts\python.exe scripts/verify/audit_confirmation_policy.py --write-report
.\.venv\Scripts\python.exe scripts/reload_evidence_cards.py
```

| Target | What gets updated |
|--------|-------------------|
| `data/evidence_cards/raw/*.json` | Cards matching fingerprint or `by_card_id` overrides |
| `metadata/reviewed_policy_by_fingerprint.json` | Canonical policy templates per fingerprint |
| Mongo `evidence_cards` | Via reload script |

## 4. Audits (run after edits)

```powershell
.\.venv\Scripts\python.exe scripts/verify/audit_confirmation_policy.py --write-report
.\.venv\Scripts\python.exe scripts/verify/audit_follow_up_effects.py --write-report
.\.venv\Scripts\python.exe scripts/verify/audit_mcq_normalized.py
```

## 5. Reload Mongo

```powershell
.\.venv\Scripts\python.exe scripts/reload_evidence_cards.py
```

## Prose: auto-generate vs keep LLM note

| Keep in LLM `overall_reasoning_note` | Safe to auto-generate |
|--------------------------------------|------------------------|
| Agro-climatic / AER context | Primary signal list |
| Confounders and alternatives | Min confirms count |
| Intervention framing | Amplifier list |
| Nuanced “when not to confirm” | Linked follow-up variable names |

Recommendation: treat **policy + effects** as source of truth; use `draft_note` as a **checklist** and retain LLM prose for context below a short policy summary.
