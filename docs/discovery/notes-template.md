# Interview notes — P&lt;n&gt; (anonymized)

> **Scrub before saving.** No participant name, company, product name, email,
> phone, hostname, IP, tenant ID, ticket ID or customer data. Replace vendors
> with `vendor A` / `cloud B` / `tool C`. Raw notes stay in private storage;
> only this filled template is committed.

## Metadata

| Field | Value |
|---|---|
| Participant ID | `P1` (never a name) |
| Role | e.g. platform engineer, MSP owner, on-call lead |
| Team-size band | `1–5` / `6–20` / `21–50` |
| Site-count band | `2–5` / `6–20` / `21+` |
| Segment | MSP / in-house / other |
| Date | `YYYY-MM-DD` |
| Interviewer / note-taker | initials only |
| Consent to anonymized notes | yes / no |
| Consent to follow-up | yes / no |
| Recording | no (default) |

## Context

- What they run (Linux / VMs / containers / Kubernetes):
- Where the sites are (remote office / factory / retail / cloud region):
- Team shape and on-call model:
- Current tools (metrics, logs, alerts, incident management):

## Incident walkthrough

One real incident, not a hypothetical. Keep the timeline concrete.

| Phase | What happened | Duration | Who / tool |
|---|---|---|---|
| First signal | | | |
| Detection | | | |
| Diagnosis | | | |
| Action | | | |
| Verification | | | |
| Follow-up | | | |

- Impact (customer-facing? cost? travel?):
- What made it harder:
- What they would do differently:

## Workflow and approvals

- Changes that need approval:
- Who approves, and how:
- What is pre-approved vs. per incident:
- What must never be automated:
- How they handle a bad automated action:

## Connectivity, security and data

- Behaviour when the site or central link is down:
- Data that may leave the site:
- Security/compliance review a new tool must pass:
- Audit/retention requirements:

## Tooling gaps and pilot

- Most annoying manual step:
- What a pilot would need to prove:
- Buyer / other stakeholders:
- Referrals offered:

## Quotes (scrubbed)

> "…" — meaning, not identifying detail.

> "…"

## Observations

- Tone, hesitation, workarounds, artefacts shown (describe, do not copy):
- Surprises:

## Hypotheses touched

| Hypothesis | Supported / contradicted / unclear | Evidence |
|---|---|---|
| H2: this is a real, painful problem | | |
| Offline operation matters | | |
| Approval is a blocker for automation | | |
| MSP vs in-house positioning (S6-J1) | | |

## Decisions this interview informs

- Segment fit / kill-pivot rule:
- Action catalogue or autonomy matrix:
- Pilot criteria:
- Positioning:

## Follow-ups

- Clarifications needed:
- Referral requested (yes/no):
- Debrief date (≤ 24 h):

## Debrief (both researchers)

- What we changed in the script:
- What we changed in the product assumptions:
- Next action / owner:
