#!/usr/bin/env python3
"""Create an immutable local playback preview; never create an acceptance automatically."""
import argparse
import io
import json
import sys
import tempfile
import zipfile
from html import escape
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from review_records import assets, asset_path, digest, write_new
from validate_pack import validate
from export_animation import contact_sheet


def preview(manifest_path, output):
    manifest_path, output = Path(manifest_path), Path(output)
    technical = validate(manifest_path)
    if not technical['valid']:
        raise ValueError('; '.join(technical['errors']))
    if output.exists():
        raise ValueError('Preview output must be a new directory')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    payloads = {name: asset_path(manifest_path, name).read_bytes() for name in assets(manifest)}
    # Validate precisely the copied bytes, including files swapped during initial probing.
    with tempfile.TemporaryDirectory(prefix='expression-preview-') as temporary:
        snapshot = Path(temporary)
        (snapshot / 'manifest.json').write_bytes(manifest_bytes)
        for name, data in payloads.items():
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        technical = validate(snapshot / 'manifest.json')
        if not technical['valid']:
            raise ValueError('Snapshot validation failed: ' + '; '.join(technical['errors']))
    entries, sections = [], []
    for name, data in payloads.items():
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
        label = escape(name)
        src = 'assets/' + quote(name, safe='/')
        pictures = ''.join(f'<figure class="{theme}"><figcaption>{caption}</figcaption>'
                           f'<img src="{src}" width="{width}" height="{height}" alt="{label}"></figure>'
                           for theme, caption in [('light', '浅色聊天底'), ('dark', '深色聊天底')])
        # Disclosures reduce visual clutter; browser GIF timing is not observation evidence.
        sections.append(f'<section><h2>{label}</h2><details><summary>展开原速预览</summary><div class="pair">{pictures}</div></details></section>')
        if manifest['mode'] == 'animated' and name in {i['file'] for i in manifest['stickers']}:
            entries.append({'file': name, 'sha256': digest(data), 'speed': 1, 'loops': 0,
                            'light': False, 'dark': False, 'decision': 'pending', 'evidence': ''})
    html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>待播放验收</title><style>*{box-sizing:border-box}body{font:16px/1.6 system-ui;margin:24px;background:#eee;color:#171717}main{max-width:1000px;margin:auto}summary{cursor:pointer;padding:12px}summary:focus-visible{outline:3px solid #2765ca}.pair{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;padding:16px;max-width:100%;overflow:auto}.light{background:#fff;color:#171717;color-scheme:only light}.dark{background:#202020;color:#fff;color-scheme:only dark}img{display:block;object-fit:contain}section{padding:12px 0;border-bottom:1px solid #bbb}</style><main><h1>待播放验收</h1><p>这是待验收预览，不表示整套合格。逐张展开，每张在浅、深底原速观察至少两轮，检查节奏、循环、闪烁和动作是否自然。发现问题请告知具体文件；全部看完后明确回复验收范围与结果。页面不会自动记录通过。</p>'''+''.join(sections)+'</main></html>'
    output.mkdir(parents=True)
    for name, data in payloads.items():
        target = output / 'assets' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name, data in payloads.items():
        frames, durations = [], []
        with Image.open(io.BytesIO(data)) as image:
            for index in range(getattr(image, 'n_frames', 1)):
                image.seek(index)
                frames.append(image.convert('RGBA').copy())
                durations.append(image.info.get('duration', 0))
        # All frames come from final bytes, never the unencoded source sequence.
        folder = output / '_frames' / digest(data)
        folder.mkdir(parents=True, exist_ok=True)
        if frames[0].size == (240, 240):
            for theme, background in [('light', '#ffffff'), ('dark', '#202020')]:
                contact_sheet(frames, durations, background).save(folder / f'decoded-{theme}.png')
        else:
            for theme, background in [('light', '#ffffff'), ('dark', '#202020')]:
                tile = Image.new('RGBA', frames[0].size, background)
                tile.alpha_composite(frames[0])
                tile.convert('RGB').save(folder / f'decoded-{theme}.png')
    (output / 'index.html').write_text(html, encoding='utf-8')
    write_new(output / 'playback-pending.json', {'schema_version': 1, 'observer_type': 'human',
                'observer': '', 'confirmed_at': '', 'user_confirmation': '', 'items': entries})
    write_new(output / 'status.json', {'status': 'pending_acceptance', 'manifest_sha256': digest(manifest_bytes),
                'asset_hashes': {n: digest(b) for n,b in payloads.items()}, 'technical': technical})
    # Only an explicitly labelled pending preview bundle; no approved delivery shortcut.
    with zipfile.ZipFile(output / '待验收预览.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.relative_to(output).as_posix())
    return {'preview': str(output / 'index.html'), 'status': 'pending_acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(preview(args.manifest, args.output_dir), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
