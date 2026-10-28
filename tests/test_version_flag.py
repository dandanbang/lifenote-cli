"""`lifenote --version` prints the version (what pipx users and install docs try first)."""
import unittest

from typer.testing import CliRunner

from lifenote import __version__, cli


class VersionFlagTests(unittest.TestCase):

    def test_version_flag_prints_the_version(self):
        result = CliRunner().invoke(cli.app, ["--version"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.output.strip(), f"lifenote {__version__}")

    def test_subcommands_still_run_after_the_root_callback(self):
        result = CliRunner().invoke(cli.app, ["version"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(__version__, result.output)


if __name__ == "__main__":
    unittest.main()
