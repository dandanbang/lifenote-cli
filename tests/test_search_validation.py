"""`lifenote search` rejects <2-char queries locally with EXIT_USAGE (no request sent)."""
import unittest
from unittest import mock

from typer.testing import CliRunner

from lifenote import cli
from lifenote.config import EXIT_USAGE


class SearchValidationTests(unittest.TestCase):

    def test_single_char_search_exits_2_without_network(self):
        def _no_network(*args, **kwargs):
            raise AssertionError("no request should be sent")

        with mock.patch.object(cli, "get", side_effect=_no_network):
            r = CliRunner().invoke(cli.app, ["search", "x"])
        self.assertEqual(r.exit_code, EXIT_USAGE)
        self.assertIn("2 characters", r.output)

    def test_empty_search_exits_2(self):
        with mock.patch.object(cli, "get", side_effect=AssertionError("no request")):
            r = CliRunner().invoke(cli.app, ["search", ""])
        self.assertEqual(r.exit_code, EXIT_USAGE)

    def test_two_char_search_passes_validation(self):
        with mock.patch.object(cli, "get", return_value={"entries": []}) as fake_get:
            r = CliRunner().invoke(cli.app, ["search", "xy"])
        fake_get.assert_called_once()
        self.assertEqual(r.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
