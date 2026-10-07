"""Settings for the synthetic customer-health dataset.

Everything here is fictional. There is no real company, customer or person behind
any row. The shape (tiers, lifecycle, signals) mirrors a B2B analytics SaaS tech-touch
program, and the signal types mirror the client-intelligence work done at 5C.
"""
from datetime import date

SEED = 42
N_CUSTOMERS = 250

# 52 weekly snapshots, Monday to Sunday. Snapshot is the Monday after the last week.
START = date(2025, 10, 6)
N_WEEKS = 52
SNAPSHOT = date(2026, 10, 5)

SIGNUP_MIN = date(2024, 10, 1)
SIGNUP_MAX = date(2026, 8, 15)

# Exact size-band counts so cohort tables line up with the mock
BAND_COUNTS = {"SME": 130, "Mid": 95, "Whale": 25}
BAND_ARR = {"SME": (6_000, 24_900), "Mid": (25_000, 99_000), "Whale": (100_000, 600_000)}
# Coverage tier probabilities per size band: Digital, Pooled, CSM-led
TIER_P = {"SME": [0.85, 0.15, 0.0], "Mid": [0.25, 0.60, 0.15], "Whale": [0.0, 0.10, 0.90]}
BASE_RATIO_MEAN = {"SME": 0.58, "Mid": 0.52, "Whale": 0.44}   # active users / licensed seats
PRICE_PER_SEAT = (900, 1400)                                  # ARR per seat range

INDUSTRIES = ["Retail", "Banking and Financial Services", "Healthcare", "Telecom",
              "Manufacturing", "Software and Technology", "Logistics"]
USE_CASES = ["Sales analytics", "Finance reporting", "Operations monitoring",
             "Customer analytics", "Supply chain visibility"]
REGIONS = ["India", "North America", "Europe", "Middle East", "Asia Pacific"]
REGION_P = [0.34, 0.26, 0.18, 0.10, 0.12]

# Hidden story arcs. Customers are assigned one; the arc drives usage, support,
# engagement and (sometimes) churn. The arc is saved only in ground_truth.csv, so any
# model or dashboard has to infer risk from the observable signals.
ARC_W = {
    "healthy_steady": 0.42,
    "healthy_expanding": 0.10,
    "late_bloomer": 0.05,
    "false_alarm": 0.06,
    "slow_onboarding_stall": 0.08,
    "champion_loss": 0.08,
    "support_friction": 0.08,
    "competitor_eval": 0.05,
    "quiet_fade": 0.08,
}
# Probability a risky customer actually churns at its target renewal (if it falls in the window).
CHURN_P = {"slow_onboarding_stall": 0.65, "champion_loss": 0.50, "support_friction": 0.45,
           "competitor_eval": 0.55, "quiet_fade": 0.60}
DECAY_ARCS = {"champion_loss", "quiet_fade", "competitor_eval", "support_friction"}
CHURN_REASON = {"slow_onboarding_stall": "never reached value", "champion_loss": "champion left, no replacement",
                "support_friction": "unresolved support issues", "competitor_eval": "moved to competitor",
                "quiet_fade": "low adoption", "surprise": "budget cut"}

SURPRISE_CHURN_P = 0.03   # churn with no warning signs, so the model is not unrealistically perfect

CSM_NAMES = ["Priya Nair", "Daniel Okafor", "Meera Iyer", "Lucas Brandt",
             "Anika Rao", "Tomas Silva", "Hana Kobayashi", "Rohan Mehta"]
SUPPORT_NAMES = ["Sam", "Asha", "Ben", "Nisha", "Carlos", "Leila"]
FIRST = ["Aarav", "Maya", "Ethan", "Sofia", "Kabir", "Emma", "Rahul", "Olivia", "Arjun", "Isla", "Noah",
         "Zara", "Liam", "Ananya", "Mateo", "Chloe", "Vikram", "Grace", "Omar", "Elena", "Dev", "Nora",
         "Kenji", "Amara", "Jonas", "Ritu", "Felix", "Sana", "Hugo", "Tara"]
LAST = ["Sharma", "Patel", "Nguyen", "Garcia", "Kapoor", "Mueller", "Reddy", "Smith", "Khan", "Rossi",
        "Iyer", "Tanaka", "Singh", "Costa", "Das", "Bauer", "Menon", "Park", "Haddad", "Ivanov",
        "Joshi", "Larsen", "Verma", "Cohen", "Okoye", "Shah", "Moreau", "Gupta", "Silva", "Lim"]

PLAYS = [
    ("onboarding_stall", "Onboarding stall", "Day 14 with no dashboard created", "Digital, Pooled"),
    ("adoption_nudge", "Adoption nudge", "Active users below 40% of seats for 2 weeks", "Digital, Pooled"),
    ("champion_loss", "Champion loss", "Champion contact inactive or departed", "All"),
    ("renewal_readiness", "Renewal readiness", "Renewal in 120 days", "All"),
    ("expansion_signal", "Expansion signal", "Seat use above 85% for 2 weeks", "All"),
]
