"""The processing pipeline, one module per stage. processing_service.py runs them in
order for one submission; each stage gets the session and the rows it works on.

  claiming.py     take a submission for this run (or leave it to the worker that has it)
  fetching.py     a reprocess: fetch the email again from the mailbox when needed
  classifying.py  the optional "is this a timesheet at all?" check, from the file name
                  and the email only, before any file is read
  reading.py      file -> text (Docling), with the size limits
  extracting.py   text -> timesheets (the AI call, split into pieces for big sheets)
  matching.py     which company and which employee each timesheet is for
  deciding.py     pay rules, assignment dates, duplicates, then approve or review
  finishing.py    the submission's final state
  failing.py      a failed run: the message, and whether to try again later"""
