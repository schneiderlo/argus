from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import argus
from argus.config import ArgusConfig


class ProjectScaffoldTests(unittest.TestCase):
    def test_package_version_is_defined(self) -> None:
        self.assertEqual(argus.__version__, "0.1.0")

    def test_config_discovers_repo_relative_paths(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = ArgusConfig.discover(root)

        self.assertEqual(config.root_dir, root.resolve())
        self.assertEqual(config.artifacts_dir, root.resolve() / "artifacts")
        self.assertEqual(config.runs_dir, root.resolve() / "artifacts" / "runs")
        self.assertEqual(config.agent_runs_dir, root.resolve() / "artifacts" / "agent_runs")

    def test_pyproject_declares_argus_console_script(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject_text = pyproject_path.read_text(encoding="utf-8")

        self.assertIn('[project.scripts]', pyproject_text)
        self.assertIn('argus = "argus.cli:main"', pyproject_text)
