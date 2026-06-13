# Prompt Analysis and Revision Notes

## Ollama (qwen2.5:14b) vs Claude Sonnet 4.6

---

## 1. What the Current Prompt Does Well

- **Clean separation of concerns**: location context, variable values, pathway bundles, and task
instructions are clearly delimited with bracketed headers. Any model can parse these.
- **Explicit confirmation logic**: the evidence notes state exactly how many signals are
needed and in what combinations, removing ambiguity that would expose a weaker model.
- **Anti-hallucination guards**: Task rules 4 and 7 explicitly prohibit asking for variables
already in `present_variables`, and the note says never include `panel_updates`. These
guardrails are necessary for Qwen but also harmless for Claude.
- **Structured output schema**: the exact JSON skeleton is given, reducing formatting errors.
- **Confounder framing**: providing `how_to_distinguish` for each confounder helps weaker
models avoid the most common false-positive errors.

---

## 2. What the Ollama Prompt Over-Provides for Claude

Everything in the `Diagnostic signals` blocks — `expression`, `explanation`,
`threshold_confidence`, `context_sensitivity`, `interaction_with` — is essentially
a distilled knowledge base that compensates for Qwen's limited domain knowledge.
Claude already knows:


| Encoded in prompt                                     | Claude's prior knowledge                                   |
| ----------------------------------------------------- | ---------------------------------------------------------- |
| "soge_dev_percent > 70 confirms stress"               | CGWB SOGE classification (Safe/Semi-critical thresholds)   |
| "crystalline_basement has low storativity"            | Hard rock aquifer hydrogeology in peninsular India         |
| "dist_bank_km > 10 → moneylender dependence"          | Rural finance exclusion and debt-trap literature           |
| "village_st_percent > 10 + FRA backlog → access loss" | Forest Rights Act 2006 and tribal NTFP rights              |
| "cropping_intensity ≤ 1.15 → rainfed dependence"      | Agronomic interpretation of CI in semi-arid India          |
| "Banded Gneissic Complex 100%"                        | Crystalline basement geology of Deccan/Eastern Ghats       |
| "drought_weeks_severe = 8 in 2023"                    | What constitutes a drought year under India Drought Manual |


Sending all of this to Claude adds ~8,000–10,000 tokens of context per query for no
accuracy gain, and may actually *reduce* response quality by diluting Claude's attention
and anchoring it to the evidence card's wording rather than letting it reason freshly.

---

## 3. Issues in the Current Prompt (Both Models)

### 3a. `trend_annual_delta_g_mm` is a pre-computed field not in the data dictionary

`trend_annual_delta_g_mm: -15.0555` appears in the groundwater pathway variables but
is not a raw variable — it's a linear trend slope pre-computed by the assembler. This is
useful but should be labelled clearly as a derived/computed value so the model understands
it represents the average annual change in delta_g rather than a single year's value.

### 3b. The TASK section is 7 rules but rules 3 and 4 partially overlap

Rule 3 says to mention the MWS UID and village names; rule 4 says not to ask for
present_variables. These are fine but rule 4 is more critical and could be phrased
more sharply. For Qwen specifically, rule 4 violations (asking for already-present
variables) are the most common failure mode in testing.

### 3c. `panel_updates` exclusion is unnecessarily cryptic

"panel_updates chart keys are assigned server-side" — this is implementation detail
that neither model needs to know. A simpler instruction ("do not include a
`panel_updates` field in your JSON") is clearer and removes a potential source of
confusion where Qwen might try to generate chart key strings anyway.

### 3d. The output schema comment `"..." or null` is ambiguous

For `panel_update_explanation` and `follow_up_question`, the schema shows
`"..." or null`. Qwen has been observed to output the literal string `"..."` rather
than null when it has nothing to say. Use `null` as the explicit example.

---

## 4. Improvements Specific to the Ollama Prompt

1. **Add explicit numeric evaluation instructions** before the pathway blocks:
  ```
   For each pathway, evaluate each signal expression against the variable values
   provided above. State whether each expression evaluates to TRUE or FALSE.
   Then apply the evidence note confirmation logic.
  ```
   Qwen is significantly more reliable when instructed to work step-by-step before
   producing the final JSON. This can be done in a scratchpad block that is excluded
   from the final output, or as an internal chain-of-thought instruction.
2. **Shorten signal blocks**: the `sources_cited` field and the `interaction_with`
  cross-references add length without helping a 14B model. Remove them from the  
   prompt and keep only `signal_id`, `condition.expression`, `direction`, and a  
   one-sentence `explanation`.
3. **Make the JSON output constraint harder**: end the prompt with:
  ```
   IMPORTANT: Output ONLY the JSON object. No preamble, no explanation, no markdown
   fences. The first character of your response must be '{' and the last must be '}'.
  ```
4. **State the confidence calibration rule explicitly** for Qwen:
  ```
   Use confidence=high only when ≥2 signals evaluate to TRUE.
   Use confidence=medium when exactly 1 signal evaluates to TRUE.
   Use confidence=low when no signal evaluates to TRUE but the pathway is plausible
   from context.
  ```

