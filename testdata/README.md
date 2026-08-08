# testdata/

Fixture files for parser regression tests. These mirror what the restaurant PDFs
look like *today* and must be refreshed whenever a restaurant changes its layout.

## Conventions

- Store **extracted text only** (output of `pdftotext -layout <file> -`), never the
  PDFs themselves.
- Naming: `<source_id>_sample.txt` (e.g. `vaihingen_sample.txt`, `roland_sample.txt`).
- Each file records the week range it covers in its first comment line.

## Regenerating fixtures

1. Download the PDF via the URLs in `PROJECT.md` §3 (respect robots.txt / crawl-delay).
2. Run `pdftotext -layout <file> - > testdata/<source_id>_sample.txt`.
3. Verify the parsed output against the original document before committing.

## Adding a new source

Create `<source_id>_sample.txt` following the same pattern. Tests must never depend
on the PDF itself.
