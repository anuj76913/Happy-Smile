# P0-01 / P0-04 — Baseline analysis

Tests the ops head's claim ("leads we happen to call within 5 minutes convert 3x better") against historical data. It also measures when enquiries arrive and the language mix, which set the calling window and the Hindi priority.

## Files

| File | Purpose |
|---|---|
| `baseline_analysis.py` | The analysis. Reads a CSV export and writes a Markdown report |
| `generate_sample_data.py` | Builds a **synthetic** dataset with known confounders, so the method can be checked before real data arrives |
| `sample_data/enquiries_synthetic.csv` | Generated synthetic data (not HappySmile data) |
| `reports/baseline_report_synthetic.md` | Report on the synthetic data, as a worked example |

Python 3.10+ and the standard library only. Nothing to install.

## Run it

On synthetic data:

```bash
python generate_sample_data.py
python baseline_analysis.py --input sample_data/enquiries_synthetic.csv \
    --out reports/baseline_report_synthetic.md --synthetic
```

On the real export from HappySmile:

```bash
python baseline_analysis.py --input <path-to-export>.csv --out reports/baseline_report.md
```

Keep the real export out of version control. It contains personal data.

## Data request to HappySmile

Ask for **the last 90 days** of enquiries, one row per enquiry, with these columns. Names and phone numbers are **not** needed. Use an internal ID.

| Column | Required | Format | Notes |
|---|---|---|---|
| `enquiry_id` | Yes | text | Any unique ID |
| `created_at` | Yes | ISO datetime, IST (`2026-08-01T14:05:00`) | When the enquiry arrived |
| `clinic_id` | Yes | text | Nearest clinic chosen |
| `treatment` | Yes | text | braces_aligners / whitening / implants / other |
| `source` | Recommended | text | website / ads / aggregator / … |
| `language` | Optional | `en` / `hi` / … | Often not recorded; then sample at clinics |
| `first_call_at` | Yes | ISO datetime | First **dial** attempt, answered or not |
| `first_reached_at` | Yes | ISO datetime or blank | First call the person **answered**; blank if never |
| `call_attempts` | Optional | integer | |
| `booked` | Yes | 0 / 1 | Consultation booked |
| `booked_at` | Optional | ISO datetime | |
| `attended` | Optional | 0 / 1 / blank | Did they turn up |

The **difference between `first_call_at` and `first_reached_at`** is the most important ask. Without first dial times, the analysis cannot separate "we called fast" from "they answered fast", and that difference is likely the main source of the "3x".

## What the report shows

1. **Baseline**: volume, booking rate, time to first dial and first reached, attendance.
2. **Booking by delay bucket**, measured both ways.
3. **The 3x claim** in three steps (fast-reached vs everyone else → reached only → by first dial), plus Mantel–Haenszel ratios adjusted for hour, source, treatment and clinic, and a check of *who* gets fast calls.
4. **Arrival times** (P0-04): share outside 09:00–21:00, busiest hour, language mix.
5. **Volume by clinic** for pilot selection (P0-07) and staffing (P0-08).

## How to read the synthetic example

The generator sets the true effect of reaching someone within 5 minutes at **1.3x**. It adds two confounders: eager leads answer the first call, and staff call website leads and quiet-hour leads faster. The raw "fast versus everyone else" figure comes out at about **2.3x**. It falls step by step as the confounders are removed. This shows why the pilot needs a randomised control group, whatever the real data says.
