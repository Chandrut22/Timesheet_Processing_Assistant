# Attachment classifier (Jev by TypeSafe): optional, off by default

After a file is read, and before the AI extraction, the worker can ask Jev: *"is this a
timesheet?"*. If Jev is **very sure it is not one**, the AI extraction is skipped. That
saves time and cost on invoices, payslips and other attachments.

```
read file (Docling) ──► classify (Jev) ──► AI extraction ──► match ──► rules ──► decide
                          │
                          └─ label ≠ timesheet AND P(timesheet) < 0.2 → skip, say why
```

## Safety rules (built in and tested)

A wrongly skipped timesheet means hours that don't get paid, so:

| Situation | What happens |
|---|---|
| `CLASSIFIER_ENABLED=false` (the default) | Nothing changes; no call to Jev |
| Shadow mode (`CLASSIFIER_SHADOW_ONLY=true`, the default when enabled) | Jev is asked and the answer is logged ("would skip"), but **everything is extracted** |
| Label `timesheet` | Extracted |
| Label `unclear` | Extracted |
| P(timesheet) ≥ threshold | Extracted |
| P(timesheet) **not in the answer** | Extracted (a format we don't understand never skips) |
| Error, timeout, wrong key, Jev down | Extracted as usual; warning in the step log |
| Manual **reprocess** | Classifier not used; full extraction |
| Label not timesheet **and** P(timesheet) < `CLASSIFIER_SKIP_BELOW` | **Skipped.** The document says "Not a timesheet (classifier: invoice, 3% timesheet). Reprocess to extract it anyway." |

Every decision is written to the step log as a **`classify`** step, with the label,
P(timesheet), threshold, decision, model and time. Every skip can be checked in the
timeline. With tracing on, it also appears as an `ai.classify` span.

**What is sent to TypeSafe:** only the start of the document's text (`CLASSIFIER_MAX_CHARS`, 8,000 by default). The file name, sender, subject and email body are never sent.

## Settings (core-service/.env)

```
CLASSIFIER_ENABLED=false        # the main switch
CLASSIFIER_SHADOW_ONLY=true     # log only, never skip
CLASSIFIER_SKIP_BELOW=0.2       # skip only if P(timesheet) < 0.2
CLASSIFIER_TIMEOUT_S=10
CLASSIFIER_MAX_CHARS=8000
JEV_API_KEY=                    # .env only: never commit it
JEV_MODEL=jev-1.13.0            # pinned version
JEV_URL=https://api.typesafe.ai/v1/systemone
```

`CLASSIFIER_ENABLED=true` without `JEV_API_KEY` is refused at start-up.

## Before switching it on (Jev 0, your part)

1. Get a **TypeSafe account and API key** (early access).
2. Get **your mentor's approval** to send timesheet text to TypeSafe.
3. **Confirm the response format** in TypeSafe's docs: the field that holds each option's probability.
   - The parser accepts `probabilities: {"timesheet": 0.9}`, a list of `{option, probability}`, `options`, and `confidence` (used only when the choice is timesheet).
   - If the real field has another name, every answer comes back as "probability unknown", and nothing is ever skipped. Then tell me the field name; it's a one-line change in `jev_client.py`.

## Rollout

1. **Off** (now): nothing changes.
2. **Evaluate** on 30–50 of your own labelled files:
   ```powershell
   .\test-classifier.ps1 -Samples "..\samples"
   ```
   It prints, for thresholds 0.1, 0.2 and 0.3, how many **real timesheets would be wrongly skipped** (this must be **0**) and how many AI calls would be saved.
3. **Shadow** (`CLASSIFIER_ENABLED=true`, `CLASSIFIER_SHADOW_ONLY=true`) during the Step 9 batch. Compare the "would skip" decisions with what the AI actually found.
4. **On** (`CLASSIFIER_SHADOW_ONLY=false`), only if the evaluation and shadow mode are both clean.

## Apply (PowerShell, from `backend/`)

```powershell
git add -A; git commit -m "Before attachment classifier"
Expand-Archive -Force ..\jev-classifier.zip -DestinationPath .
cd core-service; uv lock; uv sync; cd ..          # httpx is now a direct dependency
docker compose build core-service
docker compose up -d                              # runs migration c9e5f3a7b2d4
cd core-service; uv run pytest -q; cd ..          # 192 passed
.\test-classifier.ps1                             # 2 passed (set-up checks; it stays off)
```

## Changed files

- **New:**
  - `src/core/services/attachment_classifier.py`: result type, skip rule, decisions
  - `src/data/clients/jev_client.py`: request, answer parser, HTTP call
  - `src/tools/evaluate_classifier.py`: the evaluation on your samples
  - migration `c9e5f3a7b2d4`: allows step `classify`
  - `tests/unit/test_classifier.py` (28 tests), `test-classifier.ps1`, `CLASSIFIER.md`
- **Changed:**
  - `src/config/settings.py`: the classifier settings, and a check that a key is set when it's enabled
  - `src/constants/timesheet_status.py`: `StepName.CLASSIFY`
  - `src/core/services/processing_service.py`: the classify step before extraction
  - `pyproject.toml`: `httpx`
