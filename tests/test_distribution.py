from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import plananvil_dist


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def init_repo(path: Path, *, config: str | None = None, hooks: dict | None = None) -> Path:
    path.mkdir(parents=True)
    run('git', 'init', '-b', 'main', cwd=path)
    run('git', 'config', 'user.name', 'PlanAnvil Test', cwd=path)
    run('git', 'config', 'user.email', 'plananvil-test@example.invalid', cwd=path)
    (path / 'README.md').write_text('# Fixture\n', encoding='utf-8')
    (path / 'AGENTS.md').write_text('USER_OWNED_AGENTS\n', encoding='utf-8')
    if config is not None:
        p = path / '.codex/config.toml'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(config, encoding='utf-8')
    if hooks is not None:
        p = path / '.codex/hooks.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(hooks, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    run('git', 'add', '-A', cwd=path)
    run('git', 'commit', '-m', 'fixture', cwd=path)
    return path


def commit_all(repo: Path, message: str) -> None:
    run('git', 'add', '-A', cwd=repo)
    run('git', 'commit', '-m', message, cwd=repo)


def synthetic_source(source: Path, version: str) -> Path:
    source.mkdir(parents=True)
    manifest = json.loads((ROOT / 'distribution/manifest.json').read_text(encoding='utf-8'))
    for raw in manifest['copy_roots'] + [manifest['hooks_source']]:
        src = ROOT / raw
        dest = source / raw
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    (source / 'distribution').mkdir(parents=True, exist_ok=True)
    manifest['product_version'] = version
    (source / 'distribution/manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return source


class DistributionTests(unittest.TestCase):
    def test_install_verify_and_uninstall_clean_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / 'repo')
            original_agents = (repo / 'AGENTS.md').read_bytes()
            state = plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            self.assertEqual(state['product_version'], '0.2.0')
            self.assertTrue((repo / '.agents/skills/plan-anvil/SKILL.md').is_file())
            self.assertTrue((repo / '.plananvil/installation.json').is_file())
            self.assertTrue(plananvil_dist.verify_installation(repo)['ok'])
            self.assertEqual((repo / 'AGENTS.md').read_bytes(), original_agents)
            commit_all(repo, 'install plananvil')
            result = plananvil_dist.uninstall(repo, False)
            self.assertTrue(result['ok'])
            self.assertFalse((repo / '.agents/skills/plan-anvil/SKILL.md').exists())
            self.assertFalse((repo / '.plananvil/installation.json').exists())
            self.assertEqual((repo / 'AGENTS.md').read_bytes(), original_agents)

    def test_existing_config_and_hooks_are_preserved(self) -> None:
        config = '[agents]\nenabled = true\nmax_concurrent_threads_per_session = 2\n\n[other]\nvalue = "keep"\n'
        custom_hook = {
            'metadata': {'owner': 'fixture'},
            'hooks': {
                'PreToolUse': [
                    {'matcher': '^Custom$', 'hooks': [{'type': 'command', 'command': 'echo custom'}]}
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / 'repo', config=config, hooks=custom_hook)
            plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            self.assertEqual((repo / '.codex/config.toml').read_text(encoding='utf-8'), config)
            merged = json.loads((repo / '.codex/hooks.json').read_text(encoding='utf-8'))
            self.assertEqual(merged['metadata'], {'owner': 'fixture'})
            self.assertIn(custom_hook['hooks']['PreToolUse'][0], merged['hooks']['PreToolUse'])
            commit_all(repo, 'install plananvil')
            plananvil_dist.uninstall(repo, False)
            final_hooks = json.loads((repo / '.codex/hooks.json').read_text(encoding='utf-8'))
            self.assertEqual(final_hooks, custom_hook)
            self.assertEqual((repo / '.codex/config.toml').read_text(encoding='utf-8'), config)

    def test_conflicting_disabled_agents_fails_without_changes(self) -> None:
        config = '[agents]\nenabled = false\n'
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / 'repo', config=config)
            before = run('git', 'status', '--porcelain', cwd=repo).stdout
            with self.assertRaises(plananvil_dist.DistError):
                plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            self.assertEqual((repo / '.codex/config.toml').read_text(encoding='utf-8'), config)
            self.assertEqual(run('git', 'status', '--porcelain', cwd=repo).stdout, before)

    def test_upgrade_replaces_only_unmodified_owned_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root / 'repo')
            plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            commit_all(repo, 'install plananvil')
            source = synthetic_source(root / 'source', '0.2.1')
            skill = source / '.agents/skills/plan-anvil/SKILL.md'
            skill.write_text(skill.read_text(encoding='utf-8') + '\n<!-- upgrade fixture -->\n', encoding='utf-8')
            state = plananvil_dist.install_or_upgrade(source, repo, True, False)
            self.assertEqual(state['product_version'], '0.2.1')
            self.assertIn('upgrade fixture', (repo / '.agents/skills/plan-anvil/SKILL.md').read_text(encoding='utf-8'))
            self.assertTrue(plananvil_dist.verify_installation(repo)['ok'])

    def test_upgrade_refuses_locally_modified_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root / 'repo')
            plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            commit_all(repo, 'install plananvil')
            path = repo / '.agents/skills/plan-anvil/SKILL.md'
            path.write_text(path.read_text(encoding='utf-8') + '\nLOCAL CHANGE\n', encoding='utf-8')
            source = synthetic_source(root / 'source', '0.2.1')
            with self.assertRaises(plananvil_dist.DistError):
                plananvil_dist.install_or_upgrade(source, repo, True, True)
            self.assertIn('LOCAL CHANGE', path.read_text(encoding='utf-8'))

    def test_uninstall_refuses_locally_modified_managed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / 'repo')
            plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            commit_all(repo, 'install plananvil')
            path = repo / '.codex/hooks/plan-anvil-guard.py'
            path.write_text(path.read_text(encoding='utf-8') + '\n# local\n', encoding='utf-8')
            with self.assertRaises(plananvil_dist.DistError):
                plananvil_dist.uninstall(repo, True)
            self.assertTrue(path.exists())
            self.assertTrue((repo / '.plananvil/installation.json').exists())

    def test_nested_target_installs_at_monorepo_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / 'repo')
            nested = repo / 'packages/app'
            nested.mkdir(parents=True)
            (nested / 'README.md').write_text('# App\n', encoding='utf-8')
            commit_all(repo, 'add monorepo package')
            plananvil_dist.install_or_upgrade(ROOT, nested, False, False)
            self.assertTrue((repo / '.agents/skills/plan-anvil/SKILL.md').is_file())
            self.assertTrue((repo / '.plananvil/installation.json').is_file())
            self.assertFalse((nested / '.plananvil/installation.json').exists())
            self.assertTrue(plananvil_dist.verify_installation(nested)['ok'])

    def test_failed_payload_copy_rolls_back_partial_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = init_repo(Path(tmp) / 'repo')
            real_copy = plananvil_dist.shutil.copy2
            calls = {'count': 0}

            def fail_on_second_copy(src, dst, *args, **kwargs):
                calls['count'] += 1
                if calls['count'] == 2:
                    raise OSError('injected copy failure')
                return real_copy(src, dst, *args, **kwargs)

            with patch.object(plananvil_dist.shutil, 'copy2', side_effect=fail_on_second_copy):
                with self.assertRaises(OSError):
                    plananvil_dist.install_or_upgrade(ROOT, repo, False, False)
            self.assertFalse((repo / '.agents/skills/plan-anvil').exists())
            self.assertFalse((repo / '.plananvil/installation.json').exists())
            self.assertFalse((repo / '.codex/hooks/plan-anvil-guard.py').exists())
            self.assertEqual(run('git', 'status', '--porcelain', cwd=repo).stdout, '')


if __name__ == '__main__':
    unittest.main()
