#!/usr/bin/env python3
"""Inspect project space and prune only verified, tool-owned, reproducible artifacts."""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from review_records import digest, read, require, write_new

MARKER = '.expression-artifact.json'
PROCESS_DIRS = ('build', 'previews', '.expression-cache')
DEFAULT_BUDGET = 100 * 1024 * 1024


def project_for(manifest):
    parent = Path(manifest).resolve().parent
    return parent.parent if parent.name == 'delivery' else parent


def walk_files(root):
    """Never follow links into user folders or another project."""
    if root.is_symlink() or not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_symlink():
            continue
        if child.is_dir():
            yield from walk_files(child)
        elif child.is_file():
            yield child


def budget_for(project):
    policy = Path(project) / '.expression-storage-policy.json'
    if not policy.exists():
        return DEFAULT_BUDGET
    value = read(policy)
    require(value.get('schema_version') == 1 and type(value.get('budget_bytes')) is int
            and value['budget_bytes'] > 0 and isinstance(value.get('user_authorization'), str)
            and value['user_authorization'].strip(), 'Storage policy requires a positive budget and actual user authorization')
    return value['budget_bytes']


def inventory(project):
    project = Path(project).resolve()
    totals, logical, physical, seen = {}, 0, 0, set()
    for path in walk_files(project):
        if '.git' in path.relative_to(project).parts:
            continue
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino)
        category = path.relative_to(project).parts[0]
        logical += stat.st_size
        totals.setdefault(category, 0)
        if key not in seen:
            totals[category] += stat.st_size
            physical += stat.st_size
            seen.add(key)
    # Count each inode once inside process roots too, independent of directory traversal order.
    process_seen, process_bytes = set(), 0
    for name in PROCESS_DIRS:
        for path in walk_files(project / name):
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
            if key not in process_seen:
                process_seen.add(key)
                process_bytes += stat.st_size
    return {'project': str(project), 'logical_bytes': logical, 'unique_file_bytes': physical,
            'process_bytes': process_bytes, 'categories_unique_bytes': totals,
            'budget_bytes': budget_for(project), 'budget_exceeded': process_bytes >= budget_for(project)}


def ensure_budget(project, additional=0, budget=None):
    budget = budget_for(project) if budget is None else budget
    current = inventory(project)['process_bytes']
    require(current + additional <= budget,
            f'Process storage budget exceeded: {current} + {additional} > {budget} bytes. '
            'Stop generating; inspect and prune verified old artifacts, or obtain an explicit larger budget.')


def owned_path(project, path):
    project = Path(project).resolve()
    raw = Path(path).absolute()
    require('..' not in raw.parts, 'Non-canonical artifact path')
    path = raw.resolve()
    require(path.is_relative_to(project), 'Artifact must be inside project')
    relative = path.relative_to(project)
    require(len(relative.parts) >= 2 and relative.parts[0] in PROCESS_DIRS, 'Only a process leaf directory may be managed')
    current = raw
    while current.resolve() != project:
        require(not current.is_symlink(), 'Symlinked artifact paths are not managed')
        current = current.parent
    return path


def seal(project, folder, kind, asset, key, inputs=()):
    folder = owned_path(project, folder)
    require(not any(p.is_symlink() for p in folder.rglob('*')), 'Cannot register symlinked contents')
    files = {p.relative_to(folder).as_posix(): digest(p.read_bytes()) for p in walk_files(folder) if p.name != MARKER}
    require(files, 'Artifact files required')
    require(not any(p.name == MARKER for p in folder.rglob('*')), 'Nested/already registered artifacts are not allowed')
    require(not any((parent / MARKER).exists() for parent in folder.parents if parent != Path(project).resolve()),
            'Artifact cannot be nested inside another artifact')
    write_new(folder / MARKER, {'schema_version': 1, 'owner': 'expression-design', 'kind': kind,
                'asset': asset, 'key': key, 'created_ns': time.time_ns(), 'files': files,
                'inputs': [str(Path(p).resolve()) for p in inputs]})


def verified(folder):
    folder = Path(folder)
    require(not folder.is_symlink(), 'Symlinked artifact')
    record = read(folder / MARKER)
    require(record.get('schema_version') == 1 and record.get('owner') == 'expression-design', 'Unowned artifact')
    require(not any(p.is_symlink() for p in folder.rglob('*')), 'Artifact contains symlink')
    actual = {p.relative_to(folder).as_posix(): digest(p.read_bytes()) for p in walk_files(folder) if p.name != MARKER}
    require(actual == record.get('files'), f'Artifact changed; preserve it: {folder}')
    return record


def managed(project):
    result = {}
    for name in PROCESS_DIRS:
        for path in walk_files(Path(project) / name):
            if path.name == MARKER:
                folder = owned_path(project, path.parent)
                try:
                    result[folder] = verified(folder)
                except (OSError, ValueError, TypeError, KeyError):
                    # Modified or incomplete directories stay untouched and visible in inventory.
                    pass
    return result


def find(project, kind, asset, key):
    for name in PROCESS_DIRS:
        for marker in walk_files(Path(project) / name):
            if marker.name != MARKER:
                continue
            record = read(marker)
            if (record.get('kind'), record.get('asset'), record.get('key')) == (kind, asset, key):
                folder = owned_path(project, marker.parent)
                verified(folder)
                return folder
    return None


def review_hashes(project):
    hashes = set()
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('sha256'), str):
                hashes.add(value['sha256'])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for path in walk_files(Path(project) / 'reviews'):
        if path.suffix == '.json':
            try:
                visit(read(path))
            except (ValueError, OSError):
                raise ValueError(f'Unreadable review evidence; refuse pruning: {path}')
    return hashes


def plan(project, keep=2):
    require(type(keep) is int and keep >= 2, 'Keep at least current and previous version')
    project = Path(project).resolve()
    records = managed(project)
    groups, protected = {}, set()
    evidence = review_hashes(project)
    for folder, record in records.items():
        if record['kind'] != 'preview-cache':
            groups.setdefault((record['kind'], record['asset']), []).append(folder)
        # Preserve reviewed image bytes in per-asset builds/cache, not every whole-pack HTML copy.
        if record['kind'] != 'preview' and evidence.intersection(record['files'].values()):
            protected.add(folder)
    for folders in groups.values():
        protected.update(sorted(folders, key=lambda p: records[p]['created_ns'], reverse=True)[:keep])
    # Source/dependency references from every retained artifact are transitive roots.
    changed = True
    while changed:
        changed = False
        for folder in list(protected):
            for dependency in records[folder].get('inputs', []):
                dep = Path(dependency)
                for candidate in records:
                    if dep == candidate or dep.is_relative_to(candidate):
                        if candidate not in protected:
                            protected.add(candidate)
                            changed = True
    return {'project': str(project), 'delete': [str(p.relative_to(project)) for p in records if p not in protected],
            'preserve': [str(p.relative_to(project)) for p in protected], 'inventory': inventory(project)}


def prune(project, keep=2, apply=False):
    result = plan(project, keep)
    project = Path(project).resolve()
    if apply:
        # Re-plan immediately; never consume a previously saved deletion list.
        for name in result['delete']:
            folder = owned_path(project, project / name)
            verified(folder)
            shutil.rmtree(folder)
        result['after'] = inventory(project)
    return result


def build_key(recipe, inputs):
    paths = [Path(recipe).resolve()] + [Path(p).resolve() for p in inputs]
    require(all(p.is_file() for p in paths), 'Recipe and all reproducible inputs must be existing files')
    return digest(json.dumps([(str(p), digest(p.read_bytes())) for p in paths], sort_keys=True).encode())


def register_build(project, folder, asset, recipe, inputs):
    require(asset and recipe and inputs, 'Stable asset, recipe and complete input files required')
    folder = owned_path(project, folder)
    paths = [Path(recipe).resolve()] + [Path(p).resolve() for p in inputs]
    require(all(not p.is_relative_to(folder) for p in paths), 'Rebuild recipe/inputs must live outside disposable output')
    key = build_key(recipe, inputs)
    previous = find(project, 'build', asset, key)
    require(previous is None, f'Build already exists; reuse it instead of registering another copy: {previous}')
    seal(project, folder, 'build', asset, key, paths)
    return {'path': str(folder), 'key': key}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('action', choices=['inspect', 'prune', 'lookup', 'register-build'])
    parser.add_argument('--keep', type=int, default=2)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--asset')
    parser.add_argument('--recipe', type=Path)
    parser.add_argument('--inputs', type=Path, nargs='+')
    parser.add_argument('--path', type=Path)
    parser.add_argument('--rebuildable', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'inspect':
            result = inventory(args.project)
        elif args.action == 'prune':
            result = prune(args.project, args.keep, args.apply)
        elif args.action == 'lookup':
            require(args.asset and args.recipe and args.inputs, 'asset, recipe and inputs required')
            key = build_key(args.recipe, args.inputs)
            existing = find(args.project, 'build', args.asset, key)
            if existing is None:
                ensure_budget(args.project)
            result = {'key': key, 'reused': existing is not None, 'path': str(existing) if existing else None}
        else:
            require(args.rebuildable and args.path is not None, 'Explicit --rebuildable and --path required')
            result = register_build(args.project, args.path, args.asset, args.recipe, args.inputs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
