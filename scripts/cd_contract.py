#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

SCHEMA = "nddev-cd-plan/v1"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
DEPLOYMENT = re.compile(r"^deploy_[0-9A-Z]{26}$")
STATES = {
    "DRAFT", "VALIDATED", "PLANNED", "APPROVED", "APPLYING", "VERIFYING", "SUCCEEDED",
    "FAILED_RETRYABLE", "RESUMING", "FAILED_ROLLBACK_REQUIRED", "ROLLING_BACK", "ROLLED_BACK", "BLOCKED",
}
TRANSITIONS = {
    "DRAFT": {"VALIDATED", "BLOCKED"},
    "VALIDATED": {"PLANNED", "BLOCKED"},
    "PLANNED": {"APPROVED", "BLOCKED"},
    "APPROVED": {"APPLYING", "BLOCKED"},
    "APPLYING": {"VERIFYING", "FAILED_RETRYABLE", "FAILED_ROLLBACK_REQUIRED", "BLOCKED"},
    "VERIFYING": {"SUCCEEDED", "FAILED_RETRYABLE", "FAILED_ROLLBACK_REQUIRED", "BLOCKED"},
    "FAILED_RETRYABLE": {"RESUMING", "BLOCKED"},
    "RESUMING": {"APPLYING", "VERIFYING", "FAILED_ROLLBACK_REQUIRED", "BLOCKED"},
    "FAILED_ROLLBACK_REQUIRED": {"ROLLING_BACK", "BLOCKED"},
    "ROLLING_BACK": {"ROLLED_BACK", "FAILED_RETRYABLE", "BLOCKED"},
    "SUCCEEDED": set(), "ROLLED_BACK": set(), "BLOCKED": set(),
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def plan_digest(plan: dict[str, Any]) -> str:
    unsigned = copy.deepcopy(plan)
    unsigned.pop("plan_digest", None)
    return "sha256:" + hashlib.sha256(canonical(unsigned)).hexdigest()


def timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def validate_plan(plan: dict[str, Any], *, now: dt.datetime | None = None) -> None:
    required = {
        "schema", "deployment_id", "idempotency_key", "created_at", "expires_at", "estate",
        "module_lock_sha256", "modules", "artifact_manifest_digest", "target",
        "previous_state_digest", "operations", "health", "plan_digest",
    }
    if set(plan) != required or plan["schema"] != SCHEMA:
        raise ValueError("plan fields or schema differ from v1")
    if not DEPLOYMENT.fullmatch(plan["deployment_id"]):
        raise ValueError("invalid deployment_id")
    if not 1 <= len(plan["idempotency_key"]) <= 128:
        raise ValueError("invalid idempotency_key")
    created, expires = timestamp(plan["created_at"]), timestamp(plan["expires_at"])
    if expires <= created or expires - created > dt.timedelta(hours=24):
        raise ValueError("plan lifetime must be positive and at most 24 hours")
    if now is not None and expires <= now.astimezone(dt.timezone.utc):
        raise ValueError("plan is stale")
    if not SHA.fullmatch(plan["estate"].get("sha", "")) or "/" not in plan["estate"].get("repository", ""):
        raise ValueError("invalid estate identity")
    digests = [plan["module_lock_sha256"], plan["artifact_manifest_digest"], plan["previous_state_digest"], plan["target"].get("inventory_fingerprint", ""), plan["health"].get("query_contract_digest", "")]
    if any(not DIGEST.fullmatch(value) for value in digests):
        raise ValueError("invalid content digest")
    modules = plan["modules"]
    if not modules or len({row["name"] for row in modules}) != len(modules) or any(not SHA.fullmatch(row.get("sha", "")) for row in modules):
        raise ValueError("invalid or duplicate module identity")
    operations = plan["operations"]
    ids = [row.get("id", "") for row in operations]
    if not operations or len(ids) != len(set(ids)):
        raise ValueError("operation ids must be non-empty and unique")
    seen: set[str] = set()
    kinds = {"install-artifact", "write-config", "restart-service", "provider-reconcile", "verify-health"}
    for operation in operations:
        if operation.get("kind") not in kinds or not DIGEST.fullmatch(operation.get("target_digest", "")):
            raise ValueError("operation kind or target digest is invalid")
        if not 1 <= operation.get("timeout_seconds", 0) <= 3600:
            raise ValueError("operation timeout is invalid")
        dependencies = operation.get("depends_on")
        if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)) or any(dep not in seen for dep in dependencies):
            raise ValueError("operations must be topologically ordered")
        if operation.get("rollback") not in {"restore-previous", "compensate", "none-read-only"}:
            raise ValueError("operation rollback contract is invalid")
        seen.add(operation["id"])
    if plan["health"].get("failure_action") not in {"resume", "rollback-required"}:
        raise ValueError("health failure action is invalid")
    if plan["plan_digest"] != plan_digest(plan):
        raise ValueError("plan digest mismatch")


def validate_state(state: dict[str, Any], plan: dict[str, Any]) -> None:
    if state.get("schema") != "nddev-cd-state/v1" or state.get("state") not in STATES:
        raise ValueError("invalid deployment state schema")
    if state.get("deployment_id") != plan["deployment_id"] or state.get("plan_digest") != plan["plan_digest"]:
        raise ValueError("state is not bound to the exact plan")
    if not isinstance(state.get("generation"), int) or state["generation"] < 1 or not state.get("history"):
        raise ValueError("state generation or history is invalid")
    timestamp(state["updated_at"])


def transition(state: dict[str, Any], target: str, plan: dict[str, Any], at: str) -> dict[str, Any]:
    validate_plan(plan)
    validate_state(state, plan)
    current = state["state"]
    if target not in TRANSITIONS[current]:
        raise ValueError(f"transition {current}->{target} is not allowed")
    result = copy.deepcopy(state)
    result["state"] = target
    result["generation"] += 1
    result["updated_at"] = timestamp(at).isoformat().replace("+00:00", "Z")
    result["history"].append({"from": current, "to": target, "at": result["updated_at"]})
    return result


def load(path: str) -> dict[str, Any]:
    value = json.loads(pathlib.Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError("document must be a JSON object")
    return value


def write(path: str, value: dict[str, Any]) -> None:
    pathlib.Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-schema")
    seal = sub.add_parser("seal"); seal.add_argument("input"); seal.add_argument("output")
    validate = sub.add_parser("validate-plan"); validate.add_argument("plan"); validate.add_argument("--now")
    move = sub.add_parser("transition"); move.add_argument("plan"); move.add_argument("state"); move.add_argument("target"); move.add_argument("output"); move.add_argument("--at", required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate-schema":
            for path in pathlib.Path("schemas/v1").glob("*.json"):
                json.loads(path.read_text())
            return 0
        if args.command == "seal":
            plan = load(args.input); plan["plan_digest"] = plan_digest(plan); validate_plan(plan); write(args.output, plan); return 0
        if args.command == "validate-plan":
            now = timestamp(args.now) if args.now else None; validate_plan(load(args.plan), now=now); return 0
        if args.command == "transition":
            plan = load(args.plan); result = transition(load(args.state), args.target, plan, args.at); write(args.output, result); return 0
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"cd-contract: {error}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
