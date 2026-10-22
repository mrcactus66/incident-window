import copy
import hashlib
import json
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = "mrcactus66/incident-window"
URL = "https://raw.githubusercontent.com/" + REPO + "/" + "a" * 40 + "/examples/overlap.txt"
BODY = (ROOT / "examples/overlap.txt").read_text()


def policy(body=BODY):
    return {"component": "Aster API", "region": "North", "start": "2026-10-20T10:00:00Z",
        "end": "2026-10-20T11:00:00Z", "budget_seconds": 2400,
        "incident_ids": ["INC-A", "INC-B", "INC-C"],
        "source": {"url": URL, "sha256": hashlib.sha256(body.encode()).hexdigest()}}


def rows():
    lines = BODY.splitlines()
    def line(prefix):
        return next(s for s in lines if s.startswith(prefix))
    return [
        {"id": "INC-A", "scope": "AFFECTED", "scope_quote": line("INC-A: The"), "state": "RESTORED",
         "start": "2026-10-20T09:50:00Z", "end": "2026-10-20T10:20:00Z",
         "start_quote": line("INC-A: The"), "end_quote": line("INC-A: All")},
        {"id": "INC-B", "scope": "AFFECTED", "scope_quote": line("INC-B: The"), "state": "RESTORED",
         "start": "2026-10-20T10:10:00Z", "end": "2026-10-20T10:40:00Z",
         "start_quote": line("INC-B: The"), "end_quote": line("INC-B: Full")},
        {"id": "INC-C", "scope": "OTHER", "scope_quote": line("INC-C: Only"), "state": "RESTORED",
         "start": "2026-10-20T10:00:00Z", "end": "2026-10-20T10:55:00Z",
         "start_quote": line("INC-C: Only"), "end_quote": line("INC-C: South")},
    ]


@pytest.fixture
def contract(direct_deploy):
    return direct_deploy(str(ROOT / "contracts/incident_window.py"), REPO, sdk_version="v0.2.12")


def setup(contract, vm, p=None, evidence=None, body=BODY):
    p = p or policy(body)
    contract.register("window", json.dumps(p))
    mock(vm, evidence or rows(), body)


def mock(vm, evidence, body=BODY, status=200):
    vm.mock_web("^" + re.escape(URL) + "$", {"status": status, "body": body})
    vm.mock_llm("Interpret an incident report", json.dumps({"rows": evidence}))


def review(contract):
    contract.review("window")
    return json.loads(contract.get_review("window"))


def test_overlap_clipping_and_exact_budget(contract, direct_vm):
    setup(contract, direct_vm)
    r = review(contract)
    assert r["downtime_seconds"] == 2400
    assert r["intervals"] == [[0, 2400]]
    assert r["availability_ppm"] == 333333
    assert r["budget_exceeded"] is False
    assert r["policy_sha256"] == hashlib.sha256(contract.get_policy("window").encode()).hexdigest()
    assert direct_vm.run_validator() is True


@pytest.mark.parametrize("budget,exceeded", [(2399, True), (2400, False), (2401, False)])
def test_budget_boundary(contract, direct_vm, budget, exceeded):
    p = policy(); p["budget_seconds"] = budget
    setup(contract, direct_vm, p)
    assert review(contract)["budget_exceeded"] is exceeded


def test_open_is_censored_at_window_end(contract, direct_vm):
    body = (ROOT / "examples/ongoing.txt").read_text()
    p = policy(body); p["incident_ids"] = ["INC-A"]
    row = {"id": "INC-A", "scope": "AFFECTED", "scope_quote": body.splitlines()[1], "state": "OPEN",
        "start": "2026-10-20T10:45:00Z", "end": "", "start_quote": body.splitlines()[1], "end_quote": body.splitlines()[2]}
    setup(contract, direct_vm, p, [row], body)
    r = review(contract)
    assert (r["downtime_seconds"], r["intervals"]) == (900, [[2700, 3600]])
    assert direct_vm.run_validator() is True


def test_mitigation_does_not_supply_a_recovery_time(contract, direct_vm):
    body = (ROOT / "examples/mitigated.txt").read_text()
    p = policy(body); p["incident_ids"] = ["INC-A"]
    row = {"id": "INC-A", "scope": "AFFECTED", "scope_quote": body.splitlines()[1], "state": "UNKNOWN",
        "start": "2026-10-20T10:10:00Z", "end": "", "start_quote": body.splitlines()[1], "end_quote": ""}
    setup(contract, direct_vm, p, [row], body)
    assert review(contract)["status"] == "INCOMPLETE"
    assert not contract.has_complete_accounting("window")
    assert direct_vm.run_validator() is True


def test_unknown_scope_withholds_accounting(contract, direct_vm):
    r = rows(); r[2]["scope"] = "UNKNOWN"
    setup(contract, direct_vm, evidence=r)
    assert review(contract)["status"] == "INCOMPLETE"


def test_other_scope_does_not_need_recovery(contract, direct_vm):
    r = rows(); r[2].update(state="UNKNOWN", start="", end="", start_quote="", end_quote="")
    setup(contract, direct_vm, evidence=r)
    assert review(contract)["downtime_seconds"] == 2400


def test_nonowner_cannot_register_but_can_review(contract, direct_vm, direct_bob):
    with direct_vm.prank(direct_bob), direct_vm.expect_revert("Only owner"):
        contract.register("window", json.dumps(policy()))
    setup(contract, direct_vm)
    with direct_vm.prank(direct_bob):
        review(contract)
    with direct_vm.expect_revert("already reviewed"):
        review(contract)
    with direct_vm.expect_revert("duplicate"):
        contract.register("window", json.dumps(policy()))


@pytest.mark.parametrize("mutation", [
    {"end": "2026-10-20T10:05:00Z"}, {"id": "INC-B"}, {"end_quote": "Invented"},
    {"start": "2026-02-30T09:50:00Z"}, {"state": "OPEN"}, {"scope": "MATCH"},
    {"end": "2026-10-20T09:40:00Z"}, {"start": 42}, {"start_quote": BODY.splitlines()[-1]},
    {"state": "UNKNOWN"}, {"extra": True}, {"scope_quote": ""},
])
def test_invalid_evidence_cannot_create_receipt(contract, direct_vm, mutation):
    r = rows(); r[0].update(mutation)
    setup(contract, direct_vm, evidence=r)
    with direct_vm.expect_revert():
        review(contract)
    assert not contract.has_complete_accounting("window")


@pytest.mark.parametrize("mutation", [
    {"incident_ids": []}, {"incident_ids": ["INC-A", "INC-A"]}, {"budget_seconds": True},
    {"budget_seconds": -1}, {"budget_seconds": 3601}, {"end": "2026-10-20T10:00:00Z"},
    {"component": ""}, {"start": "2026-10-20T10:00:00+00:00"},
])
def test_invalid_policy_rejected(contract, direct_vm, mutation):
    p = policy(); p.update(mutation)
    with direct_vm.expect_revert():
        contract.register("window", json.dumps(p))


@pytest.mark.parametrize("tail", ["main/examples/a.txt", "a"*40+"/../a.txt", "a"*40+"/a.txt?q=1"])
def test_unpinned_and_unsafe_sources_rejected(contract, direct_vm, tail):
    p = policy(); p["source"]["url"] = "https://raw.githubusercontent.com/"+REPO+"/"+tail
    with direct_vm.expect_revert():
        contract.register("window", json.dumps(p))


@pytest.mark.parametrize("mode", ["hash", "http", "empty", "oversize"])
def test_unavailable_report_is_retryable(contract, direct_vm, mode):
    setup(contract, direct_vm)
    direct_vm.clear_mocks()
    mock(direct_vm, rows(), {"hash": BODY+"changed", "http": BODY, "empty": "", "oversize": "x"*16001}[mode], 503 if mode == "http" else 200)
    with direct_vm.expect_revert():
        review(contract)
    assert not contract.has_complete_accounting("window")
    direct_vm.clear_mocks(); mock(direct_vm, rows())
    assert review(contract)["status"] == "COMPLETE"


def test_validator_checks_semantics_and_can_accept_different_quotes(contract, direct_vm):
    setup(contract, direct_vm); review(contract)
    different = rows(); different[0]["scope_quote"] = different[0]["end_quote"]
    direct_vm.clear_mocks(); mock(direct_vm, different)
    assert direct_vm.run_validator() is True
    different[0]["scope"] = "OTHER"
    direct_vm.clear_mocks(); mock(direct_vm, different)
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_structurally_valid_wrong_recovery(contract, direct_vm):
    setup(contract, direct_vm); review(contract)
    r = rows(); r[0]["end"] = "2026-10-20T10:05:00Z"; r[0]["end_quote"] = BODY.splitlines()[4]
    assert direct_vm.run_validator(leader_result=r) is False
    assert direct_vm.run_validator(leader_result=[]) is False
    assert direct_vm.run_validator(leader_error=ValueError("failed")) is False


@pytest.mark.parametrize("endpoints,seconds,intervals", [
    ([(0, 10), (10, 20)], 1200, [[0, 1200]]),
    ([(0, 10), (20, 30)], 1200, [[0, 600], [1200, 1800]]),
    ([(0, 30), (10, 20)], 1800, [[0, 1800]]),
    ([(10, 20), (10, 20)], 600, [[600, 1200]]),
    ([(0, 60)], 3600, [[0, 3600]]),
    ([(60, 70)], 0, []),
])
def test_interval_union_shapes(contract, direct_vm, endpoints, seconds, intervals):
    p = policy(); p["incident_ids"] = ["I"+str(i) for i in range(len(endpoints))]
    r, lines = [], []
    for i, (a, b) in enumerate(endpoints):
        def stamp(minutes):
            return f"2026-10-20T{10+minutes//60:02}:{minutes%60:02}:00Z"
        start, end = stamp(a), stamp(b)
        q = f"I{i}: North Aster API was unavailable from {start} until full recovery at {end}."
        lines.append(q)
        r.append({"id": "I"+str(i), "scope": "AFFECTED", "scope_quote": q,
            "state": "RESTORED", "start": start, "end": end, "start_quote": q, "end_quote": q})
    body = "\n".join(lines)
    p["source"]["sha256"] = hashlib.sha256(body.encode()).hexdigest()
    setup(contract, direct_vm, p, r, body)
    result = review(contract)
    assert (result["downtime_seconds"], result["intervals"]) == (seconds, intervals)


def test_utc_window_crosses_leap_day_and_midnight(contract, direct_vm):
    p = policy(); p.update(start="2024-02-29T23:30:00Z", end="2024-03-01T00:30:00Z", incident_ids=["INC-A"])
    a, b = "2024-02-29T23:45:00Z", "2024-03-01T00:15:00Z"
    q = f"INC-A: North Aster API unavailable from {a} until full recovery at {b}."
    p["source"]["sha256"] = hashlib.sha256(q.encode()).hexdigest()
    r = [{"id": "INC-A", "scope": "AFFECTED", "scope_quote": q, "state": "RESTORED",
          "start": a, "end": b, "start_quote": q, "end_quote": q}]
    setup(contract, direct_vm, p, r, q)
    assert review(contract)["downtime_seconds"] == 1800
