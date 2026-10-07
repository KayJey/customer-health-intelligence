"""Load the generated CSVs into BigQuery so ThoughtSpot (or any BI tool) can query them.

One-time setup (you do this, I cannot):
  1. Create a Google Cloud project (BigQuery sandbox needs no credit card).
  2. pip install -r requirements.txt
  3. gcloud auth application-default login      (or set GOOGLE_APPLICATION_CREDENTIALS to a key file)
  4. Run:  python load_bigquery.py --project YOUR_PROJECT_ID

By default ground_truth.csv (the hidden story arcs) is NOT loaded, so dashboards and models
have to infer risk from the observable signals. Add --include-ground-truth only for validation.
"""
import argparse
import os

from google.cloud import bigquery

CSV_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "csv")
TABLES = ["customers", "contacts", "weekly_usage", "onboarding_milestones", "tickets", "email_events",
          "nps_responses", "invoices", "contract_events", "play_catalog", "play_runs", "documents",
          # outputs of analytics/run_analytics.py (run it first)
          "health_weekly", "health_current", "cohort_size", "cohort_tier", "cohort_signup_quarter",
          "cohort_retention_matrix", "rfm_customers", "rfm_summary", "portfolio_kpis"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--dataset", default="customer_health")
    ap.add_argument("--location", default="US")
    ap.add_argument("--include-ground-truth", action="store_true")
    a = ap.parse_args()

    client = bigquery.Client(project=a.project)
    ds = bigquery.Dataset(f"{a.project}.{a.dataset}")
    ds.location = a.location
    client.create_dataset(ds, exists_ok=True)

    tables = TABLES + (["ground_truth"] if a.include_ground_truth else [])
    cfg = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.CSV, skip_leading_rows=1, autodetect=True,
                                 write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                                 allow_quoted_newlines=True)   # ticket threads contain line breaks
    for t in tables:
        with open(os.path.join(CSV_DIR, f"{t}.csv"), "rb") as f:
            client.load_table_from_file(f, f"{a.project}.{a.dataset}.{t}", job_config=cfg).result()
        print(f"loaded {t:24s}{client.get_table(f'{a.project}.{a.dataset}.{t}').num_rows:>8,d} rows")
    print(f"\nDone. Dataset: {a.project}.{a.dataset}")


if __name__ == "__main__":
    main()
