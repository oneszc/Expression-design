#!/usr/bin/env python3
"""Export timed frames to a shared-palette GIF without changing the timeline."""

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat


SIZE = (240, 240)
LIMIT = 500_000


def rectangle(value, size, label):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(v) is not int for v in value)):
        raise ValueError(f"{label}: expected [x, y, width, height] integers")
    x, y, width, height = value
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > size[0] or y + height > size[1]:
        raise ValueError(f"{label}: rectangle is outside the image")
    return x, y, x + width, y + height


def load_sequence(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("stage") not in ("draft", "final"):
        raise ValueError("stage must be draft or final")
    entries = data.get("frames")
    if not isinstance(entries, list) or not 2 <= len(entries) <= 240:
        raise ValueError("frames must contain 2 to 240 timed entries")
    frames, durations = [], []
    source_size = None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError(f"frame {index}: missing file")
        raw = Path(entry["file"])
        source = (path.parent / raw).resolve()
        if raw.is_absolute() or not source.is_relative_to(path.parent):
            raise ValueError(f"frame {index}: file must stay inside sequence directory")
        duration = entry.get("duration_ms")
        if type(duration) is not int or not 10 <= duration <= 655_350 or duration % 10:
            raise ValueError(f"frame {index}: duration_ms must be 10..655350 in multiples of 10")
        with Image.open(source) as original:
            if getattr(original, "n_frames", 1) != 1:
                raise ValueError(f"frame {index}: use still frames, not an animated input")
            frame = original.convert("RGBA")
        if "crop" in entry:
            frame = frame.crop(rectangle(entry["crop"], frame.size, f"frame {index} crop"))
        if source_size is None:
            source_size = frame.size
        elif frame.size != source_size:
            raise ValueError("all source frames must share a canvas size; do not fit each subject separately")
        # One fixed scale and centered canvas for all frames, never per-frame bbox fitting.
        scale = min(SIZE[0] / source_size[0], SIZE[1] / source_size[1])
        fitted = frame.resize((max(1, round(source_size[0] * scale)),
                               max(1, round(source_size[1] * scale))), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", SIZE)
        canvas.paste(fitted, ((SIZE[0] - fitted.width) // 2, (SIZE[1] - fitted.height) // 2))
        if canvas.getextrema()[3][1] == 0:
            raise ValueError(f"frame {index}: fully transparent")
        frames.append(canvas)
        durations.append(duration)
    if len({frame.tobytes() for frame in frames}) < 2:
        raise ValueError("sequence has no visible changes")
    return data, frames, durations


def stability_checks(frames, regions):
    if not isinstance(regions, list):
        raise ValueError("stable_regions must be an array")
    results = []
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            raise ValueError("stable region must be an object")
        box = rectangle(region.get("rect"), SIZE, f"stable region {index}")
        threshold = region.get("threshold", 0.03)
        if type(threshold) not in (int, float) or not 0 <= threshold <= 1:
            raise ValueError("stable region threshold must be between 0 and 1")
        # Compare visible pixels on both backgrounds; hidden RGB must not trigger drift.
        values = [0.0] * len(frames)
        for background in ("white", "#242424"):
            visible = []
            for frame in frames:
                tile = Image.new("RGBA", SIZE, background)
                tile.alpha_composite(frame)
                visible.append(tile.convert("RGB").crop(box))
            base = visible[0]
            for i, frame in enumerate(visible):
                value = sum(ImageStat.Stat(ImageChops.difference(base, frame)).mean) / (3 * 255)
                values[i] = max(values[i], value)
        results.append({"name": region.get("name", f"region-{index}"),
                        "rect": region["rect"], "threshold": threshold,
                        "max_difference": round(max(values), 6),
                        "flagged_frames": [i for i, value in enumerate(values) if value > threshold]})
    return results


def encode(frames, durations, colors, alpha_threshold):
    # Build one palette across all frames; index 255 is reserved for transparency.
    rgb = []
    masks = []
    for frame in frames:
        mask = frame.getchannel("A").point(lambda a: 255 if a < alpha_threshold else 0)
        opaque = frame.convert("RGB")
        opaque.paste((0, 0, 0), mask=mask)
        rgb.append(opaque)
        masks.append(mask)
    board = Image.new("RGB", (SIZE[0], SIZE[1] * len(rgb)))
    for index, frame in enumerate(rgb):
        board.paste(frame, (0, index * SIZE[1]))
    palette = board.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                             dither=Image.Dither.NONE)
    indexed, times = [], []
    for frame, mask, duration in zip(rgb, masks, durations):
        output = frame.quantize(palette=palette, dither=Image.Dither.NONE)
        output.paste(255, mask=mask)
        output.info["transparency"] = 255
        if indexed and output.tobytes() == indexed[-1].tobytes() and times[-1] + duration <= 655_350:
            times[-1] += duration
        else:
            indexed.append(output)
            times.append(duration)
    if len(indexed) < 2:
        return None
    stream = io.BytesIO()
    indexed[0].save(stream, format="GIF", save_all=True, append_images=indexed[1:],
                    duration=times, loop=0, transparency=255, disposal=2, optimize=False)
    return stream.getvalue()


def contact_sheet(frames, durations, background):
    columns = 4
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 240, rows * 264), background)
    draw = ImageDraw.Draw(sheet)
    for index, (frame, duration) in enumerate(zip(frames, durations)):
        x, y = (index % columns) * 240, (index // columns) * 264
        tile = Image.new("RGBA", SIZE, background)
        tile.alpha_composite(frame)
        sheet.paste(tile.convert("RGB"), (x, y))
        draw.text((x + 5, y + 244), f"{index}: {duration}ms", fill="#888888")
    return sheet


def export(sequence_path, output_dir, alpha_threshold=128):
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory already exists; choose a new directory")
    if type(alpha_threshold) is not int or not 1 <= alpha_threshold <= 255:
        raise ValueError("alpha threshold must be 1..255")
    data, frames, durations = load_sequence(sequence_path)
    regions = stability_checks(frames, data.get("stable_regions", []))
    attempts = []
    payload = None
    for colors in (255, 192, 128, 96):
        candidate = encode(frames, durations, colors, alpha_threshold)
        if candidate is None:
            raise ValueError("animation collapsed after palette/alpha conversion; revise source frames")
        payload = candidate
        attempts.append({"colors": colors, "bytes": len(payload)})
        if len(payload) <= LIMIT:
            break
    # Fully decode exported frames; verify the exact total timeline survives encoding.
    with Image.open(io.BytesIO(payload)) as gif:
        encoded_durations = []
        fingerprints = set()
        for index in range(gif.n_frames):
            gif.seek(index)
            encoded_durations.append(gif.info.get("duration", 0))
            fingerprints.add(gif.convert("RGBA").tobytes())
        if sum(encoded_durations) != sum(durations) or len(fingerprints) < 2:
            raise ValueError("encoded GIF lost timing or visible animation")
        encoded_frames = gif.n_frames
    warnings = ["Visual review required: identity, timing, loop join and transparent edges"]
    if not regions:
        warnings.append("No fixed regions supplied; no automatic frame stability judgment was made")
    if any(region["flagged_frames"] for region in regions):
        warnings.append("Fixed regions changed; review flagged frames before final delivery")
    size_passed = len(payload) <= LIMIT
    if not size_passed:
        warnings.append("Still exceeds 500000 bytes; timeline preserved. Revise source or approve a timing change")
    report = {"stage": data["stage"], "size_passed": size_passed,
              "visual_review_required": True, "size": list(SIZE), "bytes": len(payload),
              "input_entries": len(frames), "encoded_frames": encoded_frames,
              "duration_ms": sum(durations), "encoded_durations_ms": encoded_durations,
              "palette_attempts": attempts, "alpha_threshold": alpha_threshold,
              "stable_regions": regions, "warnings": warnings}
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "animation.gif").write_bytes(payload)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    contact_sheet(frames, durations, "#ffffff").save(output_dir / "contact-light.png")
    contact_sheet(frames, durations, "#242424").save(output_dir / "contact-dark.png")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sequence", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--alpha-threshold", type=int, default=128)
    args = parser.parse_args()
    try:
        report = export(args.sequence, args.output_dir, args.alpha_threshold)
    except (OSError, ValueError, KeyError, TypeError, EOFError, Image.DecompressionBombError) as exc:
        parser.exit(1, f"Export failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["size_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
