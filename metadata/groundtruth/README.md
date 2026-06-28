# Ground truth field collection

Structured JSON for collecting **pathway ground truth** from landscape stewards and field enablers.

## Files

| File | Purpose |
|------|---------|
| [groundtruth_collection_form.json](./groundtruth_collection_form.json) | Form schema: hierarchy + MCQ options |
| [groundtruth_response_template.json](./groundtruth_response_template.json) | Empty response skeleton to copy per MWS visit |

## Hierarchy

Each response walks this tree:

1. **Production system** (yes / no / don't know)  
2. **Observed stress** (shown when production system = yes)  
3. **Causal pathway** (shown when stress = yes)  
4. **Follow-up MCQs** (shown when pathway = yes; only for pathways with evidence cards)

Pathways with `has_evidence_cards: true` match compiled evidence cards in `data/evidence_cards/raw/`. Other framework pathways are included for completeness but have no follow-up questions yet.

## Location fields

Collect before the hierarchy:

- `mws_uid` (required)  
- Village, state, district, tehsil  
- Collector name, organisation, date, free-text notes  

## Regenerate after framework or card changes

```bash
.venv/Scripts/python.exe scripts/maintenance/build_groundtruth_form.py
```

Sources: `metadata/diagnosis_framework.json`, evidence cards, `runtime/services/follow_up_mcq.py`.

## Using responses for tuning

Positive pathway labels (`present: "yes"`) can feed `metadata/case_study_locations_*.json` and automated tuning (`scripts/tuning/tune_pathway_signals.py`). Follow-up `choice_id` values align with diagnosis MCQ injection in the runtime API.
