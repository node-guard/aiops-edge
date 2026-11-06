# Customer discovery interview script (S1-J4)

**Purpose.** Learn how small teams operate Linux/Kubernetes services at remote
sites, with emphasis on real incidents, approvals and offline constraints. This
is discovery, **not a product pitch**. The output feeds H2 (does this solve a
real problem?) and the S6-J1 positioning decision.

**Format.** 45 minutes, remote, one interviewer and one note-taker. Target 8–10
interviews overall, with at least 3 incident walkthroughs. Kill/pivot rule:
after 5 interviews, if fewer than 2 participants operate multi-site Linux
infrastructure, revisit the segment and record the decision in an ADR.

## Target profile

- An MSP, or a small in-house team (2–20 people), running Linux and/or
  Kubernetes workloads at **two or more** sites.
- Someone who is on-call, runs incidents, or approves production changes.
- Ideally both an MSP profile and an in-house profile in the first three slots.

Not a fit: a single-laptop developer, a large platform team with a dedicated
SRE organisation, or someone who cannot discuss an incident without exposing
customer data.

## Recruitment message

Keep it short, specific and free of product claims:

> Hi — we are two software-engineering master's students studying how small
> teams keep Linux/Kubernetes services running at remote sites. We are looking
> for a 45-minute conversation about how you handle incidents today. There is
> no product pitch and no preparation needed. Would you be open to a call in the
> next two weeks? If not, could you point us to someone who runs infrastructure
> across multiple sites?

Screening questions before booking:

1. Do you run Linux/Kubernetes workloads at more than one physical or cloud
   location?
2. Are you involved in incident response, on-call, or change approval?
3. Can you walk us through a recent incident without customer names, hostnames
   or credentials?

Channels: personal network, university alumni, local DevOps/cloud meetups,
relevant community Slacks. No mass outreach and no scraping of contact lists.

## Consent script (read verbatim)

> Thanks for your time. We are two master's students researching how small teams
> operate Linux and Kubernetes services at remote sites. This is discovery, not
> a sales pitch. With your permission I will take notes; I will not record
> audio. Notes stay in private storage and only an anonymized version is kept in
> our repository: a participant ID, your role, a team-size band and a site-count
> band. We will not write down your name, company, email, hostnames, IPs or
> customer data. You can skip any question, ask me to remove something, or stop
> at any time. Do you consent to anonymized notes?

If the participant declines: do not take notes, thank them and end. Do not
record audio without explicit consent; the default is no recording.

## Anonymization rules

- Use `P1`, `P2`, … as the only identifier.
- Record role, team-size band (`1–5`, `6–20`, `21–50`) and site-count band
  (`2–5`, `6–20`, `21+`) only.
- Replace company/product names with `vendor A`, `cloud B`, `tool C`.
- Never write names, emails, phone numbers, hostnames, IPs, customer names,
  tenant IDs or incident ticket IDs.
- Scrub quotes; keep meaning, remove identifying detail.
- Raw notes live in private storage until the end of the PFE, then are deleted.
  The repository contains only the filled `notes-template.md`.

## 45-minute agenda

| Time | Segment | Goal |
|---|---|---|
| 0–3 | Welcome, consent, ground rules | Explicit consent; no recording |
| 3–10 | Context and infrastructure | Segment fit, sites, stack, team |
| 10–25 | Incident walkthrough (core) | A real timeline: detect → diagnose → act → verify |
| 25–33 | Workflow, approvals, automation tolerance | Who decides, what must stay manual |
| 33–38 | Offline/connectivity, security and data rules | Constraints a new platform must respect |
| 38–42 | Tooling gaps, pilot willingness, buying process | Pain severity and next step |
| 42–45 | Closing and referrals | Thanks, follow-up permission, referrals |

If the participant has less than ~30 minutes, keep the incident walkthrough
(10–25) and the automation-tolerance questions; drop the rest.

## Question bank

Every question maps to a decision. Ask open questions; do not lead with the
product. `→` is the decision the answer informs.

### A. Context (7 min)

| # | Question | Decision informed |
|---|---|---|
| A1 | What does your team run, and across how many independent sites? | Segment fit; kill/pivot rule |
| A2 | Which parts are Linux, VMs, containers, Kubernetes? | Relevance of K3s/Prometheus design |
| A3 | How large is the team, and who is on-call? | Persona and staffing assumptions |
| A4 | What does "edge" mean in your setup — remote office, factory, retail, cloud region? | Positioning (S6-J1) |

### B. Incident walkthrough (15 min, core)

Ask for the **last significant incident**, not a hypothetical. Build a timeline
on paper while they talk.

| # | Question | Decision informed |
|---|---|---|
| B1 | What happened first, and how did you find out — alert, customer report, or manual check? | Detection gap; value of local monitoring |
| B2 | What did you look at to diagnose it? Which tools and in what order? | Evidence sources for the investigation agent |
| B3 | How long did detection, diagnosis and recovery each take? | MTTR baseline and H3 metric |
| B4 | Who was involved, and did anyone have to travel or join a call? | Cost of manual correlation |
| B5 | What action fixed it? Was it a restart, scale-out, rollback, config change, or nothing? | Action catalogue realism (ACT-001/002/003) |
| B6 | How did you know it was actually fixed — not just that the command succeeded? | Verification requirement (US-08) |
| B7 | What made it harder: missing data, noisy alerts, access, or the link to the site? | Offline/observability requirements |
| B8 | What did you do afterwards to prevent a repeat? | Runbook/RAG and feedback-loop value |

### C. Workflow, approvals and automation (8 min)

| # | Question | Decision informed |
|---|---|---|
| C1 | Which changes need approval, and who gives it? | L2 approver persona and policy model |
| C2 | What is approved in advance vs. per incident? | Autonomy matrix levels |
| C3 | What would you never let a tool do automatically, even with approval? | Hard safety boundaries |
| C4 | If a tool proposed a typed action with evidence, what would you need to trust it? | Explainability and approval UX |
| C5 | How do you handle a bad automated action today? | Rollback/kill-switch requirements |

### D. Connectivity, security and data (5 min)

| # | Question | Decision informed |
|---|---|---|
| D1 | What happens when the link to a site or to central is down? | Offline autonomy (Scenario B) |
| D2 | Which data may leave the site, and which must stay local? | Data residency and local-first design |
| D3 | What security review would a new agent/tool need to pass? | Adoption blockers; mTLS/RBAC story |
| D4 | Do you have audit/compliance requirements for automated actions? | Audit trail and retention |

### E. Tooling gaps and pilot (4 min)

| # | Question | Decision informed |
|---|---|---|
| E1 | What do you use today for metrics, logs, alerts and incident management? | Integration surface; build-vs-buy |
| E2 | What is the most annoying manual step that remains? | Prioritising the MVP slice |
| E3 | If a controlled non-production pilot existed, what would it need to prove? | Pilot success criteria |
| E4 | Who else would need to say yes, and what is the buying process? | Buyer/persona for S6-J1 |
| E5 | Who else should we talk to? | Recruitment; snowball sampling |

## Probing prompts

- "Can you give me a concrete example?"
- "What did you do next?"
- "How did you know that was the right thing?"
- "What would have happened if you had done nothing?"
- "Who disagreed, and why?"
- "What did that cost — time, money, customer impact?"

Do not ask "would you use a product that…" until the end; prefer past behaviour.

## Closing (2 min)

> That is everything from our side. Is there anything important about how you
> run incidents that we did not ask? May we contact you again if we need to
> clarify a note? And could you point us to one other person who runs
> infrastructure across multiple sites?

Record consent to follow-up (yes/no) in the notes template. Do not add the
participant to any mailing list.

## Interviewer roles

- **Lead:** asks the questions, watches the clock, probes for concrete stories,
  does not pitch.
- **Note-taker:** captures quotes and timeline, marks decisions/hypotheses,
  flags anything identifying for immediate scrubbing.
- **Debrief (within 24 h):** both fill one anonymized template, compare notes,
  record surprises and which hypotheses were supported or contradicted. Update
  the interview tracker (not the repo) and decide whether the kill/pivot rule
  has been triggered.

## Dry run checklist

- [ ] Run the full agenda once with the other student (or a colleague), timer
      visible.
- [ ] Confirm it finishes in ≤ 45 minutes; cut questions that do not earn their
      slot.
- [ ] Fill `notes-template.md` with fake data and review it for accidental
      identifying details.
- [ ] Agree who leads and who notes for each of the first three slots.
- [ ] Confirm where raw notes live and who can access them.

## Slot tracking

Bookings and contact details live in a private calendar, not in this repository.
Only the non-sensitive status below is committed:

| Slot | Profile (role, team-size band, site-count band) | Date/time | Status | Notes |
|---|---|---|---|---|
| P1 | _to fill_ | _private calendar_ | _not booked_ | |
| P2 | _to fill_ | _private calendar_ | _not booked_ | |
| P3 | _to fill_ | _private calendar_ | _not booked_ | |

Use three distinct profiles, ideally at least one MSP and one in-house team.
Record only `booked` / `done` / `declined` here; never a name, company or email.
