"""
Backend smoke/benchmark runner.
Run after starting the backend: python smoke_test.py
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE = "http://127.0.0.1:8765"
PASS = "✓"
FAIL = "✗"
BENCHMARK_PATH = Path(__file__).with_name("generation_benchmark.json")


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as response:
        return json.loads(response.read())


def _post(path: str, body: Dict[str, Any], timeout: int = 90) -> Dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def check(label: str, ok: bool, detail: str = "") -> bool:
    sym = PASS if ok else FAIL
    msg = f"  {sym}  {label}"
    if detail:
        msg += f"  ->  {detail}"
    print(msg)
    return ok


def _load_cases() -> List[Dict[str, Any]]:
    payload = json.loads(BENCHMARK_PATH.read_text())
    return payload.get("cases", [])


def main() -> int:
    print("\n=== AI PCB Backend Benchmark ===\n")
    all_passed = True

    try:
        health = _get("/health")
        all_passed &= check(
            "/health",
            health.get("status") in {"ok", "ready"},
            f"llm={health.get('llm_loaded')} templates={health.get('templates_available')}"
        )
    except Exception as exc:
        all_passed &= check("/health", False, str(exc))

    try:
        templates = _get("/templates")
        names = [item.get("name") for item in templates]
        all_passed &= check(
            "/templates",
            isinstance(templates, list) and len(templates) >= 1,
            str(names),
        )
    except Exception as exc:
        all_passed &= check("/templates", False, str(exc))

    print()
    for case in _load_cases():
        body: Dict[str, Any] = {
            "prompt": case["prompt"],
            "priority": case.get("priority", "quality"),
        }
        if case.get("constraints"):
            body["constraints"] = case["constraints"]
        try:
            t0 = time.time()
            result = _post("/generate", body)
            elapsed = time.time() - t0
            ok = result.get("success") is True
            mode_ok = case.get("expected_generation_mode") in (None, result.get("generation_mode"))
            support_value = result.get("support_status")
            support_ok = case.get("expected_support_status") in (None, support_value)
            if support_value is None:
                support_detail = "missing (restart backend to load latest API)"
            else:
                support_detail = support_value
            all_passed &= check(
                case["name"],
                ok and mode_ok and support_ok,
                f"mode={result.get('generation_mode')} support={support_detail} template={result.get('template_used')} time={elapsed:.1f}s",
            )
            if result.get("warnings"):
                print("     warnings:", " | ".join(result.get("warnings", [])[:2]))
        except urllib.error.HTTPError as exc:
            all_passed &= check(case["name"], False, f"HTTP {exc.code}")
        except Exception as exc:
            all_passed &= check(case["name"], False, str(exc))

    print()
    if all_passed:
        print(f"  {PASS}  Benchmark passed.\n")
        return 0

    print(f"  {FAIL}  Benchmark found failures.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
