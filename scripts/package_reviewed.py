#!/usr/bin/env python3
"""Package only a complete, current delivery with passing independent reviews."""

import argparse
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from validate_pack import validate


LIMITS = {"identity": 25, "expression": 25, "craft": 35, "legibility": 15}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def passing(record, label):
    require(isinstance(record, dict), f"{label}: missing review")
    require(record.get("decision") == "pass", f"{label}: review has not passed")
    require(record.get("critical_issues") == [], f"{label}: critical issues not cleared")
    require(record.get("unchecked") == [], f"{label}: required observations incomplete")


def prepare(manifest_path, review_path):
    manifest_path = Path(manifest_path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    review = json.loads(Path(review_path).read_bytes())
    require(isinstance(review, dict) and review.get("schema_version") == 1,
            "Unsupported review schema")
    require(isinstance(review.get("reviewer_id"), str) and review["reviewer_id"].strip(),
            "Independent reviewer_id is required")
    require(review.get("manifest_sha256") == sha256(manifest_bytes), "Manifest review is stale")
    technical = validate(manifest_path)
    require(technical["valid"], "Technical validation failed: " + "; ".join(technical["errors"]))
    require(manifest_path.read_bytes() == manifest_bytes, "Manifest changed during validation")
    names = [item["file"] for item in manifest["stickers"]]
    names += [manifest[key] for key in ("banner", "cover", "icon")]
    items = review.get("items")
    require(isinstance(items, list) and all(isinstance(item, dict) for item in items),
            "Review items must be objects")
    require(all(isinstance(item.get("file"), str) for item in items), "Review file path required")
    require(len(items) == len(names) and {item["file"] for item in items} == set(names),
            "Review must cover every delivery asset exactly once")
    records = {item["file"]: item for item in items}
    animated_names = {item["file"] for item in manifest["stickers"]} if manifest["mode"] == "animated" else set()
    snapshot = {"manifest.json": manifest_bytes}
    for name in names:
        archive_path = PurePosixPath(name)
        require(not archive_path.is_absolute() and ".." not in archive_path.parts
                and "\\" not in name and archive_path.as_posix() == name
                and name != "manifest.json", f"{name}: non-canonical archive path")
        item = records[name]
        passing(item, name)
        require(item.get("stage") == "final", f"{name}: draft review cannot approve final delivery")
        data = (manifest_path.parent / name).read_bytes()
        require(item.get("sha256") == sha256(data), f"{name}: asset review is stale")
        scores, evidence = item.get("scores"), item.get("evidence")
        require(isinstance(scores, dict) and set(scores) == set(LIMITS), f"{name}: incomplete scores")
        for key, maximum in LIMITS.items():
            require(type(scores[key]) is int and 0 <= scores[key] <= maximum,
                    f"{name}: invalid {key} score")
            require(isinstance(evidence, dict) and isinstance(evidence.get(key), str)
                    and evidence[key].strip(), f"{name}: {key} evidence required")
        require(sum(scores.values()) > 80, f"{name}: total score must exceed 80")
        require(scores["expression"] >= 18, f"{name}: expression score must be at least 18/25")
        checks = item.get("checks")
        required = ["light", "dark"]
        if name in animated_names:
            required += ["all_frames", "playback"]
            require(isinstance(item.get("playback_evidence"), str) and item["playback_evidence"].strip(),
                    f"{name}: original-speed playback evidence required")
        for role in ("banner", "cover", "icon"):
            if name == manifest[role]:
                required.append(role + "_design")
                require(isinstance(item.get("platform_evidence"), str) and item["platform_evidence"].strip(),
                        f"{name}: WeChat {role} design evidence required")
        require(isinstance(checks, dict) and all(checks.get(key) is True for key in required),
                f"{name}: required observation missing")
        snapshot[name] = data
    batch = review.get("batch")
    passing(batch, "batch")
    require(type(batch.get("score")) is int and 80 < batch["score"] <= 100,
            "Batch score must exceed 80")
    require(isinstance(batch.get("evidence"), str) and batch["evidence"].strip(), "Batch evidence required")
    # Revalidate the exact immutable bytes that will be archived. Source files can
    # change between the initial path validation and the snapshot read.
    with tempfile.TemporaryDirectory(prefix="expression-reviewed-") as directory:
        root = Path(directory)
        for name, data in snapshot.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        technical = validate(root / "manifest.json")
    require(technical["valid"], "Snapshot technical validation failed: " + "; ".join(technical["errors"]))
    return snapshot, technical["warnings"]


def package(manifest_path, review_path, output):
    output = Path(output)
    require(output.suffix.lower() == ".zip", "Output must be a .zip file")
    files, warnings = prepare(manifest_path, review_path)
    # Archive the checked bytes, not files that may have changed after review checks.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    with output.open("xb") as handle:
        handle.write(buffer.getvalue())
    return {"valid": True, "output": str(output), "files": list(files), "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = package(args.manifest, args.review, args.output)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
