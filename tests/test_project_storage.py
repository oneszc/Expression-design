"""Storage regressions use synthetic assets, not generated user cases."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import project_storage as storage
import preview_pack
import export_animation
from review_records import write_new
import test_package_reviewed as fixtures


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def artifact(self, version, *, inputs=(), asset='收到', kind='build'):
        folder = self.root / 'build' / asset / str(version)
        folder.mkdir(parents=True)
        (folder / 'animation.gif').write_bytes(f'synthetic version {version}'.encode())
        storage.seal(self.root, folder, kind, asset, str(version), inputs)
        return folder

    def test_cleanup_keeps_two_and_preserves_unmanaged_and_sources(self):
        old, previous, current = [self.artifact(i) for i in range(3)]
        for name in ('sources/reference.png', 'delivery/收到.gif', 'build/unmanaged/source.png', 'reviews/evidence.md'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'user original')
        planned = storage.prune(self.root)
        self.assertEqual(planned['delete'], [str(old.relative_to(self.root))])
        self.assertTrue(old.exists())
        storage.prune(self.root, apply=True)
        self.assertFalse(old.exists())
        self.assertTrue(previous.exists() and current.exists())
        self.assertEqual((self.root / 'sources/reference.png').read_bytes(), b'user original')
        self.assertTrue((self.root / 'build/unmanaged/source.png').exists())

    def test_changed_and_reviewed_old_builds_are_protected(self):
        changed, reviewed = self.artifact(0), self.artifact(1)
        self.artifact(2)
        self.artifact(3)
        (changed / 'notes.md').write_text('User added this')
        write_new(self.root / 'reviews/old.json', {'sha256': storage.digest((reviewed / 'animation.gif').read_bytes())})
        storage.prune(self.root, apply=True)
        self.assertTrue(changed.exists() and reviewed.exists())

    def test_dependency_and_symlink_cannot_be_pruned(self):
        source = self.artifact(0)
        self.artifact(1)
        self.artifact(2, inputs=[source / 'animation.gif'])
        outside = self.root / 'sources'
        outside.mkdir()
        (self.root / 'build/link').symlink_to(outside, target_is_directory=True)
        storage.prune(self.root, apply=True)
        self.assertTrue(source.exists())
        with self.assertRaises(ValueError):
            storage.owned_path(self.root, self.root / 'build/link/deeper')
        with self.assertRaises(ValueError):
            storage.owned_path(self.root, self.root / 'build/../sources')

    def test_inventory_counts_hardlinks_once(self):
        folder = self.root / 'previews/a'
        folder.mkdir(parents=True)
        original = folder / 'image.png'
        original.write_bytes(b'x' * 10000)
        os.link(original, folder / 'other.png')
        usage = storage.inventory(self.root)
        self.assertEqual(usage['logical_bytes'], 20000)
        self.assertEqual(usage['process_bytes'], 10000)
        self.assertEqual(usage['unique_file_bytes'], 10000)
        with self.assertRaises(ValueError):
            storage.ensure_budget(self.root, additional=1, budget=10000)

    def test_unreferenced_cache_is_removed_but_active_cache_retained(self):
        active = self.artifact(0, asset='cache0', kind='preview-cache')
        orphan = self.artifact(1, asset='cache1', kind='preview-cache')
        self.artifact(2, asset='pack', kind='preview', inputs=[active])
        storage.prune(self.root, apply=True)
        self.assertTrue(active.exists())
        self.assertFalse(orphan.exists())

    def test_custom_budget_requires_recorded_user_authorization(self):
        policy = self.root / '.expression-storage-policy.json'
        write_new(policy, {'schema_version': 1, 'budget_bytes': 2000, 'user_authorization': 'Synthetic explicit budget choice'})
        self.assertEqual(storage.inventory(self.root)['budget_bytes'], 2000)
        policy.write_text('{"schema_version":1,"budget_bytes":2000}')
        with self.assertRaises(ValueError):
            storage.inventory(self.root)

    def test_external_builder_lookup_uses_recipe_and_input_bytes(self):
        recipe = self.root / 'sources/render.py'
        recipe.parent.mkdir()
        recipe.write_text('# deterministic test renderer')
        params = self.root / 'sources/收到.json'
        params.write_text('{"pose":1}')
        output = self.root / 'build/收到/v1'
        output.mkdir(parents=True)
        (output / 'frame.png').write_bytes(b'synthetic')
        result = storage.register_build(self.root, output, '收到', recipe, [params])
        self.assertEqual(storage.find(self.root, 'build', '收到', result['key']), output)
        params.write_text('{"pose":2}')
        self.assertIsNone(storage.find(self.root, 'build', '收到', storage.build_key(recipe, [params])))
        with self.assertRaises(ValueError):
            storage.register_build(self.root, output, '收到', output / 'frame.png', [params])

    def test_export_same_input_reuses_without_new_directory(self):
        from PIL import Image, ImageDraw
        source = self.root / 'sources'
        source.mkdir()
        frames = []
        for i in range(2):
            image = Image.new('RGBA', (240, 240))
            ImageDraw.Draw(image).rectangle((20 + i*20, 20, 50 + i*20, 50), fill='black')
            image.save(source / f'{i}.png')
            frames.append({'file': f'{i}.png', 'duration_ms': 100})
        sequence = source / 'sequence.json'
        write_new(sequence, {'stage': 'final', 'frames': frames})
        first = export_animation.export(sequence, self.root / 'build/收到/v1', project=self.root, asset='收到')
        before = storage.inventory(self.root)['process_bytes']
        with patch.object(export_animation, 'encode', side_effect=AssertionError('should not encode twice')):
            second = export_animation.export(sequence, self.root / 'build/收到/v2', project=self.root, asset='收到')
        self.assertTrue(second['reused'])
        self.assertEqual(first['output_dir'], second['output_dir'])
        self.assertEqual(storage.inventory(self.root)['process_bytes'], before)
        self.assertFalse((self.root / 'build/收到/v2').exists())

    def test_many_versions_stay_at_two_after_pruning(self):
        peak = 0
        for version in range(12):
            folder = self.root / 'build/收到' / str(version)
            folder.mkdir(parents=True)
            (folder / 'process.bin').write_bytes(bytes([version]) * 1024 * 1024)
            storage.seal(self.root, folder, 'build', '收到', str(version))
            peak = max(peak, storage.inventory(self.root)['process_bytes'])
            storage.prune(self.root, apply=True)
        self.assertEqual(len(list((self.root / 'build/收到').iterdir())), 2)
        self.assertLess(storage.inventory(self.root)['process_bytes'], 2 * 1024 * 1024 + 10000)
        self.assertLess(peak, 3 * 1024 * 1024 + 10000)


class PreviewStorageTest(unittest.TestCase):
    setUp = fixtures.PackageReviewedTest.setUp
    image = fixtures.PackageReviewedTest.image
    hash = fixtures.PackageReviewedTest.hash

    def test_ten_repeats_add_no_storage_and_no_zip(self):
        first = preview_pack.preview(self.manifest, self.root / 'previews/v1')
        size = storage.inventory(self.root)['process_bytes']
        for i in range(2, 12):
            result = preview_pack.preview(self.manifest, self.root / f'previews/v{i}')
            self.assertTrue(result['reused'])
            self.assertEqual(result['preview'], first['preview'])
        self.assertEqual(storage.inventory(self.root)['process_bytes'], size)
        self.assertFalse(list((self.root / 'previews').rglob('*.zip')))

    def test_only_changed_asset_gets_new_decoded_previews(self):
        preview_pack.preview(self.manifest, self.root / 'previews/v1')
        before = set((self.root / '.expression-cache').glob('*/*'))
        self.image('表情0.png', (240,240), 42)
        with patch.object(preview_pack, 'contact_sheet', wraps=preview_pack.contact_sheet) as render:
            preview_pack.preview(self.manifest, self.root / 'previews/v2')
            self.assertEqual(render.call_count, 2)
        after = set((self.root / '.expression-cache').glob('*/*'))
        self.assertEqual(len(after - before), 1)
        left = self.root / 'previews/v1/assets/表情1.png'
        right = self.root / 'previews/v2/assets/表情1.png'
        self.assertEqual(left.stat().st_ino, right.stat().st_ino)

    def test_bundle_is_explicit_and_portable(self):
        import zipfile
        result = preview_pack.preview(self.manifest, self.root / 'previews/portable', bundle=True)
        archive = Path(result['preview']).parent / '待验收预览.zip'
        with zipfile.ZipFile(archive) as zipped:
            self.assertIn('assets/表情0.png', zipped.namelist())
            self.assertIn('status.json', zipped.namelist())
            self.assertIsNone(zipped.testzip())

    def test_without_hardlinks_copies_with_valid_reports(self):
        import errno
        with patch('os.link', side_effect=OSError(errno.EOPNOTSUPP, 'synthetic unsupported filesystem')):
            result = preview_pack.preview(self.manifest, self.root / 'previews/copied')
        self.assertTrue(Path(result['preview']).exists())
        self.assertEqual((self.root / 'previews/copied/assets/表情0.png').read_bytes(), (self.root / '表情0.png').read_bytes())
        storage.verified(self.root / 'previews/copied')

    def test_failed_bundle_does_not_leave_partial_preview(self):
        original = preview_pack.seal
        def fail_at_end(project, output, kind, *args):
            if kind == 'preview':
                raise ValueError('synthetic storage failure')
            return original(project, output, kind, *args)
        with patch.object(preview_pack, 'seal', side_effect=fail_at_end):
            with self.assertRaisesRegex(ValueError, 'storage failure'):
                preview_pack.preview(self.manifest, self.root / 'previews/failed', bundle=True)
        self.assertFalse((self.root / 'previews/failed').exists())
        self.assertEqual(list((self.root / 'previews').iterdir()), [])

    def test_budget_stops_before_writing_output(self):
        with patch.object(preview_pack, 'ensure_budget', side_effect=ValueError('budget reached')):
            with self.assertRaisesRegex(ValueError, 'budget reached'):
                preview_pack.preview(self.manifest, self.root / 'previews/v1')
        self.assertFalse((self.root / 'previews/v1').exists())


if __name__ == '__main__':
    unittest.main()
