"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

try:
    from lab8.console import utf8_stdio
except ModuleNotFoundError as exc:
    if exc.name not in {"lab8", "lab8.console"}:
        raise

    def utf8_stdio() -> None:
        return None

import yaml

from lab9 import stats
from lab9.graders import GRADERS

SPEC = Path("config/metric_spec.yaml")


def load_spec(path: Path = SPEC) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def per_item(report: dict, metric: str, slice_name: str | None = None) -> dict[str, float]:
    acc: dict[str, list[float]] = {}
    for row in report["rows"]:
        if slice_name is not None and slice_name not in (row.get("slices") or []):
            continue
        if row.get(metric) is not None:
            acc.setdefault(row["item_id"], []).append(float(row[metric]))
    return {item_id: sum(values) / len(values) for item_id, values in acc.items()}


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    for metric_id, value in (pr.get("metrics") or {}).items():
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            problems.append(f"metric {metric_id} is NaN/inf")
    manifest = pr.get("manifest") or {}
    rows = pr.get("rows") or []
    items = manifest.get("items")
    seeds = manifest.get("seeds") or []
    expected_rows = None if items is None else int(items) * len(seeds)
    if expected_rows is not None and len(rows) != expected_rows:
        problems.append(f"row count {len(rows)} != {expected_rows} ({items} items × {len(seeds)} seeds)")
    pr_keys = {(r.get("item_id"), r.get("seed")) for r in rows}
    base_keys = {(r.get("item_id"), r.get("seed")) for r in (base.get("rows") or [])}
    if pr_keys != base_keys:
        problems.append("row key set differs from baseline")
    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures non-empty")
    metric_ids = [m["id"] for m in (spec.get("metrics") or []) if m.get("id") in GRADERS]
    for row in rows:
        for metric_id in metric_ids:
            value = row.get(metric_id)
            if value is None:
                problems.append(f"row {row.get('item_id')}@{row.get('seed')} missing {metric_id}")
            elif isinstance(value, (int, float)) and not math.isfinite(float(value)):
                problems.append(f"row {row.get('item_id')}@{row.get('seed')} metric {metric_id} is NaN/inf")
    same_version = (base_spec is not None
                    and spec.get("eval_set_version") == base_spec.get("eval_set_version"))
    if same_version:
        base_metrics = {m["id"]: m for m in (base_spec.get("metrics") or []) if m.get("id")}
        spec_metrics = {m["id"]: m for m in (spec.get("metrics") or []) if m.get("id")}
        for metric_id in sorted(set(base_metrics) | set(spec_metrics)):
            if metric_id not in spec_metrics:
                problems.append(f"metric {metric_id} disappeared from spec")
                continue
            if metric_id not in base_metrics:
                continue
            base_threshold = (base_metrics[metric_id].get("threshold") or {})
            spec_threshold = (spec_metrics[metric_id].get("threshold") or {})
            for field in ("max", "min", "max_increase"):
                if field in base_threshold and field not in spec_threshold:
                    problems.append(f"metric {metric_id} threshold {field} disappeared")
                elif field in spec_threshold and field in base_threshold:
                    if field == "max" and spec_threshold[field] > base_threshold[field]:
                        problems.append(f"metric {metric_id} threshold {field} loosened")
                    elif field == "min" and spec_threshold[field] < base_threshold[field]:
                        problems.append(f"metric {metric_id} threshold {field} loosened")
                    elif field == "max_increase" and spec_threshold[field] > base_threshold[field]:
                        problems.append(f"metric {metric_id} threshold {field} loosened")
            if (base_threshold.get("no_significant_drop")
                    and not spec_threshold.get("no_significant_drop")):
                problems.append(f"metric {metric_id} dropped no_significant_drop")
            if bool(base_metrics[metric_id].get("blocking")) and not bool(spec_metrics[metric_id].get("blocking")):
                problems.append(f"metric {metric_id} became non-blocking")
        base_slices = {(s.get("name"), s.get("metric")): s for s in (base_spec.get("slices") or []) if s.get("name")}
        spec_slices = {(s.get("name"), s.get("metric")): s for s in (spec.get("slices") or []) if s.get("name")}
        for key in sorted(set(base_slices) | set(spec_slices)):
            if key not in spec_slices:
                problems.append(f"slice {key[0]}/{key[1]} disappeared from spec")
                continue
            if key not in base_slices:
                continue
            base_slice = base_slices[key]
            spec_slice = spec_slices[key]
            if "min" in base_slice and "min" not in spec_slice:
                problems.append(f"slice {key[0]}/{key[1]} threshold min disappeared")
            elif "min" in base_slice and spec_slice["min"] < base_slice["min"]:
                problems.append(f"slice {key[0]}/{key[1]} threshold min loosened")
            if bool(base_slice.get("blocking")) and not bool(spec_slice.get("blocking")):
                problems.append(f"slice {key[0]}/{key[1]} became non-blocking")
            if bool(base_slice.get("no_significant_drop")) and not bool(spec_slice.get("no_significant_drop")):
                problems.append(f"slice {key[0]}/{key[1]} dropped no_significant_drop")
    pr_item_slices: dict[str, set[str]] = {}
    base_item_slices: dict[str, set[str]] = {}
    for row in rows:
        pr_item_slices.setdefault(row.get("item_id"), set()).update(row.get("slices") or [])
    for row in (base.get("rows") or []):
        base_item_slices.setdefault(row.get("item_id"), set()).update(row.get("slices") or [])
    if pr_item_slices != base_item_slices:
        problems.append("slice tags differ from baseline")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    for entry in spec.get("slices") or []:
        name = entry.get("name")
        metric = entry.get("metric")
        if not name or not metric:
            continue
        pr_slice = per_item(pr, metric, name)
        base_slice = per_item(base, metric, name)
        value = sum(pr_slice.values()) / len(pr_slice) if pr_slice else None
        fail = value is None
        if value is not None and entry.get("min") is not None and value < entry["min"]:
            fail = True
        keys = sorted(set(pr_slice) & set(base_slice))
        if entry.get("no_significant_drop") and keys:
            bootstrap = spec.get("bootstrap", {})
            d, lo, hi = stats.paired_bootstrap([pr_slice[k] for k in keys], [base_slice[k] for k in keys],
                                               n_resamples=bootstrap.get("n_resamples", 1000),
                                               rng=bootstrap.get("rng", 2027),
                                               confidence=bootstrap.get("confidence", 0.95))
            if hi < 0:
                fail = True
        elif entry.get("no_significant_drop"):
            fail = True
        if fail and entry.get("blocking"):
            blocked.append(f"slice:{name}/{metric}")
        state = "BLOCK" if (fail and entry.get("blocking")) else ("ok" if not fail else "warn")
        lines.append(f"  slice:{name}/{metric:<24} value={value!s:<8} threshold={entry.get('min')!s:<8} {state}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
