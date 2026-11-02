# ADR-0010: Add a predictive exhaustion module to the MVP

- Status: Accepted
- Date: 2026-11-02
- Owner: Student B

## Context
The official subject lists predictive analytics as a key AIOps functionality; the original spec only had a growth-rate feature.

## Decision
Add forecasting of disk and memory time-to-exhaustion (`node.resource.exhaustion_predicted`), compared against `predict_linear`, with faults F17/F18 and H1b.

## Consequences
Small extra detector component; extra experiments; closes a coverage gap with the subject.
