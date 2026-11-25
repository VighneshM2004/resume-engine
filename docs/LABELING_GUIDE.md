# Labeling guide: gold set v1

The gold set is the ground truth every reported metric is measured against.
It's only as good as its consistency: when in doubt, follow these rules
literally and write a note, rather than improvising.

**Scope:** the 150 resumes in `ml/splits/kaggle_v1.json` (30 validation,
120 test). Label the 30 validation resumes first, then stop for a review
(step 6) before labeling the 120 test resumes.

**Text:** you label the Kaggle `Resume_str` text, not the PDF. The metrics
compare *values* (skill sets, job tuples), not character offsets, so the
extractor is scored fairly even though it reads the PDF.

## Setup (once)

```bash
# WSL, repo root
cp -n .env.example .env          # then set LABEL_STUDIO_USERNAME / _PASSWORD in .env
make data                        # if not done yet
make label-tasks                 # writes data/labeling/gold_tasks.json
make label                       # http://localhost:8081
```

In Label Studio:
1. Log in with the username/password from `.env`.
2. **Create project** → name `gold-v1`.
3. **Labeling setup** → **Custom template** → paste the contents of
   `ml/labeling/label_config.xml` → Save.
4. **Import** → upload `data/labeling/gold_tasks.json` (from Windows:
   `\\wsl$\Ubuntu\home\vighneshm\code\resume-engine\data\labeling\gold_tasks.json`).
5. Sort tasks by ID ascending: the 30 `gold_validation` tasks come first.

## The labels

| Label | Hotkey | What to mark |
|---|---|---|
| `SKILL` | s | A tool, technology, method, domain competency, or spoken language the candidate claims |
| `JOB_ENTRY` | j | The whole block of one position: from its title to the end of its description |
| `JOB_TITLE` | t | The position's title, inside its `JOB_ENTRY` |
| `COMPANY` | c | The employer, inside its `JOB_ENTRY` |
| `JOB_DATES` | d | The whole date range of the position, inside its `JOB_ENTRY` |
| `EDU_ENTRY` | e | The whole block of one qualification |
| `DEGREE` | g | Degree/diploma including field of study, inside its `EDU_ENTRY` |
| `INSTITUTION` | i | School, college or university, inside its `EDU_ENTRY` |
| `EDU_DATES` | y | Year(s) or date range, inside its `EDU_ENTRY` |
| `CERTIFICATION` | r | A named certification or licence |
| `LOCATION` | l | The candidate's own location (header/contact area only), at most one |

Then choose **usable** or **unusable**, and add a note if anything was
ambiguous. Submit.

## Rules

### Skills
- **Label what's written; never infer.** "Prepared monthly reconciliations"
  is not the skill "reconciliation"; label only explicit skill phrases.
- **Mark each distinct skill at least once.** Repeats are optional (the gold
  set stores a set; duplicates collapse).
- **Split lists into separate spans:** "Excel, Word and PowerPoint" → three
  `SKILL` spans. Keep compound names whole: "Microsoft Office Suite",
  "Accounts Payable", "Adobe Photoshop".
- **Include:** software and tools (QuickBooks, AutoCAD, Python), methods and
  standards (GAAP, Six Sigma, Agile), domain competencies (payroll
  processing, food safety, inventory management), equipment operation
  (forklift operation), spoken languages (Spanish).
- **Exclude:** personality traits ("hard-working", "detail-oriented",
  "team player"), job titles, degrees, certifications (they have their own
  label), and vague phrases ("computer skills", "various software").
- Borderline soft skills: label **"customer service", "project management",
  "public speaking", "negotiation"** (concrete, teachable, appear in ESCO);
  don't label "communication skills" or "leadership" on their own.

### Jobs
- One `JOB_ENTRY` per position. Same employer, two titles → two entries.
- The entry span covers title, company, dates and description; field spans
  must sit **inside** it. Overlapping entries are an error.
- `JOB_DATES` is the whole range as written: "Jan 2015 to Current",
  "2012 - 2014", "05/2016 to 08/2018". Don't normalize; the pipeline does.
- **LiveCareer placeholders:** the dataset replaces employers with
  "Company Name" and places with "City , State". Still label "Company Name"
  as `COMPANY`: the extractor must find the employer field, and evaluation
  handles placeholders. Don't label "City , State" inside jobs.
- No title written (only a description) → leave `JOB_TITLE` out; don't
  invent one.

### Education
- One `EDU_ENTRY` per qualification. `DEGREE` includes the field:
  "Bachelor of Science : Accounting", "High School Diploma".
- Coursework, GPA and honours stay inside the entry but get no field label.

### Certifications
- Named credentials only: "CPA", "Certified ScrumMaster", "ServSafe Food
  Handler", "Commercial Driver's License". Not "trained in safety
  procedures".

### Usable / unusable
- **unusable:** not a resume, mostly empty, or garbled beyond reading. Leave
  it otherwise unlabeled; it is excluded from field metrics.
- Everything else is **usable**, even if short.

## Pace

Expect about 10 minutes per resume, so the 150 take roughly 25 hours: three
days rather than two. Take a break every hour; tired labeling is
inconsistent labeling.

## Save, check, back up

At the end of every session:

1. **Export** → **JSON** → save into the repo as
   `data/labeling/exports/gold-v1-YYYYMMDD.json` (git-ignored).
2. Check it against the rules:
   ```bash
   make label-import EXPORT=data/labeling/exports/gold-v1-YYYYMMDD.json PARTIAL=1
   ```
   Fix every listed problem in Label Studio, export again, re-check.
3. **Back up** the export somewhere private (e.g. your own Google Drive).
   Never in the repo: it contains resume text (ADR-007). Losing it means
   relabeling.

## Review checkpoint (after the 30 validation resumes)

Export, run the check, then send me the printed summary (counts per label,
not the file). We'll look at the label counts and your notes for systematic
problems, and tighten this guide **before** the 120 test resumes. Changing
rules halfway through the test set would make it inconsistent.

## Consistency check (at the end)

Re-label 10 validation resumes in a second project (`gold-v1-recheck`)
without looking at your first labels. Agreement between the two passes
(computed in M3) is reported with every metric, so readers know how
reliable the ground truth is.

## When done

```bash
make label-import EXPORT=data/labeling/exports/gold-v1-final.json
```

This writes `data/gold/kaggle_gold_v1.jsonl` and fails if any of the 150
resumes is unlabeled or breaks a rule.
