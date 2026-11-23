# Baseline report — enquiries and time to first call

> **SYNTHETIC DATA.** These numbers come from `generate_sample_data.py`, not from HappySmile. They demonstrate the method only. Rerun on the real export before drawing any conclusion.

Source: `enquiries_synthetic.csv` · 26,852 enquiries over 90 days · fast = first contact within 5 minutes.

## 1. Baseline

| Metric | Value |
|---|---|
| Enquiries per day (mean) | 298 |
| Booking rate | 27.7% |
| Reached at all | 74.2% |
| Median time to first dial | 5.8 h |
| Median time to first reached | 12.2 h |
| Dialled within 5 min | 12.0% |
| Reached within 5 min | 5.5% |
| Attendance rate of bookings | 74.3% |

## 2. Booking rate by time to first contact

| Delay | Leads (by reached) | Booked (by reached) | Leads (by dial) | Booked (by dial) |
|---|---|---|---|---|
| <= 5 min | 1,480 | 58.4% | 3,218 | 34.2% |
| 5-30 min | 193 | 54.9% | 410 | 33.7% |
| 30 min-2 h | 1,485 | 47.2% | 3,069 | 28.3% |
| 2-6 h | 4,308 | 39.0% | 6,815 | 26.7% |
| > 6 h | 12,455 | 31.3% | 13,340 | 26.4% |
| never | 6,931 | 2.9% | 0 | – |

## 3. Testing the "3x within 5 minutes" claim

| Measure | Booked if fast | Booked if slow | Ratio | Fast / slow leads |
|---|---|---|---|---|
| Reached within 5 min vs **all other leads** (incl. never reached) | 58.4% | 25.9% | **2.25x** | 1,480 / 25,372 |
| Raw, by first **reached** (reached leads only) | 58.4% | 34.6% | **1.69x** | 1,480 / 18,441 |
| Raw, by first **dial** | 34.2% | 26.8% | **1.27x** | 3,218 / 23,634 |

Read the rows top to bottom:

- **Row 1** is the likely way a "3x" figure gets made: people reached fast versus everyone else, including people never reached (who almost never book).
- **Row 2** compares reached leads only. A drop from row 1 means part of the claim comes from counting unreachable leads as "slow".
- **Row 3** measures speed by first *dial*. A further drop means eager people answering the first call explains part of the effect, not the speed of calling.

### Adjusted for observable confounders (Mantel–Haenszel risk ratio, by first dial)

| Stratified by | Adjusted ratio | Strata used |
|---|---|---|
| Hour band | 1.24x | 4 |
| Lead source | 1.19x | 3 |
| Treatment | 1.27x | 4 |
| Clinic | 1.27x | 12 |
| Hour band × source × treatment | 1.14x | 48 |

Adjustment only removes bias from *recorded* factors. Intent (how keen someone is) is not recorded, so the adjusted figure can still be biased in either direction. Only the randomised pilot (architecture §10) measures the true effect of speed.

### Who gets fast calls? (is "fast" random?)

**By hour band**

| Hour band | Leads | Dialled within 5 min | Booking rate |
|---|---|---|---|
| 09-12 | 3,912 | 28.8% | 29.5% |
| 12-15 | 5,010 | 9.3% | 27.9% |
| 15-18 | 4,541 | 27.0% | 30.0% |
| 18-21 | 6,625 | 6.0% | 25.8% |
| out of window | 6,764 | 0.0% | 26.9% |

**By lead source**

| Lead source | Leads | Dialled within 5 min | Booking rate |
|---|---|---|---|
| ads | 12,106 | 10.1% | 22.0% |
| aggregator | 4,689 | 9.8% | 20.6% |
| website | 10,057 | 15.3% | 37.9% |

If some groups get fast calls far more often *and* book more anyway, the raw ratio overstates the effect of speed.

## 4. When enquiries arrive (P0-04)

- Outside the proposed calling window (09:00–21:00): **25.2%** of enquiries. These cannot get an AI call in minutes and need the overnight path (architecture §4.4).
- Busiest hour: **20:00–21:00** with 9.2% of daily volume (used for capacity, architecture §13).
- Language mix: en: 54.7%, hi: 45.3%.

| Hour | Enquiries per day | Share |
|---|---|---|
| 00:00 | 2.2 | 0.7% |
| 01:00 | 1.1 | 0.4% |
| 02:00 | 0.6 | 0.2% |
| 03:00 | 0.6 | 0.2% |
| 04:00 | 0.7 | 0.2% |
| 05:00 | 0.9 | 0.3% |
| 06:00 | 2.7 | 0.9% |
| 07:00 | 5.9 | 2.0% |
| 08:00 | 9.2 | 3.1% |
| 09:00 | 12.0 | 4.0% |
| 10:00 | 15.1 | 5.1% |
| 11:00 | 16.3 | 5.5% |
| 12:00 | 19.0 | 6.4% |
| 13:00 | 20.2 | 6.8% |
| 14:00 | 16.5 | 5.5% |
| 15:00 | 15.9 | 5.3% |
| 16:00 | 16.1 | 5.4% |
| 17:00 | 18.4 | 6.2% |
| 18:00 | 21.6 | 7.2% |
| 19:00 | 24.5 | 8.2% |
| 20:00 | 27.6 | 9.2% |
| 21:00 | 25.7 | 8.6% |
| 22:00 | 17.7 | 5.9% |
| 23:00 | 7.8 | 2.6% |

## 5. Volume by clinic (input for P0-07 and P0-08)

| Clinic | Enquiries per day | Booking rate | Median time to dial | Hindi share |
|---|---|---|---|---|
| C01 | 39.7 | 28.0% | 5.4 h | 44.8% |
| C02 | 35.5 | 28.8% | 5.9 h | 44.9% |
| C03 | 32.1 | 28.5% | 5.7 h | 45.5% |
| C04 | 30.9 | 27.0% | 7.2 h | 45.7% |
| C05 | 26.2 | 27.6% | 5.8 h | 45.4% |
| C07 | 25.2 | 27.5% | 6.0 h | 45.8% |
| C06 | 24.7 | 27.3% | 5.3 h | 44.9% |
| C08 | 22.2 | 27.2% | 5.2 h | 46.6% |
| C09 | 19.4 | 27.8% | 9.2 h | 45.6% |
| C10 | 17.7 | 27.6% | 5.9 h | 45.1% |
| C11 | 14.6 | 25.2% | 7.0 h | 44.3% |
| C12 | 10.2 | 29.1% | 5.4 h | 45.3% |

## 6. What to take to the ops head

- Fast-reached versus everyone else: **2.3x**.
- Among reached leads only: **1.7x**.
- Measured by first dial instead: **1.3x**.
- After adjusting for hour, source and treatment: **1.1x** (unrecorded factors such as intent can still bias this).
- Conclusion: speed probably helps, but the historical data cannot say by how much. The pilot keeps a randomised standard-callback group to measure it.
