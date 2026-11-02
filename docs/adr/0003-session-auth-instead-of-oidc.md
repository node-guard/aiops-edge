# ADR-0003: Local-user session authentication; OIDC deferred

- Status: Accepted
- Date: 2026-11-02
- Owner: Student A

## Context
OIDC with a self-hosted Keycloak adds deployment and debugging cost that does not advance the research questions.

## Decision
Local users with argon2id password hashes, server-side sessions (opaque id in HttpOnly/Secure/SameSite=Lax cookie), CSRF protection on state-changing requests, roles operator/approver/viewer. Keep the auth module behind an interface so OIDC can be added later.

## Consequences
Faster S6. MFA and SSO are documented as future work. Security tests still cover session rotation, expiry and CSRF.
