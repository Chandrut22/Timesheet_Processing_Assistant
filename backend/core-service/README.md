# core-service

## Photos and scanned timesheets (vision read)

Docling + RapidOCR is built for printed text and reads handwriting badly. With
`VISION_ENABLED=true`, photos (PNG, JPG, TIFF, BMP, WebP) and PDFs **without a text
layer** are read by a vision-language model instead. Typed PDFs, DOCX, XLSX, CSV and TXT
keep the Docling / plain-reader path exactly as before. It is **off by default** and
nothing is sent anywhere until it is set up.

```
Typed PDF / DOCX / XLSX / CSV ──► Docling or plain reader ──► text ─┐
                                                                     ├─► LLM extraction ─► match ─► rules ─► decide
Photo / scanned PDF ──► vision model (1 call per page) ──► text ────┘
                         classification + transcription
```

For each page (up to `VISION_MAX_PAGES`):

1. The page is turned upright (EXIF), converted to RGB and shrunk to at most
   `VISION_IMAGE_MAX_SIDE` px and about 2.5 MP; scanned PDFs are rendered at 200 DPI.
2. One call returns JSON: `classification` (printed_only / handwritten_only / mixed /
   no_text / uncertain), `confidence`, `has_handwriting`, `has_handwritten_hours`,
   `has_printed_text`, `reason` and the `transcription` (Markdown, `[UNCLEAR]` for
   anything unreadable, never guessed). A signature or initials alone stay printed_only.
3. An answer that is not that JSON is asked again once; then the page counts as
   uncertain. Confidence below `VISION_MIN_CONFIDENCE` also counts as uncertain (decided
   in code). The `[UNCLEAR]` marks are counted in code.

The pages are joined (`--- page N ---`) into `documents.extracted_text`, the same column
Docling fills, so chunking, the prompt-injection protection and reprocessing work as
before (a reprocess reuses the text: the image is never sent again). The document also
keeps `read_method`, `writing_class` (worst page wins), `writing_confidence`,
`has_handwritten_hours`, `writing_reason` and `unclear_marks`.

What the decision does with it:

| Document | Flag | Severity | Auto-approve |
|---|---|---|---|
| printed_only (confident) | none | | normal rules |
| mixed, hours printed | `handwriting_present` | low | normal rules |
| hours written by hand (or handwritten_only) | `handwritten_hours` | high | never |
| uncertain or no_text | `writing_unclear` | high | never |
| `[UNCLEAR]` values | `unreadable_values` (with the dates) | high | never |

The extraction prompt never guesses an `[UNCLEAR]` value and never uses 0 for it: the
day is listed in `unreadable_days` and left out of the timesheet.

If the vision server is down, times out or answers 5xx, the job is retried later like
any temporary failure. It is never read with OCR instead (that would guess handwriting).
Logs, traces and the step log record the method, model, pages, class, confidence,
`[UNCLEAR]` count and timings: never the image, the reason or the transcription.

### Setting it up (core-service `.env`)

Ollama Cloud (hosted by Ollama: page images of timesheets leave your network):

    VISION_ENABLED=true
    VISION_BASE_URL=https://ollama.com/v1
    VISION_API_KEY=<your Ollama API key>
    VISION_MODEL=gemma4:31b-cloud

Self-hosted Ollama (nothing leaves your network; Gemma 4 31B needs about 20 GB of GPU
memory at 4-bit):

    ollama pull gemma4:31b
    VISION_ENABLED=true
    VISION_BASE_URL=http://gpu-host:11434/v1
    VISION_MODEL=gemma4:31b

Copy the model name exactly as the server lists it. `VISION_MAX_PAGES x VISION_TIMEOUT_S
+ 300` must fit in `WORKER_JOB_TIMEOUT_SECONDS` (the settings refuse to start otherwise).
All settings: `.env.example`.

### Checking a model on your own sheets

    uv run python -m src.tools.eval_handwriting eval_data/handwritten \
        --model gemma4:31b-cloud --base-url https://ollama.com/v1 --out eval-report.md

The folder holds the images plus an `expected.csv` (`file,employee_name,work_date,hours`,
one row per day). The Markdown report gives, per file, the class the model saw, and
overall the name character error rate, date and hours exact match, the share of days
marked `[UNCLEAR]`, seconds per page and failures. `eval_data/` and `eval-report*.md`
are in `.gitignore`: never commit real timesheets.
