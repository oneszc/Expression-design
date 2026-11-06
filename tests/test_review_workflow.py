"""Synthetic workflow evidence only; these tests are not real art reviews."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from review_records import assemble, digest, item_errors, summary, verify_assembled, write_new
from project_state import update
from preview_pack import preview
import test_package_reviewed as fixtures


class WorkflowTest(unittest.TestCase):
    setUp = fixtures.PackageReviewedTest.setUp
    image = fixtures.PackageReviewedTest.image
    hash = fixtures.PackageReviewedTest.hash
    run_package = fixtures.PackageReviewedTest.run_package
    rejected = fixtures.PackageReviewedTest.rejected
    def fragments(self):
        records = copy.deepcopy(self.record['items'])
        for item in records:
            item['reviewer_id'] = 'synthetic-reviewer'
        path = self.root / 'fragment.json'
        write_new(path, {'schema_version': 2, 'items': records})
        batch = self.root / 'batch.json'
        write_new(batch, {'reviewer_id': 'synthetic-batch', 'manifest_sha256': self.hash(self.manifest),
                          'asset_hashes': {i['file']: i['sha256'] for i in records}, 'batch': self.record['batch']})
        return path, batch

    def animated(self):
        from PIL import Image, ImageDraw
        data = json.loads(self.manifest.read_text())
        data['mode'] = 'animated'
        for index, entry in enumerate(data['stickers']):
            frames = []
            for x in (10, 40):
                image = Image.new('RGBA', (240, 240))
                ImageDraw.Draw(image).rectangle((x, 20, x + 10 + index, 50), fill='black')
                frames.append(image)
            name = f'动图{index}.gif'
            frames[0].save(self.root / name, save_all=True, append_images=frames[1:], duration=100, loop=0, disposal=2)
            entry['file'] = name
            self.record['items'][index].update(file=name, sha256=self.hash(self.root / name), scope='frames',
                decision='blocked', unchecked=['playback'], total=None)
            self.record['items'][index]['checks'].update(all_frames=True, playback=False)
        self.manifest.write_text(json.dumps(data))
        self.record['manifest_sha256'] = self.hash(self.manifest)
        self.record['batch'].update(decision='blocked', unchecked=['playback'])

    def test_schema2_pack_and_changed_derived_score_rejected(self):
        fragment, batch = self.fragments()
        report = assemble(self.manifest, [fragment], batch)
        verify_assembled(self.manifest, report)
        self.record = report
        self.run_package()
        self.output.unlink()
        self.record['items'][0]['scores']['identity'] += 1
        self.rejected()

    def test_complete_frame_review_plus_real_confirmation_record(self):
        self.animated()
        fragment, batch = self.fragments()
        original = fragment.read_bytes()
        report = assemble(self.manifest, [fragment], batch)
        self.assertEqual(report['items'][0]['decision'], 'blocked')
        self.assertIn('未完成', summary(report))
        acceptance = {'schema_version': 1, 'observer_type': 'human', 'observer': 'test-fixture-user',
                      'confirmed_at': 'synthetic-time', 'user_confirmation': 'Synthetic confirmation; not a real observation',
                      'items': [{**{k: i[k] for k in ('file', 'sha256')}, 'speed': 1, 'loops': 2,
                                 'light': True, 'dark': True, 'decision': 'pass', 'evidence': 'Synthetic playback fixture'}
                                for i in self.record['items'][:8]]}
        path = self.root / 'acceptance.json'
        write_new(path, acceptance)
        report = assemble(self.manifest, [fragment], batch, path)
        self.assertEqual(report['batch']['decision'], 'pass')
        self.assertEqual(fragment.read_bytes(), original)
        self.assertEqual(report['provenance']['fragments'][0]['record']['items'][0]['decision'], 'blocked')
        self.record = report
        self.run_package()
        self.output.unlink()
        acceptance['items'][0]['sha256'] = '0' * 64
        path.write_text(json.dumps(acceptance))
        with self.assertRaisesRegex(ValueError, 'Stale acceptance'):
            assemble(self.manifest, [fragment], batch, path)

    def test_human_confirmation_cannot_clear_dark_or_frames(self):
        self.animated()
        item = self.record['items'][0]
        item['reviewer_id'] = 'synthetic'
        item['checks']['dark'] = False
        self.assertTrue(item_errors(item, True))
        item['unchecked'] = ['dark', 'playback']
        item['scores']['craft'] = None
        self.assertEqual(item_errors(item, True), [])
        fragment, batch = self.fragments()
        report = assemble(self.manifest, [fragment], batch)
        self.assertEqual(report['items'][0]['unchecked'], ['dark', 'playback'])
        item['decision'] = 'pass'
        self.assertTrue(item_errors(item, True))

    def test_reuse_unchanged_items_and_stale_batch_rejected(self):
        fragment, batch = self.fragments()
        self.image('表情0.png', (240, 240), 40)
        with self.assertRaisesRegex(ValueError, 'Stale review'):
            assemble(self.manifest, [fragment], batch)
        record = json.loads(fragment.read_text())
        record['items'][0]['sha256'] = self.hash(self.root / '表情0.png')
        fragment.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'Batch asset set is stale'):
            assemble(self.manifest, [fragment], batch)
        b = json.loads(batch.read_text())
        b['asset_hashes']['表情0.png'] = record['items'][0]['sha256']
        batch.write_text(json.dumps(b))
        self.assertEqual(assemble(self.manifest, [fragment], batch)['items'][1], record['items'][1])

    def test_preview_copies_exact_bytes_and_never_accepts(self):
        self.animated()
        folder = self.root / 'preview'
        result = preview(self.manifest, folder)
        self.assertEqual(result['status'], 'pending_acceptance')
        receipt = json.loads((folder / 'playback-pending.json').read_text())
        self.assertTrue(all(i['decision'] == 'pending' and i['loops'] == 0 for i in receipt['items']))
        self.assertEqual((folder / 'assets' / self.record['items'][0]['file']).read_bytes(),
                         (self.root / self.record['items'][0]['file']).read_bytes())
        self.assertTrue((folder / '待验收预览.zip').exists())
        with self.assertRaises(ValueError):
            preview(self.manifest, folder)

    def test_cli_schema2_preview_and_package(self):
        import subprocess
        fragment, batch = self.fragments()
        folder = Path(__file__).resolve().parents[1] / 'scripts'
        report = self.root / 'assembled.json'
        commands = [
            [sys.executable, str(folder / 'review_records.py'), str(self.manifest), '--fragments', str(fragment), '--check-only'],
            [sys.executable, str(folder / 'review_records.py'), str(self.manifest), '--fragments', str(fragment), '--batch', str(batch), '--output', str(report)],
            [sys.executable, str(folder / 'package_reviewed.py'), str(self.manifest), str(report), '--output', str(self.output)],
            [sys.executable, str(folder / 'preview_pack.py'), str(self.manifest), '--output-dir', str(self.root / 'preview')],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.output.exists())

    def test_clear_unchecked_or_original_score_cannot_silently_pass(self):
        self.animated()
        fragment, batch = self.fragments()
        report = assemble(self.manifest, [fragment], batch)
        self.record = report
        self.record['items'][0]['unchecked'] = []
        self.record['items'][0]['decision'] = 'pass'
        self.record['items'][0]['checks']['playback'] = True
        with self.assertRaises(ValueError):
            verify_assembled(self.manifest, self.record)
        report = assemble(self.manifest, [fragment], batch)
        report['provenance']['fragments'][0]['record']['items'][0]['scores']['identity'] = 25
        with self.assertRaisesRegex(ValueError, 'Original fragment changed'):
            verify_assembled(self.manifest, report)

    def test_preview_snapshot_validation_catches_swapped_file(self):
        from unittest.mock import patch
        import preview_pack
        validate = preview_pack.validate
        def swap(path):
            result = validate(path)
            if Path(path).resolve() == self.manifest.resolve():
                (self.root / 'icon.png').write_bytes(b'not-an-image')
            return result
        with patch.object(preview_pack, 'validate', side_effect=swap):
            with self.assertRaisesRegex(ValueError, 'Snapshot validation'):
                preview(self.manifest, self.root / 'preview')
        self.assertFalse((self.root / 'preview').exists())

    def test_draft_checks_but_cannot_package_as_final(self):
        fragment, batch = self.fragments()
        raw = json.loads(fragment.read_text())
        raw['items'][0]['stage'] = 'draft'
        fragment.write_text(json.dumps(raw))
        report = assemble(self.manifest, [fragment], batch)
        self.record = report
        self.rejected()

    def test_freeze_blocks_new_candidate_and_rechecks_bytes(self):
        fragment, batch = self.fragments()
        report = assemble(self.manifest, [fragment], batch)
        final = self.root / 'final.json'
        write_new(final, report)
        state = self.root / 'state.json'
        write_new(state, {'schema_version': 1, 'phase': 'production', 'active_since': 100,
                         'elapsed_seconds': 0, 'budget_seconds': 1800, 'assets': {}, 'tasks': {}})
        for item in report['items']:
            update(state, 'candidate', asset=item['file'], file=self.root / item['file'], now=110)
        result = update(state, 'freeze', file=final, manifest=self.manifest, now=120)
        self.assertEqual(result['phase'], 'frozen')
        with self.assertRaises(ValueError):
            update(state, 'candidate', asset=report['items'][0]['file'], file=self.root / report['items'][0]['file'], now=121)
        self.image('icon.png', (50, 50), 35)
        with self.assertRaises(ValueError):
            update(state, 'freeze', file=final, manifest=self.manifest, now=122)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'state.json'
        write_new(self.path, {'schema_version': 1, 'phase': 'pilot', 'active_since': 100,
                             'elapsed_seconds': 0, 'budget_seconds': 1800, 'assets': {}, 'tasks': {}})
        self.asset = self.root / 'asset.gif'
        self.asset.write_bytes(b'candidate-v1')

    def candidate(self, at=110):
        return update(self.path, 'candidate', asset='a.gif', file=self.asset, now=at)

    def test_candidate_budget_includes_self_checks_and_can_extend_one_asset(self):
        for i in range(3):
            self.asset.write_bytes(str(i).encode())
            self.candidate()
        self.asset.write_bytes(b'fourth')
        with self.assertRaisesRegex(ValueError, 'Candidate limit'):
            self.candidate()
        update(self.path, 'pause', now=120)
        update(self.path, 'resume', asset='a.gif', authorization='Synthetic explicit continuation', now=300)
        self.candidate(at=310)
        self.assertEqual(len(json.loads(self.path.read_text())['assets']['a.gif']), 4)

    def test_partial_review_survives_interruption_and_restart(self):
        self.candidate()
        update(self.path, 'review-start', task_id='r1', names=['a.gif'], now=120)
        record = self.root / 'one.json'
        item = {'file': 'a.gif', 'sha256': digest(self.asset.read_bytes()), 'reviewer_id': 'synthetic',
                'stage': 'final', 'scope': 'frames', 'decision': 'blocked', 'unchecked': ['playback'],
                'scores': {'identity': 22, 'expression': 22, 'craft': 30, 'legibility': 14},
                'checks': {'light': True, 'dark': True, 'all_frames': True},
                'evidence': {k: 'synthetic evidence' for k in ('identity','expression','craft','legibility')},
                'critical_issues': [], 'total': None}
        write_new(record, {'schema_version': 2, 'items': [item]})
        (self.root / 'a.gif').write_bytes(self.asset.read_bytes())
        manifest = self.root / 'manifest.json'
        write_new(manifest, {'mode': 'animated', 'stickers': [{'file': 'a.gif'}],
                             'banner': 'banner.png', 'cover': 'cover.png', 'icon': 'icon.png'})
        update(self.path, 'review-progress', task_id='r1', file=record, manifest=manifest, now=130)
        current = json.loads(self.path.read_text())
        saved = current['tasks']['r1']['completed']['a.gif']
        update(self.path, 'review-stop', task_id='r1', now=140)
        self.assertTrue(Path(saved).exists())
        self.assertEqual(json.loads(Path(saved).read_text())['items'][0]['sha256'], digest(self.asset.read_bytes()))

    def test_timeout_and_total_budget_stop_new_work(self):
        self.candidate()
        update(self.path, 'review-start', task_id='r1', names=['a.gif'], now=120)
        stalled = update(self.path, 'status', now=241)
        self.assertIn('r1:no_progress_check_host', stalled['stop_reasons'])
        timed = update(self.path, 'status', now=421)
        self.assertIn('r1:review_timeout', timed['stop_reasons'])
        with self.assertRaises(ValueError):
            self.candidate(at=2000)
        update(self.path, 'pause', now=2000)
        self.assertEqual(update(self.path, 'status', now=9000)['elapsed_seconds'], 1900)

    def test_more_than_three_items_rejected(self):
        self.candidate()
        with self.assertRaises(ValueError):
            update(self.path, 'review-start', task_id='r1', names=['a','b','c','d'], now=120)


if __name__ == '__main__':
    unittest.main()
