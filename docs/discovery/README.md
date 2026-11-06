# Discovery folder

Instruments for customer discovery (H2 and S6-J1). No personal data belongs in
this repository.

| File | Purpose |
|---|---|
| `interview-script.md` | Consent, 45-minute agenda, question bank (each question maps to a decision), interviewer roles, dry-run checklist, slot tracker |
| `notes-template.md` | Anonymized notes for one participant (`P1`, `P2`, …); no name, company or email fields |

## Data handling

- Raw notes and calendar invites live in private storage, not in git.
- The repository holds only anonymized templates: participant ID, role,
  team-size band, site-count band, quotes scrubbed of identifiers.
- Never commit names, emails, phone numbers, hostnames, IPs, tenant IDs or
  customer data.
- Delete raw notes at the end of the PFE.
- Record audio only with explicit consent; the default is notes only.

## Status

- Script prepared; first dry run and the three bookings are tracked in
  `interview-script.md` and remain a human step.
- After 5 interviews, apply the kill/pivot rule: fewer than 2 participants
  operating multi-site Linux infrastructure means revisiting the segment and
  recording the decision in an ADR.
