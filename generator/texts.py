"""Template-based free text (tickets, CSM call notes, QBR notes, NPS comments, email replies).

The text carries the story arc: champion departures, competitor mentions, support
friction. It feeds the vector store, so the copilot can find these signals by meaning.
Template-based on purpose: deterministic and free. An LLM pass can enrich it later.
"""

COMPETITORS = ["Brightlane BI", "Datavista", "Pivotly", "Clearmetric"]
OBJECTS = {
    "Retail": ["store sales dashboard", "inventory turnover report", "promo performance dashboard", "weekly footfall report"],
    "Banking and Financial Services": ["loan portfolio dashboard", "branch performance report", "risk exposure dashboard", "fraud alerts report"],
    "Healthcare": ["patient throughput dashboard", "claims backlog report", "bed occupancy dashboard", "referral tracking report"],
    "Telecom": ["churn by region dashboard", "network quality report", "ARPU dashboard", "store activation report"],
    "Manufacturing": ["line efficiency dashboard", "yield and scrap report", "downtime dashboard", "supplier quality report"],
    "Software and Technology": ["product usage dashboard", "pipeline coverage report", "support volume dashboard", "trial conversion report"],
    "Logistics": ["on-time delivery dashboard", "fleet utilisation report", "warehouse throughput dashboard", "route cost report"],
}
SOURCES = ["Snowflake", "BigQuery", "Postgres", "Salesforce", "SAP", "SQL Server", "Excel exports"]

TICKET_CATEGORIES = ["Data connection", "Performance", "Permissions", "How-to", "Bug", "Billing", "Feature request"]

_TICKET = {
    "Data connection": {
        "subject": ["Cannot refresh {src} connection", "Sync from {src} failing", "Credentials rejected for {src}"],
        "open": ["Our {src} connection stopped refreshing overnight and the {obj} is showing stale numbers.",
                 "We changed credentials on {src} and now the sync fails with an authentication error.",
                 "The {src} import ran but only part of the tables came through. The {obj} is missing last week's data."],
        "reply": ["Thanks for flagging. I can see the refresh token expired. Please re-authorise the connection and let me know if the sync completes.",
                  "We found a schema change upstream that broke the mapping. I have reset it and queued a full refresh."]},
    "Performance": {
        "subject": ["Dashboard loads very slowly", "{obj} times out", "Slow filters on {obj}"],
        "open": ["The {obj} takes close to a minute to load during our Monday review. It used to be a few seconds.",
                 "Filters on the {obj} hang whenever more than two people are in it at once.",
                 "Our weekly review meeting stalls because the {obj} times out. This is becoming a real problem for us."],
        "reply": ["I can see heavy queries on that dashboard. I suggest limiting the date range and I have asked engineering to look at the query plan.",
                  "Thanks for the detail. We have raised this with the performance team and will update you tomorrow."]},
    "Permissions": {
        "subject": ["Need access for new team", "Row-level access not working", "Users can see wrong data"],
        "open": ["We added a new regional team and they cannot open the {obj}. Please advise on the right access setup.",
                 "Row-level restrictions are not applied correctly, some users see data from other regions on the {obj}."],
        "reply": ["I have checked the group mapping. The new team was missing the viewer role, which I have added. Please ask them to sign out and in.",
                  "The row-level rule had an incorrect filter value. It is fixed now, please verify with a test user."]},
    "How-to": {
        "subject": ["How do I build a calculated metric?", "Question about sharing dashboards", "Scheduling reports"],
        "open": ["Could you show us how to create a ratio metric for the {obj}? We keep getting the wrong totals.",
                 "How can we schedule the {obj} to email our leadership every Monday?",
                 "We are new to this. What is the best way to share the {obj} with people outside our team?"],
        "reply": ["Happy to help. Here is a short guide with screenshots, and I have also linked a five minute walkthrough video.",
                  "You can do that from the scheduling menu. I have attached the steps, and I can set up a short call if you prefer."]},
    "Bug": {
        "subject": ["Totals do not match export", "Chart shows blank values", "Date filter resets"],
        "open": ["The totals on the {obj} do not match the export we pulled from {src}. We are off by about four percent.",
                 "The chart on the {obj} shows blank values for some regions even though the data is there.",
                 "The date filter on the {obj} resets itself whenever we apply another filter."],
        "reply": ["Thanks, I can reproduce this. It looks like a rounding issue with a null join. I have logged it with engineering.",
                  "I can see the problem on our side. A fix is scheduled for the next release and I will confirm when it ships."]},
    "Billing": {
        "subject": ["Question about last invoice", "Seat count mismatch on invoice", "Need updated billing contact"],
        "open": ["The last invoice shows more seats than we have onboarded. Can you check it?",
                 "Please update the billing contact on our account, our finance lead has changed."],
        "reply": ["I have reviewed the invoice with our billing team and issued a corrected one.",
                  "The billing contact is updated. You will receive the next invoice at the new address."]},
    "Feature request": {
        "subject": ["Request: export to slides", "Request: alert thresholds per user", "Request: more chart types"],
        "open": ["It would help a lot if we could export the {obj} straight to slides for our leadership pack.",
                 "Could we set alert thresholds per user on the {obj}? Right now it is one setting for everyone.",
                 "We need a few more chart types on the {obj}, in particular a waterfall."],
        "reply": ["Thanks for the suggestion. I have added it to our product feedback list with your use case.",
                  "That is a useful request and I have shared it with the product team. I will let you know if it is planned."]},
}

_FOLLOWUP = ["Following up, this is still happening for us.", "The same issue is back again, this is the second time.",
             "We tried your suggestion but the problem is still there. Can someone take a closer look?"]
_SLOW = ["It took a long time to get a first response on this ticket, which is frustrating for us.",
         "We waited most of a day before anyone replied. We need faster responses on issues like this."]
_COMPETITOR = ["Leadership has asked us to compare how {comp} handles this, so a quick answer would really help.",
               "To be honest we are also looking at {comp} for this use case, so we need this resolved soon."]
_COMP_PAST = ["For context, we compared this with {comp} during our original purchase, and we chose this one, so we would like it to work well.",
              "We evaluated {comp} before signing, and this was a deciding feature for us, so a quick fix would be great."]
_NEWOWNER = ["I am new on this account since {old} left, so please bear with me and explain it step by step.",
             "I have just taken over this from {old}, who has left the company, and I am still learning the setup."]


def ticket_subject(rng, cat, obj, src):
    return str(rng.choice(_TICKET[cat]["subject"])).format(obj=obj, src=src)


def ticket_text(rng, cat, obj, src, cust, supp, reopened, tags, old=None, comp=None):
    t = _TICKET[cat]
    lines = [f"Customer ({cust}): " + str(rng.choice(t["open"])).format(obj=obj, src=src)]
    if "new_owner" in tags and old:
        lines.append(f"Customer ({cust}): " + str(rng.choice(_NEWOWNER)).format(old=old))
    if "competitor" in tags and comp:
        lines.append(f"Customer ({cust}): " + str(rng.choice(_COMPETITOR)).format(comp=comp))
    if "comp_past" in tags and comp:
        lines.append(f"Customer ({cust}): " + str(rng.choice(_COMP_PAST)).format(comp=comp))
    lines.append(f"Support ({supp}): " + str(rng.choice(t["reply"])))
    if "slow" in tags:
        lines.append(f"Customer ({cust}): " + str(rng.choice(_SLOW)))
    for _ in range(min(reopened, 3)):
        lines.append(f"Customer ({cust}): " + str(rng.choice(_FOLLOWUP)))
        lines.append(f"Support ({supp}): Thanks for your patience, I am looking into it again and will update you shortly.")
    return "\n".join(lines)


# --- CSM call notes and QBR notes, by account phase ---
_CALL = {
    "ok": ["Regular check-in with {c}. Usage is steady and the team uses the {obj} weekly. No blockers. They asked about scheduled reports and I shared the guide.",
           "Call with {c} went well. Two new analysts have joined and are active. We agreed to review advanced features next month.",
           "Quick sync with {c}. Happy with the product, adoption is healthy and they plan to roll it out to a second department."],
    "ok_dip": ["{c} said usage is lower this month because of a system migration on their side. They expect it back to normal in a few weeks. Keeping an eye on it.",
               "Call with {c}. Activity dropped during their quarter-end freeze. They confirmed the dip is temporary and they remain committed."],
    "concern": {
        "champion_loss": ["{c} champion {old} has left the company. The new owner is not yet trained on the {obj} and attendance on our calls is low. Need an introduction session.",
                          "Spoke to {c}. {old} handed over to someone in operations who has limited context. Usage on the {obj} has dropped and we have no executive contact right now."],
        "support_friction": ["{c} is frustrated with how long support issues are taking. Several tickets were reopened. They said it is affecting trust in the platform.",
                             "Call with {c}. The same performance issue on the {obj} has come back more than once. They want a named contact and a root cause."],
        "competitor_eval": ["{c} mentioned they have been in talks with {comp} and are comparing pricing and dashboard speed. Need to prepare a value review before renewal.",
                            "{c} asked for a roadmap discussion. In passing they said leadership is evaluating {comp}. Flagging as a competitive risk."],
        "quiet_fade": ["Hard to reach {c}. Last two emails were not answered and only a few users are logging in. Engagement is slipping and I do not see a clear reason.",
                       "{c} declined the last check-in. Usage is down compared with the previous quarter and only the admin is active."],
        "slow_onboarding_stall": ["{c} still has not shared a dashboard with a second user. The data connection is done but the team has not had time to build anything. Onboarding is stalled.",
                                  "Onboarding call with {c} was rescheduled twice. They are not seeing value yet because nobody owns the rollout."],
    },
    "critical": {
        "champion_loss": ["{c} has no active champion. Usage on the {obj} is a fraction of what it was. Renewal is coming and nobody senior knows the product.",
                          "Escalating {c}. No response from the new owner and the exec sponsor has not been engaged since {old} left."],
        "support_friction": ["{c} states they will not renew unless the open issues are resolved. Escalated to the support lead.",
                             "{c} is very unhappy. Reopened tickets, slow responses and no fix for the {obj} problem. Renewal at risk."],
        "competitor_eval": ["{c} confirmed they are running a proof of concept with {comp}. They said the {obj} loads too slowly for their weekly review.",
                            "Renewal risk with {c}. They are leaning towards {comp} and asked for a final pricing offer."],
        "quiet_fade": ["{c} has almost stopped using the product. No response to outreach. Treat as likely churn unless we reach an executive.",
                       "No engagement from {c} for weeks. Usage is near zero outside of a single admin."],
        "slow_onboarding_stall": ["{c} never got to value. Still no shared dashboard after many weeks and no response to the onboarding plays.",
                                  "{c} said the product is not a priority this year. No rollout planned. Likely to leave at renewal."],
    },
    "recovering": ["Good call with {c}. After the re-introduction session the new team has started using the {obj} again. Usage is recovering.",
                   "{c} responded to our value review and is back on track. We fixed the open issues and agreed on a monthly check-in. Renewal looks safer."],
    "save": ["Save plan for {c} worked. We ran a short training for the new owner, resolved the open tickets and shared a value summary. They will renew.",
             "{c} confirmed renewal after we reconnected with their executive sponsor and walked through the {obj} results."],
    "exit": {
        "champion_loss": ["{c} did not renew. With the champion gone nobody owned the platform and adoption never recovered.",],
        "support_friction": ["{c} did not renew. They cited unresolved support issues and loss of trust.",],
        "competitor_eval": ["{c} did not renew and moved to {comp}. They cited dashboard speed and pricing.",],
        "quiet_fade": ["{c} did not renew. Low adoption throughout the year and we could not reach a decision maker.",],
        "slow_onboarding_stall": ["{c} did not renew. They never reached value and had no internal owner.",],
        "surprise": ["{c} did not renew due to an internal budget cut. Usage had been healthy until the end.",],
    },
    "renewal": ["Renewal prep with {c}. Usage is healthy and they want to expand to a second team. Planning a pricing conversation.",
                "{c} is ready to renew. They asked for a business review pack with the {obj} adoption numbers."],
    "expansion": ["{c} is using nearly every licensed seat and a new department has asked for access. Good expansion opportunity.",
                  "Seat use at {c} is above 85 percent. They mentioned a plan to roll out to another region. Passing the signal to Sales."],
}

_QBR = {
    "ok": ["QBR with {c}. Time to value, activation and adoption are all on target. The {obj} is used daily. They want to expand to a new use case next quarter.",
           "Quarterly review for {c}: strong adoption, a healthy mix of viewers and builders, and positive feedback from the exec sponsor."],
    "concern": ["QBR with {c}. Adoption is below plan and the exec sponsor attended only part of the session. Agreed on an action plan with a training session.",
                "Quarterly review for {c}: fewer active users than last quarter and open support items. Action plan agreed, follow-up in four weeks."],
    "critical": ["QBR with {c} did not take place, the sponsor cancelled twice. Adoption is far below target and renewal is at risk.",
                 "Quarterly review for {c}: poor usage, open escalations and no clear owner. Recommended executive outreach."],
    "recovering": ["QBR with {c}. Adoption has improved since the training session and open issues are closed. The sponsor was positive about renewing."],
}

_NPS = {
    "promoter": ["Great product, our team uses it daily and the support has been quick.", "Easy to build dashboards and the AI assistant saves us time.",
                 "Onboarding was smooth and we saw value within weeks.", "Very happy, we plan to roll it out to more teams."],
    "passive": ["It does the job but a few reports are slow at peak times.", "Good overall. We would like more chart types and faster support on complex questions.",
                "Solid platform, but adoption in the wider team is slower than we hoped."],
    "detractor": ["Support issues keep coming back and take too long to fix.", "Dashboards are too slow for our Monday reviews.",
                  "We have not seen the value we expected. Hard to get the team to use it.", "Since our lead left nobody here really knows how to use it.",
                  "We are looking at other tools because of performance and pricing."],
}

_REPLY = ["Thanks for the note, we will take a look this week.", "Thanks, we will try that and come back to you.",
          "Happy to book a call, please send some times.", "Appreciated. Forwarding this to the team."]


def call_note(rng, kind, arc, c, obj, old="our previous contact", comp="another vendor", phase=None):
    node = _CALL[kind]
    if isinstance(node, dict):
        pool = node.get(arc) or node.get("quiet_fade") or next(iter(node.values()))
    else:
        pool = node
    return str(rng.choice(pool)).format(c=c, obj=obj, old=old, comp=comp)


def qbr_note(rng, phase, c, obj):
    return str(rng.choice(_QBR.get(phase, _QBR["ok"]))).format(c=c, obj=obj)


def nps_comment(rng, score, arc, phase):
    band = "promoter" if score >= 9 else "passive" if score >= 7 else "detractor"
    text = str(rng.choice(_NPS[band]))
    if band == "detractor" and arc == "competitor_eval":
        text = str(rng.choice(["Dashboards are too slow for our reviews and we are looking at other tools.", _NPS["detractor"][4]]))
    if band == "detractor" and arc == "champion_loss":
        text = str(rng.choice(["Since our lead left nobody here really knows how to use it.", _NPS["detractor"][3]]))
    return text


def reply_text(rng):
    return str(rng.choice(_REPLY))


SUBJECTS = {
    ("onboarding_series", 0): "Welcome, here is how to get your first dashboard live",
    ("onboarding_series", 1): "Connect your data in three steps",
    ("onboarding_series", 2): "Build and share your first dashboard",
    ("onboarding_series", 3): "Invite your team and set up access",
    ("newsletter", 0): "Product tips and what is new this month",
    ("onboarding_stall", "control"): "",
    ("onboarding_stall", "standard"): "Need a hand getting your first dashboard live?",
    ("adoption_nudge", "A"): "Get more from your analytics: tips for your team",
    ("adoption_nudge", "B"): "{industry} teams like yours are saving time with these 3 dashboards",
    ("champion_loss", "standard"): "A quick intro and walkthrough for your team",
    ("renewal_readiness", "standard"): "Your year in review and what is ahead",
    ("csm_outreach", 0): "Checking in on how things are going",
}
