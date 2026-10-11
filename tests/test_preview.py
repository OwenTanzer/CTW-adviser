"""The human inspection preview must identify its exact adviser revision."""
import importlib.util
import os
import sys
from pathlib import Path
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from ctw_adviser.preview import preview_banner, preview_revision

SHA = 'a' * 40


def inspection_plugin():
    """Load the page renderer without installing Datasette in the unit runner."""
    datasette = types.ModuleType('datasette')
    datasette.hookimpl = lambda function: function
    utils = types.ModuleType('datasette.utils')
    asgi = types.ModuleType('datasette.utils.asgi')
    asgi.Response = object
    markupsafe = types.ModuleType('markupsafe')
    markupsafe.Markup = str
    path = Path(__file__).resolve().parents[1] / 'inspection_plugins' / 'unit_packets.py'
    spec = importlib.util.spec_from_file_location('test_unit_packets_preview', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'datasette': datasette, 'datasette.utils': utils,
                                  'datasette.utils.asgi': asgi, 'markupsafe': markupsafe}):
        spec.loader.exec_module(module)
    return module


class PreviewTests(unittest.TestCase):
    def test_ordinary_service_has_no_preview_label(self):
        self.assertIsNone(preview_revision({'RAILWAY_GIT_BRANCH': 'main',
                                            'RAILWAY_GIT_COMMIT_SHA': SHA}))
        self.assertEqual(preview_banner({}), '')

    def test_github_trigger_identifies_unmerged_pr_and_exact_commit(self):
        values = {'RAILWAY_GIT_BRANCH': 'issue-19/character-access',
                  'RAILWAY_GIT_COMMIT_SHA': SHA}
        self.assertEqual(preview_revision(values),
                         {'label': 'PR #23 preview — unmerged', 'adviser_commit': SHA})
        banner = preview_banner(values)
        self.assertIn('PR #23 preview — unmerged', banner)
        self.assertIn('commit/' + SHA, banner)
        self.assertIn('<code>' + SHA + '</code>', banner)

    def test_explicit_commit_supports_a_pinned_manual_preview(self):
        values = {'CTW_PREVIEW_PR': '23', 'CTW_ADVISER_COMMIT': SHA.upper()}
        self.assertEqual(preview_revision(values)['adviser_commit'], SHA)

    def test_missing_invalid_or_conflicting_commit_fails_closed(self):
        for values in (
            {'RAILWAY_GIT_BRANCH': 'issue-19/character-access'},
            {'CTW_PREVIEW_PR': '23', 'CTW_ADVISER_COMMIT': 'not-a-sha'},
            {'CTW_PREVIEW_PR': '23', 'RAILWAY_GIT_BRANCH': 'main',
             'RAILWAY_GIT_COMMIT_SHA': SHA},
            {'CTW_PREVIEW_PR': '23', 'RAILWAY_GIT_COMMIT_SHA': SHA,
             'CTW_ADVISER_COMMIT': 'b' * 40},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                preview_revision(values)

    def test_inspection_pages_show_the_label_and_full_sha(self):
        plugin = inspection_plugin()
        with patch.dict(os.environ, {'RAILWAY_GIT_BRANCH': 'issue-19/character-access',
                                     'RAILWAY_GIT_COMMIT_SHA': SHA}, clear=True):
            rendered = plugin.page('<section>example</section>')
            self.assertIn('PR #23 preview — unmerged', rendered)
            self.assertIn('<code>' + SHA + '</code>', rendered)
            self.assertIn('<section>example</section>', rendered)
            self.assertEqual(len(plugin.register_routes(None)), 2)

    def test_inspection_plugin_rejects_preview_without_commit(self):
        plugin = inspection_plugin()
        with patch.dict(os.environ, {'RAILWAY_GIT_BRANCH': 'issue-19/character-access'},
                        clear=True), self.assertRaisesRegex(ValueError, 'exact adviser commit'):
            plugin.register_routes(None)


if __name__ == '__main__':
    unittest.main()
