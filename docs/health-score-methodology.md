# Health score, cohorts and RFM: methodology

All figures come from synthetic data. The method is what matters; the numbers only show it works.

## Health score (0-100, per customer, per week)

Five dimensions, each 0-100, built from raw signals only (nothing from the hidden story arcs).

| Dimension | Weight | Signals |
|---|---|---|
| Adoption | 30% | Seat utilisation vs a 60% target (50%), 2-week usage trend vs the prior 4 weeks (25%), features used out of 8 (25%) |
| Support | 20% | Last 8 weeks: escalations (-20 each), reopened tickets (-12), first response over 2x the tier SLA (-8), open tickets older than 7 days (-10), high ticket volume (-2 per ticket over 3) |
| Engagement | 20% | Email open rate, scaled 10% = 0 to 50% = 100 (30%); champion present (45%): active 100, gone 30 days or less 25, gone longer 0, bounced emails cap it at 10; latest NPS in 180 days (25%, neutral 60 if none) |
| Commercial and relationship | 20% | Average days late on the last 3 invoices (-5 per day), disputed invoice (-25), contraction in 180 days (-15), expansion (+10), exec sponsor missing for Mid and Whale accounts (-15) |
| Onboarding | 10% | Milestones reached (data connected, first search, first dashboard, shared by a second user), with a time-to-first-value penalty after 21 days |

**Final score = 0.8 x weighted average + 0.2 x weakest dimension.** The weakest-link term stops
one very weak area (for example a departed champion) from being averaged away by strong ones.

**Flags:** 75 and above Healthy, 60 to 74 Watch, below 60 At risk.

Each row also has `top_driver` (the dimension costing the most points), `driver_tags` (for example
`champion_left;usage_down_52pct;tickets_reopened`), `score_change_4w`, and `weeks_in_flag`
(consecutive weeks in the current flag, for alert persistence rules).

Text signals such as competitor mentions are tagged (`competitor_mentioned`) but not scored: they
are noisy (healthy accounts mention competitors too), and the AI copilot is meant to read them in context.

## How it was checked (against the hidden story arcs, validation only)

- 26 customers churned. The score went below 60 before the churn date for 96% of them, with a
  median lead of 7 weeks; below 70 for 100% of them, with a median lead of 11 weeks (73% at least 8 weeks early).
- Healthy steady accounts: 7% ever dipped below 70 after their first 8 weeks, none were flagged At risk.
- False alarms (a 6-week dip that recovers) do dip, as they should. The alerting layer therefore uses
  `weeks_in_flag` and the copilot reads the call notes before escalating.
- Thresholds and the blend were tuned on this synthetic data. On real data they would be calibrated
  against actual churn outcomes.

## Cohorts

- **Size cohorts (SME, Mid, Whale) and coverage tiers (Digital, Pooled, CSM-led):** customers, average health,
  at-risk count and ARR, logo retention, gross and net revenue retention for accounts present at the
  start of the window, median days to first value, average seat utilisation.
- **Signup-quarter cohorts:** logo retention at 3, 6, 9, 12, 15 and 18 months. A cell is shown only
  when the whole cohort has been observed that long. Contracts are annual, so churn steps at renewal dates.

## RFM, adapted for SaaS

- **Recency:** days since the last week of meaningful use (at least 25% of seats and at least 50% of the customer's own typical level).
- **Frequency:** sessions per licensed seat per week, last 8 weeks.
- **Monetary:** current ARR.
- Each scored 1-5 (recency by fixed bins, frequency and monetary by quintile). Segments: Champions, Loyal,
  Promising (new and ramping), Light users, Need attention, At risk, Cannot lose (high ARR, gone quiet), Hibernating.
- RFM is a behavioural view and does not replace the health score. It reacts slowly to gradual decay
  because customers stay "recently active", which is one reason health uses trends and multiple dimensions.

## Outputs (`data/csv` and `data/health.db`)

`health_weekly`, `health_current`, `cohort_size`, `cohort_tier`, `cohort_signup_quarter`,
`cohort_retention_matrix`, `rfm_customers`, `rfm_summary`, `portfolio_kpis`.
