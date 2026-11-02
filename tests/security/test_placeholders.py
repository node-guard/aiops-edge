"""Security test placeholders (SPEC section 12).

Replace each with a real test as the boundary code lands. They are xfail(strict=False) so the
suite documents required coverage while staying green.
"""

import pytest

REQUIRED = [
    "tenant_a_cannot_read_tenant_b_incident",
    "expired_or_revoked_site_cert_rejected",
    "payload_site_id_must_match_cert",
    "observer_cannot_read_secrets_exec_or_patch",
    "executor_limited_to_allowlist",
    "modified_approval_payload_rejected",
    "expired_command_not_executed",
    "duplicate_command_not_repeated",
    "expired_policy_disables_auto_remediation",
    "prompt_injection_cannot_cause_privileged_execution",
    "credentials_absent_from_logs_and_llm_payloads",
    "critical_actions_have_complete_audit",
]


@pytest.mark.xfail(reason="not implemented yet", strict=False)
@pytest.mark.parametrize("name", REQUIRED)
def test_required_security_case(name):
    raise NotImplementedError(name)
