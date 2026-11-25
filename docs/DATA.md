# Data

All datasets live in `data/`, which is git-ignored. What is committed: the
code that prepares data, checksums, the frozen split file (record IDs only)
and aggregate reports. See ADR-001 (data strategy) and ADR-007 (what may
appear in the public repo).

## 1. Kaggle LiveCareer resume dataset

| | |
|---|---|
| Source | <https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset> |
| Contents | 2,484 resumes: `Resume/Resume.csv` (ID, Resume_str, Resume_html, Category) + `data/data/<CATEGORY>/<ID>.pdf` |
| Labels | Job category only (24 values); no field labels |
| Licence | Not stated; scraped from livecareer.com. **Never commit, publish, screenshot or demo its content.** |
| Expected SHA-256 | `b12c4ab34df707ad2cc64312c016509cad9b6c93b0baed7a6a2c7cbd6b2b7aa4` |

### Get it

1. Sign in to Kaggle, open the dataset page, **Download → Download dataset as zip**.
2. Save it as `data/raw/kaggle-resume-dataset.zip` (from WSL:
   `mv /mnt/c/Users/<you>/Downloads/archive.zip data/raw/kaggle-resume-dataset.zip`).

### Prepare it

```bash
make data
```

Verifies the checksum, checks that every CSV row has its PDF (and vice
versa), drops exact duplicates (same text after case/whitespace
normalization; lowest ID wins), then writes:

| Output | Committed? | What |
|---|---|---|
| `data/interim/kaggle/pdf/<CATEGORY>/<ID>.pdf` | no | Extracted PDFs |
| `data/interim/kaggle/records.jsonl` | no | One line per unique resume: id, category, pdf path, text hash, text |
| `data/interim/kaggle/duplicates.tsv` | no | Dropped ID → kept ID |
| `ml/reports/kaggle_profile.md` | **yes** | Aggregate counts only (no content) |

`make data` fails if the frozen split file no longer matches the dataset.

## 2. Splits (frozen)

```bash
make splits     # once, then commit ml/splits/kaggle_v1.json
```

| Split | Size | Use |
|---|---|---|
| `gold_validation` | 30 | Hand-labeled. Tune thresholds, calibrate confidence, pick models. |
| `gold_test` | 120 | Hand-labeled. Reported metrics only. **Never train or tune on it.** |
| `train` | the rest | Unlabeled real text for training and weak supervision. |

The gold sample is spread evenly across the 24 categories (seed 20261125) so
per-category results are possible. `make splits` refuses to overwrite an
existing file: regenerating it silently would invalidate every reported
metric. If it must change, bump to `kaggle_v2.json` and record why in an ADR.
