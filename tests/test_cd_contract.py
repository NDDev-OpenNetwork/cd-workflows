import copy
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cd_contract", ROOT / "scripts/cd_contract.py")
contract = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(contract)


def digest(char: str) -> str:
    return "sha256:" + char * 64


def plan() -> dict:
    value = {
        "schema": "nddev-cd-plan/v1",
        "deployment_id": "deploy_01M0Q000000000000000000000",
        "idempotency_key": "example-production-1",
        "created_at": "2026-08-23T10:00:00Z",
        "expires_at": "2026-08-23T11:00:00Z",
        "estate": {"repository": "example-org/example-estate", "sha": "a" * 40},
        "module_lock_sha256": digest("b"),
        "modules": [{"name": "example-engine", "sha": "c" * 40}],
        "artifact_manifest_digest": digest("d"),
        "target": {"environment": "example-production", "inventory_fingerprint": digest("e")},
        "previous_state_digest": digest("f"),
        "operations": [
            {"id": "install", "kind": "install-artifact", "depends_on": [], "target_digest": digest("1"), "timeout_seconds": 300, "rollback": "restore-previous"},
            {"id": "verify", "kind": "verify-health", "depends_on": ["install"], "target_digest": digest("2"), "timeout_seconds": 120, "rollback": "none-read-only"},
        ],
        "health": {"query_contract_digest": digest("3"), "success_threshold": 3, "failure_action": "rollback-required"},
    }
    value["plan_digest"] = contract.plan_digest(value)
    return value


class ContractTests(unittest.TestCase):
    def test_valid_plan(self):
        contract.validate_plan(plan(), now=dt.datetime(2026, 8, 23, 10, 30, tzinfo=dt.timezone.utc))

    def test_tamper_rejected(self):
        value = plan(); value["target"]["environment"] = "other"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            contract.validate_plan(value)

    def test_stale_plan_rejected(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            contract.validate_plan(plan(), now=dt.datetime(2026, 8, 23, 12, 0, tzinfo=dt.timezone.utc))

    def test_operation_dependency_must_be_prior(self):
        value = plan(); value["operations"][0]["depends_on"] = ["verify"]; value["plan_digest"] = contract.plan_digest(value)
        with self.assertRaisesRegex(ValueError, "topologically"):
            contract.validate_plan(value)

    def test_state_is_plan_bound_and_terminal(self):
        value = plan()
        state = {"schema": "nddev-cd-state/v1", "deployment_id": value["deployment_id"], "plan_digest": value["plan_digest"], "state": "DRAFT", "generation": 1, "updated_at": value["created_at"], "history": [{"from": None, "to": "DRAFT", "at": value["created_at"]}]}
        for target in ("VALIDATED", "PLANNED", "APPROVED", "APPLYING", "VERIFYING", "SUCCEEDED"):
            state = contract.transition(state, target, value, "2026-08-23T10:01:00Z")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            contract.transition(state, "APPLYING", value, "2026-08-23T10:02:00Z")

    def test_retry_and_rollback_paths(self):
        value = plan()
        base = {"schema": "nddev-cd-state/v1", "deployment_id": value["deployment_id"], "plan_digest": value["plan_digest"], "state": "APPLYING", "generation": 5, "updated_at": value["created_at"], "history": [{"from": "APPROVED", "to": "APPLYING", "at": value["created_at"]}]}
        failed = contract.transition(copy.deepcopy(base), "FAILED_RETRYABLE", value, "2026-08-23T10:02:00Z")
        resumed = contract.transition(failed, "RESUMING", value, "2026-08-23T10:03:00Z")
        contract.transition(resumed, "APPLYING", value, "2026-08-23T10:04:00Z")
        rollback = contract.transition(copy.deepcopy(base), "FAILED_ROLLBACK_REQUIRED", value, "2026-08-23T10:02:00Z")
        rollback = contract.transition(rollback, "ROLLING_BACK", value, "2026-08-23T10:03:00Z")
        contract.transition(rollback, "ROLLED_BACK", value, "2026-08-23T10:04:00Z")


if __name__ == "__main__":
    unittest.main()
