"""Token source order and documented exit codes (LIFE-907).

Run: PYTHONPATH=src python -m unittest discover -s tests
"""
import os
import unittest
from unittest import mock

import httpx
import typer
from typer.testing import CliRunner

from lifenote import auth, cli
from lifenote.api import APIError
from lifenote.config import EXIT_AUTH, EXIT_NETWORK, EXIT_SERVER, EXIT_USAGE

CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in ("LIFENOTE_TOKEN", "LIFENOTE_API_TOKEN")}


def fake_keyring(store):
    m = mock.MagicMock()
    m.get_password.side_effect = lambda service, user: store.get(user)
    return m


class TokenSourceTests(unittest.TestCase):

    def test_order_is_env_then_legacy_env_then_saved_pat_then_sign_in(self):
        store = {"personal-access-token": "ln_pat_saved", "agent-token": '{"access": "lna_session"}'}
        with mock.patch.dict("sys.modules", {"keyring": fake_keyring(store)}):
            with mock.patch.dict(os.environ, {**CLEAN_ENV, "LIFENOTE_TOKEN": "ln_pat_env",
                                              "LIFENOTE_API_TOKEN": "lna_old"}, clear=True):
                self.assertEqual(auth.token_source(), ("ln_pat_env", "env LIFENOTE_TOKEN"))
            with mock.patch.dict(os.environ, {**CLEAN_ENV, "LIFENOTE_API_TOKEN": "lna_old"}, clear=True):
                self.assertEqual(auth.token_source()[0], "lna_old")
            with mock.patch.dict(os.environ, CLEAN_ENV, clear=True):
                self.assertEqual(auth.token_source()[0], "ln_pat_saved")
                del store["personal-access-token"]
                self.assertEqual(auth.token_source()[0], "lna_session")
                # Managing tokens always uses the sign-in, never a PAT.
                store["personal-access-token"] = "ln_pat_saved"
                self.assertEqual(auth.get_session_token(), "lna_session")

    def test_env_token_never_touches_the_keychain(self):
        # On headless Linux a keyring lookup can block ~25 s on D-Bus.
        kr = mock.MagicMock()
        kr.get_password.side_effect = AssertionError("keychain touched")
        with mock.patch.dict("sys.modules", {"keyring": kr}), \
                mock.patch.dict(os.environ, {**CLEAN_ENV, "LIFENOTE_TOKEN": "ln_pat_env"}, clear=True):
            self.assertEqual(auth.get_token(), "ln_pat_env")
        kr.get_password.assert_not_called()


class ExitCodeTests(unittest.TestCase):

    def _code(self, status, body):
        with self.assertRaises(typer.Exit) as ctx:
            cli._handle_api_error(APIError(status, body))
        return ctx.exception.exit_code

    def test_api_errors_map_to_documented_codes(self):
        self.assertEqual(self._code(401, {"error": "invalid_token"}), EXIT_AUTH)
        self.assertEqual(self._code(403, {"error": "pat_cannot_manage_tokens"}), EXIT_AUTH)
        self.assertEqual(self._code(403, {"error": "insufficient_scope"}), EXIT_AUTH)
        self.assertEqual(self._code(400, {"error": "invalid_request"}), EXIT_USAGE)
        self.assertEqual(self._code(404, {"error": "not_found"}), EXIT_USAGE)
        self.assertEqual(self._code(429, {"reason": "per-token daily limit exceeded"}), EXIT_SERVER)
        self.assertEqual(self._code(500, "boom"), EXIT_SERVER)
        self.assertEqual(self._code(502, "<html>"), EXIT_SERVER)

    def test_cli_commands_exit_3_when_the_token_is_dead(self):
        runner = CliRunner()
        with mock.patch.object(cli, "get", side_effect=APIError(401, {"error": "invalid_token"})), \
                mock.patch.object(cli, "token_source", return_value=("ln_pat_x", "env LIFENOTE_TOKEN")):
            r = runner.invoke(cli.app, ["auth", "status"])
        self.assertEqual(r.exit_code, EXIT_AUTH)
        with mock.patch.object(cli, "token_source", return_value=(None, None)):
            r = runner.invoke(cli.app, ["auth", "status"])
        self.assertEqual(r.exit_code, EXIT_AUTH)

    def test_token_commands_refuse_without_an_interactive_sign_in(self):
        with mock.patch.object(cli, "get_session_token", return_value=None):
            r = CliRunner().invoke(cli.app, ["token", "create", "--name", "x"])
        self.assertEqual(r.exit_code, EXIT_AUTH)
        r = CliRunner().invoke(cli.app, ["token", "create", "--name", "x", "--expires", "7d"])
        self.assertEqual(r.exit_code, EXIT_USAGE)

    def test_token_is_shown_even_when_the_keychain_save_fails(self):
        created = {"id": 9, "name": "x", "token": "ln_pat_SHOWN", "expires_at": "2027-01-01T00:00:00Z"}
        with mock.patch.object(cli, "get_session_token", return_value="lna_s"), \
                mock.patch.object(cli, "post", return_value=created), \
                mock.patch.object(cli, "save_pat", side_effect=RuntimeError("no keyring")):
            r = CliRunner().invoke(cli.app, ["token", "create", "--name", "x", "--save"])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("ln_pat_SHOWN", r.output)

    def test_network_failure_exits_4(self):
        with mock.patch.object(cli, "app", side_effect=httpx.ConnectError("refused")):
            with self.assertRaises(SystemExit) as ctx:
                cli.main()
        self.assertEqual(ctx.exception.code, EXIT_NETWORK)


if __name__ == "__main__":
    unittest.main()
