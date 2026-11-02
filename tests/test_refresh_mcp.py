"""Offline regressions for issues #5, #6 and #7. No real keyring or network."""
import io
import json
import os
import unittest
from unittest import mock

import httpx

from lifenote import auth, mcp_proxy

CLIENT = httpx.Client
SIGN_IN = "keychain (sign-in)"
PAT = "keychain (personal access token)"


class RefreshTests(unittest.TestCase):
    def exchange(self, response):
        def handle(request):
            if isinstance(response, Exception):
                raise response
            return response
        with mock.patch.object(auth.httpx, "Client", side_effect=lambda **kw: CLIENT(
                transport=httpx.MockTransport(handle), **kw)), \
                mock.patch.object(auth, "clear_token") as clear, \
                mock.patch.object(auth, "store_credentials") as store:
            result = auth._try_refresh("fake-refresh")
        return result, clear, store

    def test_only_explicit_invalid_grant_clears_sign_in(self):
        for status in (400, 401):
            with self.subTest(status=status):
                result, clear, store = self.exchange(httpx.Response(status, json={"error": "invalid_grant"}))
                self.assertIsNone(result)
                clear.assert_called_once_with()
                store.assert_not_called()

    def test_transient_and_unrecognized_failures_preserve_sign_in(self):
        responses = [httpx.Response(s, json={"error": "invalid_grant"}) for s in (429, 500, 502, 503, 504)]
        responses += [httpx.Response(400, json={"error": e}) for e in ("invalid_client", "unauthorized_client")]
        responses += [httpx.Response(401, content=b""), httpx.Response(400, text="<html>"),
                      httpx.Response(400, json=[]), httpx.Response(400, json=None),
                      httpx.Response(200, text="broken"), httpx.ConnectError("offline")]
        for response in responses:
            with self.subTest(response=response):
                result, clear, store = self.exchange(response)
                self.assertIsNone(result)
                clear.assert_not_called()
                store.assert_not_called()

    def test_success_stores_rotated_credentials(self):
        result, clear, store = self.exchange(httpx.Response(200, json={
            "access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}))
        self.assertEqual(result, "new-access")
        clear.assert_not_called()
        store.assert_called_once_with(access="new-access", refresh="new-refresh", expires_in=3600)


class ProxyTests(unittest.TestCase):
    def proxy(self, responses, requests=None, source=SIGN_IN, rotated=None):
        requests = requests if requests is not None else [{"jsonrpc": "2.0", "id": 7, "method": "tools/list"}]
        sent = []
        replies = iter(responses)

        def handle(request):
            sent.append(request)
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return reply

        stdout = io.StringIO()
        with mock.patch.object(mcp_proxy.httpx, "Client", side_effect=lambda **kw: CLIENT(
                transport=httpx.MockTransport(handle), **kw)), \
                mock.patch.object(mcp_proxy, "token_source", side_effect=source if callable(source) else None,
                                  return_value=("fake-token", source)), \
                mock.patch.object(mcp_proxy, "_read_keyring_blob", return_value={"refresh": "fake-refresh"}) as read, \
                mock.patch.object(mcp_proxy, "_refresh_with_lock", return_value=rotated) as refresh, \
                mock.patch("sys.stdin", io.StringIO("\n".join(json.dumps(r) for r in requests))), \
                mock.patch("sys.stdout", stdout):
            mcp_proxy.run()
        output = [json.loads(line) for line in stdout.getvalue().splitlines()]
        return output, sent, read, refresh

    def assert_error(self, output, req_id=7):
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["jsonrpc"], "2.0")
        self.assertEqual(output[0]["id"], req_id)
        self.assertIsInstance(output[0]["error"]["code"], int)
        self.assertIsInstance(output[0]["error"]["message"], str)

    def test_http_errors_always_answer_requests(self):
        for status in (302, 400, 403, 429, 500, 502, 504):
            for body in (b"", b'{"error":"rate_limited"}', b"<html>bad gateway</html>"):
                with self.subTest(status=status, body=body):
                    output, *_ = self.proxy([httpx.Response(status, content=body)])
                    self.assert_error(output)
                    self.assertIn(f"HTTP {status}", output[0]["error"]["message"])

    def test_invalid_success_responses_answer_requests(self):
        bodies = [b"", b"not json", b"null", b"[]", b'{"error":"limited"}',
                  b'{"jsonrpc":"2.0","id":8,"result":{}}',
                  b'{"jsonrpc":"1.0","id":7,"result":{}}',
                  b'{"jsonrpc":"2.0","id":7,"error":"bad"}',
                  b'{"jsonrpc":"2.0","id":7,"result":{},"error":{}}']
        for body in bodies:
            with self.subTest(body=body):
                self.assert_error(self.proxy([httpx.Response(200, content=body)])[0])
        self.assert_error(self.proxy([httpx.Response(202)])[0])

    def test_id_zero_string_and_null_are_correlated(self):
        for req_id in (0, "call-1", None):
            with self.subTest(req_id=req_id):
                output, *_ = self.proxy([httpx.Response(502)], requests=[{
                    "jsonrpc": "2.0", "id": req_id, "method": "tools/list"}])
                self.assert_error(output, req_id)

    def test_notifications_never_receive_responses(self):
        for response in (httpx.Response(202), httpx.Response(200, json={"result": {}}),
                         httpx.Response(401), httpx.Response(429, json={"error": "limited"}),
                         httpx.Response(502), httpx.ConnectError("offline")):
            with self.subTest(response=response):
                output, *_ = self.proxy([response], requests=[{
                    "jsonrpc": "2.0", "method": "notifications/initialized"}])
                self.assertEqual(output, [])

    def test_transport_error_is_correlated(self):
        self.assert_error(self.proxy([httpx.ReadTimeout("offline")])[0])

    def test_rejected_pat_never_reads_or_rotates_sign_in(self):
        for source in (PAT, "env LIFENOTE_TOKEN", "env LIFENOTE_API_TOKEN"):
            with self.subTest(source=source):
                output, sent, read, refresh = self.proxy([httpx.Response(401)], source=source)
                self.assert_error(output)
                self.assertEqual(len(sent), 1)
                read.assert_not_called()
                refresh.assert_not_called()
                expected = "saved personal access token" if source == PAT else source
                self.assertIn(expected, output[0]["error"]["message"])
                if source == PAT:
                    self.assertIn("token create --name mcp --save", output[0]["error"]["message"])

    def test_sign_in_refresh_retries_once_with_rotated_token_and_no_session(self):
        first = {"jsonrpc": "2.0", "id": 1, "result": {}}
        second = {"jsonrpc": "2.0", "id": 7, "result": {"tools": []}}
        output, sent, _, refresh = self.proxy([
            httpx.Response(200, json=first, headers={"Mcp-Session-Id": "session-1"}),
            httpx.Response(401), httpx.Response(200, json=second)], requests=[
                {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}], rotated="rotated-token")
        self.assertEqual(output, [first, second])
        refresh.assert_called_once_with("fake-refresh")
        self.assertEqual(sent[1].headers["Mcp-Session-Id"], "session-1")
        self.assertNotIn("Mcp-Session-Id", sent[2].headers)
        self.assertEqual(sent[2].headers["Authorization"], "Bearer rotated-token")

    def test_failed_refresh_and_rejected_retry_are_correlated(self):
        for rotated in (None, "rotated-token"):
            with self.subTest(rotated=rotated):
                output, sent, _, refresh = self.proxy([httpx.Response(401), httpx.Response(401)], rotated=rotated)
                self.assert_error(output)
                self.assertIn("retry later", output[0]["error"]["message"])
                self.assertEqual(len(sent), 2 if rotated else 1)
                refresh.assert_called_once()

    def test_valid_upstream_rpc_error_is_preserved(self):
        body = {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Unknown method"}}
        self.assertEqual(self.proxy([httpx.Response(200, json=body)])[0], [body])

    def test_saved_pat_with_real_precedence_leaves_sign_in_untouched(self):
        # Exercise the actual auth resolver with a fake keyring containing both.
        kr = mock.Mock()
        kr.get_password.side_effect = lambda service, user: {
            "personal-access-token": "fake-saved-pat",
            "agent-token": json.dumps({"access": "fake-session", "refresh": "fake-refresh"}),
        }.get(user)
        with mock.patch.dict(os.environ, {"LIFENOTE_TOKEN": "", "LIFENOTE_API_TOKEN": ""}), \
                mock.patch.dict("sys.modules", {"keyring": kr}):
            output, sent, read, refresh = self.proxy(
                [httpx.Response(401), httpx.Response(401)], source=auth.token_source,
                requests=[{"jsonrpc": "2.0", "id": n, "method": "tools/list"} for n in (1, 2)])
        self.assertEqual([r["id"] for r in output], [1, 2])
        self.assertTrue(all("saved personal access token" in r["error"]["message"] for r in output))
        self.assertEqual(len(sent), 2)
        self.assertTrue(all(r.headers["Authorization"] == "Bearer fake-saved-pat" for r in sent))
        read.assert_not_called()
        refresh.assert_not_called()
        self.assertEqual(kr.get_password.call_count, 3)
        self.assertTrue(all(c.args[1] == "personal-access-token" for c in kr.get_password.call_args_list))


if __name__ == "__main__":
    unittest.main()
