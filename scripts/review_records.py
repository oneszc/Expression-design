#!/usr/bin/env python3
"""Validate immutable review fragments and assemble a provenance-preserving report."""
import argparse
import copy
import errno
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath

LIMITS = {"identity": 25, "expression": 25, "craft": 35, "legibility": 15}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    # Publish a complete file exclusively: an interrupted write is not a valid fragment.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        try:
            os.link(temporary, path)
        except OSError as exc:
            if exc.errno not in (errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS):
                raise
            # Filesystems without hard links still get exclusive, non-clobbering writes.
            # A killed fallback write can be partial; JSON/hash checks reject it on resume.
            with path.open("x", encoding="utf-8") as fallback:
                fallback.write(payload)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def assets(manifest):
    return [item["file"] for item in manifest["stickers"]] + [manifest[k] for k in ("banner", "cover", "icon")]


def asset_path(manifest_path, name):
    relative = PurePosixPath(name)
    require(isinstance(name, str) and not relative.is_absolute() and ".." not in relative.parts
            and "\\" not in name and relative.as_posix() == name and name != "manifest.json",
            f"Invalid asset path: {name}")
    root = Path(manifest_path).resolve().parent
    result = (root / name).resolve()
    require(result.is_relative_to(root), f"Asset outside delivery: {name}")
    return result


def item_errors(item, animated=False, role=None):
    if not isinstance(item, dict):
        return ["review item must be an object"]
    errors = []
    def check(ok, text):
        if not ok:
            errors.append(text)
    check(item.get("stage") in ("draft", "final"), "stage must be draft or final")
    check(isinstance(item.get("reviewer_id"), str) and bool(item["reviewer_id"].strip()), "reviewer_id required")
    check(isinstance(item.get("sha256"), str) and len(item["sha256"]) == 64, "sha256 required")
    checks = item.get("checks", {})
    required = ["light", "dark"] + (["all_frames"] if animated else []) + ([role + "_design"] if role else [])
    missing = [key for key in required if not isinstance(checks, dict) or checks.get(key) is not True]
    if animated and (not isinstance(checks, dict) or checks.get("playback") is not True):
        missing.append("playback")
    unchecked = item.get("unchecked")
    check(isinstance(unchecked, list) and all(isinstance(v, str) for v in unchecked), "unchecked must be a list")
    if isinstance(unchecked, list):
        check(set(missing) == set(unchecked), "unchecked must exactly name missing required checks")
    scores = item.get("scores", {})
    check(isinstance(scores, dict) and set(scores) == set(LIMITS), "four scores required")
    valid_scores = isinstance(scores, dict) and set(scores) == set(LIMITS) and all(
        type(scores[k]) is int and 0 <= scores[k] <= n for k, n in LIMITS.items())
    # Missing playback alone permits a frame-only provisional score; never a final total.
    frame_only = animated and missing == ["playback"] and item.get("scope") == "frames"
    if not missing or frame_only:
        check(valid_scores, "observed/provisional scores must be bounded integers")
    else:
        check(item.get("decision") == "blocked" and isinstance(scores, dict)
              and scores.get("craft") is None, "missing observations require blocked and unknown craft")
    evidence = item.get("evidence", {})
    check(isinstance(evidence, dict) and all(isinstance(evidence.get(k), str) and evidence[k].strip()
                                           for k in LIMITS), "four evidence entries required")
    critical = item.get("critical_issues")
    check(isinstance(critical, list), "critical_issues must be a list")
    decision = item.get("decision")
    check(decision in ("pass", "revise", "blocked"), "invalid decision")
    if missing:
        check(decision == "blocked", "missing observation cannot pass or trigger regeneration")
    elif critical or (valid_scores and (sum(scores.values()) <= 80 or scores["expression"] < 18)):
        check(decision == "revise", "defect/score failure must revise")
    else:
        check(decision == "pass", "complete passing review must pass")
    if frame_only:
        check(item.get("total") is None, "frame-only review cannot claim final total")
    if animated and not missing:
        check(isinstance(item.get("playback_evidence"), str) and bool(item["playback_evidence"].strip()), "playback evidence required")
    if role and isinstance(checks, dict) and checks.get(role + "_design") is True:
        check(isinstance(item.get("platform_evidence"), str) and bool(item["platform_evidence"].strip()), "platform evidence required")
    return errors


def assemble(manifest_path, fragments, batch_path, acceptance=None):
    manifest_path = Path(manifest_path)
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest)
    names = assets(manifest)
    records, provenance = {}, []
    for fragment in fragments:
        raw = Path(fragment).read_bytes()
        source = json.loads(raw)
        require(isinstance(source, dict) and source.get("schema_version") == 2
                and isinstance(source.get("items"), list) and source["items"]
                and all(isinstance(i, dict) for i in source["items"]), "Fragments require schema_version 2 items")
        for item in source["items"]:
            name = item["file"]
            require(name in names and name not in records, f"Unknown/duplicate review: {name}")
            role = next((k for k in ("banner", "cover", "icon") if manifest[k] == name), None)
            animated = manifest["mode"] == "animated" and role is None
            errors = item_errors(item, animated, role)
            require(not errors, f"{name}: " + "; ".join(errors))
            require(digest(asset_path(manifest_path, name).read_bytes()) == item["sha256"], f"Stale review: {name}")
            records[name] = copy.deepcopy(item)
        provenance.append({"source": str(Path(fragment).resolve()), "sha256": digest(raw), "raw": raw.decode("utf-8"), "record": source})
    require(set(records) == set(names), "Review coverage incomplete; keep fragments and resume missing items")
    batch_source = read(batch_path)
    require(isinstance(batch_source, dict) and isinstance(batch_source.get("batch"), dict), "Batch object required")
    require(batch_source.get("manifest_sha256") == digest(raw_manifest), "Batch manifest is stale")
    expected_hashes = {name: records[name]["sha256"] for name in names}
    require(batch_source.get("asset_hashes") == expected_hashes, "Batch asset set is stale")
    require(bool(batch_source.get("reviewer_id")), "Batch reviewer_id required")
    batch = copy.deepcopy(batch_source["batch"])
    require(type(batch.get("score")) is int and 0 <= batch["score"] <= 100, "Invalid batch score")
    require(isinstance(batch.get("evidence"), str) and batch["evidence"].strip(), "Batch evidence required")
    require(isinstance(batch.get("critical_issues"), list), "Batch defects required")
    require(batch.get("unchecked") in ([], ["playback"]), "Unresolved batch observations")
    expected_decision = "blocked" if batch["unchecked"] else ("revise" if batch["critical_issues"] or batch["score"] <= 80 else "pass")
    require(batch.get("decision") == expected_decision, "Contradictory batch decision")
    accepted = {}
    human = None
    if acceptance:
        human = read(acceptance)
        require(isinstance(human, dict) and human.get("schema_version") == 1 and human.get("observer_type") == "human", "Human acceptance required")
        require(all(isinstance(human.get(k), str) and human[k].strip() for k in ("observer", "confirmed_at", "user_confirmation")), "Confirmation attribution required")
        require(isinstance(human.get("items"), list) and all(isinstance(i, dict) for i in human["items"]), "Acceptance items must be objects")
        for entry in human["items"]:
            name = entry["file"]
            require(name in records and name not in accepted and manifest["mode"] == "animated"
                    and name in {i["file"] for i in manifest["stickers"]}, "Unknown/duplicate/non-animated acceptance item")
            require(entry.get("sha256") == records[name]["sha256"], f"Stale acceptance: {name}")
            require(type(entry.get("speed")) in (int, float) and entry.get("speed") == 1 and type(entry.get("loops")) is int and entry["loops"] >= 2
                    and entry.get("light") is True and entry.get("dark") is True and entry.get("decision") == "pass"
                    and isinstance(entry.get("evidence"), str) and entry["evidence"].strip(), f"Incomplete playback acceptance: {name}")
            accepted[name] = entry
    for name, item in records.items():
        if item.get("unchecked") == ["playback"] and name in accepted:
            scores = item["scores"]
            item["checks"]["playback"] = True
            item["playback_evidence"] = {"observer_type": "human", "observer": human["observer"],
                                        "confirmed_at": human["confirmed_at"], **accepted[name]}
            item["unchecked"] = []
            item["decision"] = "pass" if not item["critical_issues"] and sum(scores.values()) > 80 and scores["expression"] >= 18 else "revise"
            item["scope"] = "frames_and_human_playback"
    if batch["unchecked"] == ["playback"] and all(v["decision"] == "pass" for v in records.values()):
        batch["unchecked"] = []
        batch["decision"] = "pass" if batch["score"] > 80 and not batch["critical_issues"] else "revise"
    return {"schema_version": 2, "reviewer_id": batch_source["reviewer_id"],
            "manifest_sha256": digest(raw_manifest), "items": list(records.values()), "batch": batch,
            "provenance": {"fragments": provenance, "batch": batch_source, "human_acceptance": human}}


def verify_assembled(manifest_path, report):
    """Rebuild derived decisions from embedded originals; never trust edited totals."""
    provenance = report.get("provenance", {})
    require(isinstance(provenance, dict), "Provenance object required")
    with tempfile.TemporaryDirectory(prefix="expression-reviews-") as directory:
        root = Path(directory)
        fragments = []
        for i, source in enumerate(provenance.get("fragments", [])):
            fragment = root / f"part-{i}.json"
            require(digest(source["raw"].encode("utf-8")) == source["sha256"]
                    and json.loads(source["raw"]) == source["record"], "Original fragment changed")
            fragment.write_text(source["raw"], encoding="utf-8")
            fragments.append(fragment)
        require(fragments, "Original review fragments required")
        batch = root / "batch.json"
        write_new(batch, provenance["batch"])
        acceptance = None
        if provenance.get("human_acceptance") is not None:
            acceptance = root / "acceptance.json"
            write_new(acceptance, provenance["human_acceptance"])
        rebuilt = assemble(manifest_path, fragments, batch, acceptance)
        for key in ("reviewer_id", "manifest_sha256", "items", "batch"):
            require(rebuilt[key] == report.get(key), f"Assembled {key} differs from original evidence")


def check_fragments(manifest_path, fragments):
    manifest = read(manifest_path)
    names = assets(manifest)
    seen = set()
    for fragment in fragments:
        source = read(fragment)
        require(isinstance(source, dict) and source.get("schema_version") == 2
                and isinstance(source.get("items"), list) and source["items"]
                and all(isinstance(i, dict) for i in source["items"]), "Schema 2 items required")
        for item in source["items"]:
            name = item["file"]
            require(name in names and name not in seen, "Unknown/duplicate item")
            seen.add(name)
            role = next((k for k in ("banner", "cover", "icon") if manifest[k] == name), None)
            errors = item_errors(item, manifest["mode"] == "animated" and role is None, role)
            require(not errors, f"{name}: " + "; ".join(errors))
            require(digest(asset_path(manifest_path, name).read_bytes()) == item["sha256"], f"Stale review: {name}")
    return {"valid": True, "checked_items": sorted(seen), "remaining": [n for n in names if n not in seen]}


def summary(report):
    rows = ["# 评审汇总（程序生成）", "", "分数、缺项与证据来自原始记录，未检查播放的分数仅为逐帧暂评。", "",
            "| 文件 | 评审者 | 四维分数 | 总分 | 结论 | 未检查 |", "|---|---|---|---|---|---|"]
    for item in report["items"]:
        values = item["scores"]
        total = sum(values.values()) if not item["unchecked"] and all(type(v) is int for v in values.values()) else "未完成"
        safe = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
        rows.append("| " + " | ".join(safe(v) for v in [item["file"], item["reviewer_id"],
                    "/".join(str(values[k]) for k in LIMITS), total, item["decision"], ", ".join(item["unchecked"])]) + " |")
    rows.extend(["", "整套：" + report["batch"]["decision"], ""])
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--fragments", nargs="+", required=True, type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.check_only:
            print(json.dumps(check_fragments(args.manifest, args.fragments), ensure_ascii=False))
            return 0
        require(args.batch is not None and args.output is not None, "--batch and --output required for assembly")
        if args.summary:
            require(not args.summary.exists(), "Summary already exists")
        result = assemble(args.manifest, args.fragments, args.batch, args.acceptance)
        write_new(args.output, result)
        if args.summary:
            with args.summary.open("x", encoding="utf-8") as handle:
                handle.write(summary(result))
        print(json.dumps({"report": str(args.output), "ready": all(i["decision"] == "pass" and i["stage"] == "final" for i in result["items"]) and result["batch"]["decision"] == "pass"}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
