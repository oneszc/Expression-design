#!/usr/bin/env python3
"""Read-only validation of a WeChat sticker delivery against a named profile."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError


PROFILE = "wechat-user-2026-10-27"
FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".gif": "GIF"}


def validate(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    report = {"profile": PROFILE, "valid": False, "errors": [], "warnings": [], "files": []}
    errors, warnings = report["errors"], report["warnings"]
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot read manifest: {exc}")
        return report
    if not isinstance(data, dict):
        errors.append("Manifest must be a JSON object")
        return report
    if data.get("profile") != PROFILE:
        errors.append(f"Unsupported profile; expected {PROFILE}")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("A non-empty pack name is required")
    if data.get("name_status") not in ("confirmed", "provisional"):
        errors.append("name_status must be confirmed or provisional")
    elif data["name_status"] == "provisional":
        warnings.append("Pack name is provisional; user has not confirmed it")
    mode = data.get("mode")
    if mode not in ("static", "animated"):
        errors.append("mode must be static or animated")
    stickers = data.get("stickers")
    if not isinstance(stickers, list):
        errors.append("stickers must be an array")
        stickers = []
    if not 8 <= len(stickers) <= 24:
        errors.append("Expected 8 to 24 stickers")
    if type(data.get("count")) is not int or data["count"] != len(stickers):
        errors.append("count must be an integer matching the number of stickers")

    root = manifest_path.parent
    seen_paths, seen_stickers = set(), {}

    def check_image(relative, role, size, formats, limit, animated=False):
        if not isinstance(relative, str) or not relative.strip():
            errors.append(f"{role}: missing file path")
            return
        raw = Path(relative)
        path = (root / raw).resolve()
        if raw.is_absolute() or not path.is_relative_to(root):
            errors.append(f"{role}: path must remain inside delivery directory")
            return
        if path == manifest_path or path in seen_paths:
            errors.append(f"{role}: duplicate or invalid asset path {relative}")
            return
        seen_paths.add(path)
        if not path.is_file():
            errors.append(f"{role}: file not found: {relative}")
            return
        item = {"file": relative, "role": role, "bytes": path.stat().st_size}
        report["files"].append(item)
        if item["bytes"] > limit:
            errors.append(f"{relative}: exceeds {limit} bytes")
        try:
            # Verify file integrity, then reopen for complete frame decoding.
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                item.update(format=img.format, width=img.width, height=img.height,
                            frames=getattr(img, "n_frames", 1))
                if img.format not in formats:
                    errors.append(f"{relative}: format {img.format} not allowed for {role}")
                if FORMATS.get(path.suffix.lower()) != img.format:
                    errors.append(f"{relative}: extension does not match actual image format")
                if img.size != size:
                    errors.append(f"{relative}: expected {size[0]}x{size[1]}, got {img.width}x{img.height}")
                if animated and (img.format != "GIF" or item["frames"] < 2):
                    errors.append(f"{relative}: animated sticker must be a multi-frame GIF")
                if not animated and item["frames"] != 1:
                    errors.append(f"{relative}: expected a static image")
                if animated and img.info.get("loop") != 0:
                    errors.append(f"{relative}: GIF must loop indefinitely (loop=0)")
                first_frame = None
                changed = False
                transparent = False
                digest = hashlib.sha256()
                duration = 0
                for frame_index in range(item["frames"]):
                    img.seek(frame_index)
                    frame = img.convert("RGBA")
                    pixels = frame.tobytes()
                    digest.update(pixels)
                    if first_frame is None:
                        first_frame = pixels
                    elif pixels != first_frame:
                        changed = True
                    alpha_low, alpha_high = frame.getextrema()[3]
                    transparent = transparent or alpha_low < 255
                    if alpha_high == 0:
                        errors.append(f"{relative}: frame {frame_index} is fully transparent")
                    if animated:
                        frame_duration = img.info.get("duration", 0)
                        if frame_duration <= 0:
                            errors.append(f"{relative}: frame {frame_index} has no positive duration")
                        duration += frame_duration
                item["has_transparency"] = transparent
                if animated:
                    item["duration_ms"] = duration
                    if not changed:
                        errors.append(f"{relative}: no visible frame changes")
                if role.startswith("sticker"):
                    fingerprint = (img.size, item["frames"], digest.hexdigest())
                    if fingerprint in seen_stickers:
                        errors.append(f"{relative}: duplicates sticker {seen_stickers[fingerprint]}")
                    else:
                        seen_stickers[fingerprint] = relative
                if role.startswith("sticker") or role in ("cover", "icon"):
                    if not transparent:
                        warnings.append(f"{relative}: opaque background; inspect intended background and edges")
        except (OSError, ValueError, EOFError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            errors.append(f"{relative}: cannot fully decode image: {exc}")

    for index, sticker in enumerate(stickers, 1):
        if not isinstance(sticker, dict):
            errors.append(f"sticker {index}: entry must be an object")
            continue
        if not isinstance(sticker.get("meaning"), str) or not sticker["meaning"].strip():
            errors.append(f"sticker {index}: non-empty meaning is required")
        if not isinstance(sticker.get("text", ""), str):
            errors.append(f"sticker {index}: text must be a string")
        check_image(sticker.get("file"), f"sticker {index}", (240, 240),
                    {"GIF"} if mode == "animated" else {"PNG", "JPEG", "GIF"},
                    500_000, animated=mode == "animated")
    check_image(data.get("banner"), "banner", (750, 400), {"PNG", "JPEG"}, 500_000)
    check_image(data.get("cover"), "cover", (240, 240), {"PNG"}, 500_000)
    check_image(data.get("icon"), "icon", (50, 50), {"PNG"}, 100_000)
    warnings.append("Visual consistency, text, loop quality and current WeChat acceptance require human review")
    report["valid"] = not errors
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path, help="Write a JSON report to a new file")
    args = parser.parse_args()
    # Never overwrite source assets, manifests, or an earlier report.
    if args.report and (args.report.exists() or args.report.is_symlink()):
        parser.error("report path already exists; choose a new path")
    report = validate(args.manifest)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        try:
            with args.report.open("x", encoding="utf-8") as handle:
                handle.write(output + "\n")
        except OSError as exc:
            parser.error(f"cannot write report: {exc}")
    print(output)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
