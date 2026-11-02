# Customer discovery interview script

Goal: learn about real incidents and constraints; do not pitch. Target 8-10 interviews, ≥ 3 incident walkthroughs. Ask permission before notes; anonymize in the repo. Kill/pivot rule: after 5 interviews, if fewer than 2 operate multi-site Linux infrastructure, revisit the segment (record the decision in an ADR).

1. What infrastructure do you manage and how many independent sites are involved?
2. What Linux, VM, Docker or Kubernetes workloads run at each site?
3. Describe the last significant incident: how was it discovered and diagnosed?
4. How long did investigation and recovery take? Did anyone travel to the site?
5. What happens when the central link is unavailable?
6. Which tools provide metrics, logs, alerts and incident management today?
7. What stays manual or fragmented?
8. What is already automated and what needs approval?
9. What security or data-residency rules apply to a new platform?
10. Who approves a purchase, and what must a successful pilot prove?
11. Would you consider a controlled non-production pilot? Who else should we talk to?

Log template (one file per interview, anonymized): date, role/segment, number of sites, stack, incident story, pain intensity (1-5), current tools, willingness for pilot, follow-ups.
