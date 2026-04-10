"""Tests for the CLI commands using click.testing.CliRunner."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture()
def runner():
    return CliRunner()


class TestInitCommand:
    def test_init_creates_structure(self, tmp_path, runner):
        from brainvault.cli.main import cli

        result = runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output

        # Check key directories exist
        assert (tmp_path / "wiki").is_dir()
        assert (tmp_path / "raw").is_dir()
        assert (tmp_path / "meta").is_dir()
        assert (tmp_path / ".brainvault").is_dir()

    def test_init_creates_config(self, tmp_path, runner):
        from brainvault.cli.main import cli

        result = runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "meta" / "config.yaml").exists()

    def test_init_creates_schema_md(self, tmp_path, runner):
        from brainvault.cli.main import cli

        result = runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "meta" / "schema.md").exists()

    def test_init_creates_gitignore(self, tmp_path, runner):
        from brainvault.cli.main import cli

        result = runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".gitignore").exists()

    def test_init_creates_state_json(self, tmp_path, runner):
        from brainvault.cli.main import cli

        result = runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".brainvault" / "state.json").exists()

    def test_init_with_postgresql(self, tmp_path, runner):
        from brainvault.cli.main import cli

        result = runner.invoke(cli, ["init", str(tmp_path), "--db", "postgresql"])
        assert result.exit_code == 0, result.output
        import yaml

        cfg = yaml.safe_load((tmp_path / "meta" / "config.yaml").read_text())
        assert cfg["database"]["type"] == "postgresql"

    def test_init_guard_skips_second_init(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(cli, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert "already initialised" in result.output

    def test_init_force_reinitialises(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(cli, ["init", str(tmp_path), "--force"])
        assert result.exit_code == 0
        assert "already initialised" not in result.output


class TestStatusCommand:
    def test_status_after_init(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(cli, ["status", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "sqlite" in result.output.lower() or "local" in result.output.lower()


class TestMigrateCommand:
    def test_migrate_same_backends_noop(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(
            cli,
            [
                "migrate",
                "--from", "sqlite-local",
                "--to", "sqlite-local",
                "--vault", str(tmp_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "identical" in result.output.lower() or "nothing to do" in result.output.lower()

    def test_migrate_dry_run(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(
            cli,
            [
                "migrate",
                "--from", "sqlite-local",
                "--to", "postgresql-local",
                "--vault", str(tmp_path),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "dry run" in result.output.lower()

    def test_migrate_invalid_descriptor(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(
            cli,
            [
                "migrate",
                "--from", "badformat",
                "--to", "sqlite-local",
                "--vault", str(tmp_path),
            ],
        )
        # Should exit non-zero or show an error
        assert result.exit_code != 0 or "invalid" in result.output.lower() or "error" in result.output.lower()


class TestSearchCommand:
    def test_search_no_results(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        result = runner.invoke(cli, ["search", "xyzzy_not_in_db", "--vault", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "no results" in result.output.lower()

    def test_search_finds_page(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        # Write a page and sync
        page = tmp_path / "wiki" / "test_page.md"
        page.write_text("# BrainVault Test\n\nThis is a searchable document.", encoding="utf-8")
        runner.invoke(cli, ["sync", str(tmp_path)])

        result = runner.invoke(cli, ["search", "BrainVault", "--vault", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "wiki/test_page.md" in result.output


class TestSyncCommand:
    def test_sync_wiki_pages(self, tmp_path, runner):
        from brainvault.cli.main import cli

        runner.invoke(cli, ["init", str(tmp_path)])
        page = tmp_path / "wiki" / "hello.md"
        page.write_text("# Hello\n\nWorld.", encoding="utf-8")

        result = runner.invoke(cli, ["sync", str(tmp_path)])
        assert result.exit_code == 0, result.output
        # Should report synced pages
        assert "synced" in result.output.lower() or "sync" in result.output.lower()
