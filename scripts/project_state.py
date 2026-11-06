#!/usr/bin/env python3
"""Single-writer checkpoint ledger. Does not run or cancel host Agents."""
import argparse
import json
import os
import sys
import time
import tempfile
from pathlib import Path

from review_records import check_fragments, digest, read, require, write_new


def save(path, state):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def elapsed(state, now):
    return state['elapsed_seconds'] + (max(0, now - state['active_since']) if state['active_since'] is not None else 0)


def status(state, now=None):
    now = time.time() if now is None else now
    reasons = []
    if elapsed(state, now) >= state['budget_seconds']:
        reasons.append('project_budget_exhausted')
    for task_id, task in state['tasks'].items():
        if task['status'] == 'running':
            if now - task['started_at'] >= 300:
                reasons.append(f'{task_id}:review_timeout')
            elif now - task['last_progress_at'] >= 120:
                reasons.append(f'{task_id}:no_progress_check_host')
    return {'elapsed_seconds': round(elapsed(state, now)), 'stop_reasons': reasons,
            'phase': state['phase'], 'assets': state['assets'], 'tasks': state['tasks']}


def update(path, action, *, asset=None, file=None, task_id=None, names=None, authorization=None, manifest=None, now=None):
    path = Path(path)
    state = read(path)
    now = time.time() if now is None else now
    if action == 'status':
        return status(state, now)
    require(action in ('candidate', 'review-start', 'review-progress', 'review-stop', 'pause', 'resume', 'freeze'), 'Unknown state action')
    if action in ('candidate', 'review-start'):
        require(state['active_since'] is not None and state['phase'] != 'frozen', 'Project paused/frozen')
        require(not status(state, now)['stop_reasons'], 'Budget/progress limit reached; inspect and checkpoint before continuing')
    if action == 'candidate':
        require(bool(asset) and bool(file), 'asset and file required')
        sha = digest(Path(file).read_bytes())
        versions = state['assets'].setdefault(asset, [])
        if not versions or versions[-1]['sha256'] != sha:
            require(len(versions) < state.get('candidate_limits', {}).get(asset, 3), 'Candidate limit reached (including self-check revisions); pause and request explicit continuation')
            versions.append({'sha256': sha, 'file': str(Path(file).resolve()), 'recorded_at': now})
    elif action == 'review-start':
        require(bool(task_id) and task_id not in state['tasks'], 'New task_id required')
        require(names and 1 <= len(names) <= 3 and len(set(names)) == len(names), 'Review task must contain 1..3 distinct assets')
        require(all(name in state['assets'] for name in names), 'Record candidates before review')
        state['tasks'][task_id] = {'status': 'running', 'started_at': now, 'last_progress_at': now,
                                  'assets': {name: state['assets'][name][-1]['sha256'] for name in names}, 'completed': {}}
    elif action == 'review-progress':
        task = state['tasks'][task_id]
        require(task['status'] == 'running', 'Review task is not running')
        require(manifest is not None, '--manifest required to validate checkpoint')
        check_fragments(manifest, [file])
        fragment = read(file)
        require(fragment.get('schema_version') == 2 and fragment.get('items'), 'Schema 2 review fragment required')
        # Preserve complete original per-item records immediately, even before full assembly.
        for item in fragment['items']:
            name = item['file']
            require(name in task['assets'] and item.get('sha256') == task['assets'][name], 'Review does not match assigned candidate')
            require(name not in task['completed'], 'Item already checkpointed')
        target = path.parent / 'reviews' / task_id / f"part-{len(task['completed']) + 1}.json"
        if target.exists():
            require(read(target) == fragment, 'Checkpoint path already contains a different record')
        else:
            write_new(target, fragment)
        for item in fragment['items']:
            task['completed'][item['file']] = str(target.resolve())
        task['last_progress_at'] = now
        if set(task['completed']) == set(task['assets']):
            task['status'] = 'complete'
    elif action == 'review-stop':
        state['tasks'][task_id]['status'] = 'interrupted'
    elif action == 'pause':
        state['elapsed_seconds'] = elapsed(state, now)
        state['active_since'] = None
        state['phase'] = 'paused'
    elif action == 'resume':
        require(isinstance(authorization, str) and authorization.strip(), 'Record actual user continuation instruction')
        require(state['active_since'] is None, 'Pause before extending budget')
        state.setdefault('extensions', []).append({'authorization': authorization, 'at': now})
        state['budget_seconds'] = state['elapsed_seconds'] + 1800
        state['active_since'] = now
        state['phase'] = 'production'
        if asset:
            require(asset in state['assets'], 'Unknown asset for extension')
            state.setdefault('candidate_limits', {})[asset] = len(state['assets'][asset]) + 2
        # Never reset counts or open other assets' budgets implicitly.
    elif action == 'freeze':
        require(file is not None, 'Passing report required')
        require(manifest is not None, '--manifest required to freeze current delivery')
        from package_reviewed import prepare
        prepare(manifest, file)
        report = read(file)
        require(report.get('schema_version') == 2, 'Assembled schema 2 report required')
        require(report.get('batch', {}).get('decision') == 'pass' and report.get('items')
                and all(i.get('decision') == 'pass' and i.get('unchecked') == [] for i in report['items']), 'Report not ready')
        for item in report['items']:
            name = item['file']
            require(name in state['assets'], 'All assets must have recorded candidates')
            version = state['assets'][name][-1]
            require(item['sha256'] == version['sha256'] == digest(Path(version['file']).read_bytes()), 'Freeze contains stale asset')
        state['frozen_report'] = {'file': str(Path(file).resolve()), 'sha256': digest(Path(file).read_bytes())}
        state['elapsed_seconds'] = elapsed(state, now)
        state['active_since'] = None
        state['phase'] = 'frozen'
    save(path, state)
    return status(state, now)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state', type=Path)
    parser.add_argument('action', choices=['init', 'status', 'candidate', 'review-start', 'review-progress', 'review-stop', 'pause', 'resume', 'freeze'])
    parser.add_argument('--asset')
    parser.add_argument('--file', type=Path)
    parser.add_argument('--task-id')
    parser.add_argument('--names', nargs='+')
    parser.add_argument('--authorization')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--budget-minutes', type=int, default=30)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            require(args.budget_minutes > 0, 'Budget must be positive')
            write_new(args.state, {'schema_version': 1, 'phase': 'pilot', 'active_since': time.time(),
                                  'elapsed_seconds': 0, 'budget_seconds': args.budget_minutes * 60, 'assets': {}, 'tasks': {}})
            result = {'state': str(args.state)}
        else:
            result = update(args.state, args.action, asset=args.asset, file=args.file,
                            task_id=args.task_id, names=args.names, authorization=args.authorization, manifest=args.manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('stop_reasons') else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
