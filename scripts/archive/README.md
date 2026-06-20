# Archived scripts

One-off migrations already applied to the corpus. Kept for re-importing pre-migration card JSON only.

Run from repo root:

```powershell
.\.venv\Scripts\python.exe scripts\archive\maintenance\<script>.py [args]
```

| Script | Applied |
|--------|---------|
| `maintenance/add_signal_active_flag.py` | Plan 11 — `active: true` on all signals |
| `maintenance/migrate_plan13_follow_ups.py` | Plan 13 — `question_mode` + `effects` from MCQ templates |
