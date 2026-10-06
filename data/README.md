# Datasets, sources and licences

`scripts/prepare_data.py` downloads the raw files into `data/raw/` (gitignored) and
writes the cleaned CSVs to `data/processed/` (gitignored). It is deterministic (seed
42), skips the download if the cache exists, prints the per-class counts, and stops
with an error if a source is unreachable.

## Issue type (`data/processed/issues.csv`)

- Source: NLBSE'23 Tool Competition on Issue Report Classification.
  - Repo: https://github.com/nlbse2023/issue-report-classification
  - Train: https://tickettagger.blob.core.windows.net/datasets/nlbse23-issue-classification-train.csv.tar.gz (~514 MB)
  - Test: https://tickettagger.blob.core.windows.net/datasets/nlbse23-issue-classification-test.csv.tar.gz (~57 MB)
- Licence: AGPL-3.0 (per the NLBSE'23 repo). Used here for a non-commercial
  portfolio project, with attribution.
- Raw schema: `label, id, title, body, author_association`. About 1.28M train rows
  and 142k test rows, skewed: bug 52.6%, feature 37%, question 6%, documentation
  4.4%.
- What the script does: reads the ~57 MB test partition as the sampling pool by
  default (`--full-pool` uses the train file), keeps the four known labels, maps
  `feature` to `feature_request` and `question` to `question_other`, drops rows with
  no text, and takes up to 3,000 rows per class with a fixed seed. Output columns:
  `id, title, body, label`.
- Result: 11,947 rows after the classifier step's exact-text dedup, roughly 3,000
  per class. The classifier step then does its own stratified 70/15/15 split.
- There is no `performance` label because no public issue dataset provides one.

## Severity (`data/processed/severity.csv`, opt-in, not shipped)

I wanted a severity head and didn't ship one. The only well-formed, downloadable
severity source I found is
[`AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset`](https://huggingface.co/datasets/AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset)
on HuggingFace, a slice of the Lamkanfi / Perez / Demeyer Eclipse and Mozilla
defect-tracking dataset (MSR'13, Zenodo DOI 10.5281/zenodo.268443). It carries only a
citation request, no OSS licence. The EPL-2.0 Mendeley version has no stable direct
download, and the Zenodo zip is 17 GB with a 100-row sample. So the path exists for
local experiments only:

```bash
python scripts/prepare_data.py --with-severity
```

- Raw schema: `Project, Bug ID, Severity Label, Resolution Status, Short Description`.
  88,682 rows, all resolved as FIXED, no body field (`Short Description` becomes
  `title`).
- Raw counts: normal 72,170; critical 5,936; major 4,573; minor 3,125; trivial
  2,080; blocker 798.
- Mapping to `low` / `medium` / `high`: minor and trivial to `low`; normal to
  `medium`; blocker, critical and major to `high`. Up to 3,000 per class.

## Code-fix verification

The trust harness needs tasks that ship their own tests. Those are the ten practice
bugs in `tests/fixtures/`, each a small module plus a `check_*.py` test file. Nothing
is downloaded. Keeping them in the repo makes verification deterministic and keeps the
reliability store fed only by tests the harness ran itself.

## Reproduce

```bash
python scripts/prepare_data.py                 # issue type (default)
python scripts/prepare_data.py --force         # refresh the raw cache
python scripts/prepare_data.py --per-class 3000
python scripts/prepare_data.py --with-severity # local experiments only
```
