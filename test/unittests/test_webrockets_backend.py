"""Unit tests for the optional webrockets backend.

The tests mock the webrockets library so no Rust extension is required in
the test environment.  They verify:

* ``_build_server`` wires up connect / receive / disconnect handlers correctly
* the ``on_connect`` handler sends the OVOS "connected" greeting and joins the
  global broadcast room
* ``on_message`` calls ``conn.broadcast`` with the correct room and
  ``exclude_self=False``
* ``on_message`` with ``filter=True`` deserialises the message and logs it
  (or skips filtered types)
* ``on_disconnect`` does not raise
* ``main()`` accepts custom lifecycle hooks (ready_hook / error_hook /
  stopping_hook)
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Stub the 'webrockets' package before importing the backend so the test does
# not require the Rust extension to be installed.
# ---------------------------------------------------------------------------

_webrockets_stub = types.ModuleType("webrockets")


class _FakeConnectDecorator:
    """Mimics webrockets ConnectDecorator — callable that stores the handler."""

    def __init__(self):
        self.handler = None

    def __call__(self, func):
        self.handler = func
        return func


class _FakeRoute:
    """Mimics webrockets WebsocketRoute."""

    def __init__(self):
        self._connect_decorator = _FakeConnectDecorator()
        self._receive_handler = None
        self._disconnect_handler = None

    def connect(self, when="after"):
        return self._connect_decorator

    # Direct-decorator usage: @route.receive
    def receive(self, func):
        self._receive_handler = func
        return func

    # Direct-decorator usage: @route.disconnect
    def disconnect(self, func):
        self._disconnect_handler = func
        return func


class _FakeServer:
    """Mimics webrockets WebsocketServer."""

    def __init__(self, host="0.0.0.0", port=8181, broker=None):
        self.host = host
        self.port = port
        self._route: _FakeRoute | None = None

    def create_route(self, path: str, default_group: str | None = None,
                     authentication_classes=None) -> _FakeRoute:
        self._route = _FakeRoute()
        return self._route

    def start(self):
        pass  # no-op for tests

    def stop(self):
        pass


_webrockets_stub.WebsocketServer = _FakeServer  # type: ignore[attr-defined]

# Install the stub once at module level so the backend import succeeds.
# Tests that need isolation can pop/restore sys.modules themselves.
sys.modules.setdefault("webrockets", _webrockets_stub)

# Now import the backend — it will pick up the stub.
from ovos_messagebus.backends.webrockets_backend import (  # noqa: E402
    _build_server,
    _GLOBAL_ROOM,
    _wait_for_server_ready,
    main,
    on_ready,
    on_error,
    on_stopping,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(host="127.0.0.1", port=8181, route="/core", ssl=None):
    from collections import namedtuple
    MessageBusConfig = namedtuple(
        "MessageBusConfig", ["host", "port", "route", "ssl"]
    )
    return MessageBusConfig(host=host, port=port, route=route, ssl=ssl)


def _make_conn(groups=None):
    conn = MagicMock()
    conn.groups.return_value = groups or [_GLOBAL_ROOM]
    conn.join.return_value = True
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildServer(unittest.TestCase):

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def _build(self, cfg_patch, ssl=None, filter_=False, filter_logs=None):
        cfg_patch.return_value.get.return_value = {
            "filter": filter_,
            "filter_logs": filter_logs or ["gui.status.request"],
        }
        config = _make_config(ssl=ssl)
        server = _build_server(config)
        return server

    def test_returns_fake_server(self):
        server = self._build()
        self.assertIsInstance(server, _FakeServer)

    def test_route_created(self):
        server = self._build()
        self.assertIsNotNone(server._route)

    def test_connect_handler_registered(self):
        server = self._build()
        self.assertIsNotNone(server._route._connect_decorator.handler)

    def test_receive_handler_registered(self):
        server = self._build()
        self.assertIsNotNone(server._route._receive_handler)

    def test_disconnect_handler_registered(self):
        server = self._build()
        self.assertIsNotNone(server._route._disconnect_handler)

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_ssl_warning_logged(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {}
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            _build_server(_make_config(ssl=True))
            log.warning.assert_called_once()
            self.assertIn("SSL", log.warning.call_args[0][0])

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_no_ssl_warning_when_ssl_off(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {}
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            _build_server(_make_config(ssl=None))
            log.warning.assert_not_called()

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_route_path_strips_leading_slash(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {}
        # Patch create_route to capture the path argument
        original_create = _FakeServer.create_route
        captured = {}

        def capturing_create_route(self, path, default_group=None, **kw):
            captured["path"] = path
            self._route = _FakeRoute()
            return self._route

        with patch.object(_FakeServer, "create_route", capturing_create_route):
            _build_server(_make_config(route="/core"))

        self.assertEqual(captured["path"], "core")


class TestOnConnect(unittest.TestCase):

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def _get_handler(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {}
        server = _build_server(_make_config())
        return server._route._connect_decorator.handler

    def test_sends_connected_greeting(self):
        handler = self._get_handler()
        conn = _make_conn()
        handler(conn)
        conn.send.assert_called_once()
        raw = conn.send.call_args[0][0]
        data = json.loads(raw)
        # Message.serialize() uses "type" as the JSON key, not "msg_type"
        self.assertEqual(data["type"], "connected")

    def test_greeting_contains_default_session(self):
        handler = self._get_handler()
        conn = _make_conn()
        handler(conn)
        raw = conn.send.call_args[0][0]
        data = json.loads(raw)
        # context may nest session under "context" key
        context = data.get("context", {})
        session = context.get("session", {})
        self.assertEqual(session.get("session_id"), "default")


class TestOnMessage(unittest.TestCase):

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def _get_handler(self, cfg_patch, filter_=False, filter_logs=None):
        cfg_patch.return_value.get.return_value = {
            "filter": filter_,
            "filter_logs": filter_logs or ["gui.status.request"],
        }
        server = _build_server(_make_config())
        return server._route._receive_handler

    def test_broadcasts_to_global_room(self):
        handler = self._get_handler()
        conn = _make_conn()
        payload = '{"msg_type":"test.msg","data":{},"context":{}}'
        handler(conn, payload)
        conn.broadcast.assert_called_once_with(
            [_GLOBAL_ROOM], payload, exclude_self=False
        )

    def test_broadcast_exclude_self_is_false(self):
        """Sender must also receive its own message — matches Tornado behaviour."""
        handler = self._get_handler()
        conn = _make_conn()
        handler(conn, '{"msg_type":"x","data":{},"context":{}}')
        _, kwargs = conn.broadcast.call_args
        self.assertFalse(kwargs.get("exclude_self", False))

    def test_broadcast_called_even_on_malformed_json(self):
        """Non-OVOS or malformed messages must still be forwarded."""
        handler = self._get_handler()
        conn = _make_conn()
        handler(conn, "not-json")
        conn.broadcast.assert_called_once()

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_filter_mode_logs_message_type(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {
            "filter": True,
            "filter_logs": ["gui.status.request"],
        }
        server = _build_server(_make_config())
        handler = server._route._receive_handler
        conn = _make_conn()
        payload = '{"type":"intent.service.intent","data":{},"context":{}}'
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            handler(conn, payload)
            log.debug.assert_called()

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_filter_mode_skips_filtered_type_log(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {
            "filter": True,
            "filter_logs": ["gui.status.request"],
        }
        server = _build_server(_make_config())
        handler = server._route._receive_handler
        conn = _make_conn()
        # Message.deserialize uses "type" as the JSON key (not "msg_type")
        payload = '{"type":"gui.status.request","data":{},"context":{}}'
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            handler(conn, payload)
            log.debug.assert_not_called()

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_filter_mode_still_broadcasts_filtered_type(self, cfg_patch):
        """Filtered types are NOT logged but MUST still be broadcast."""
        cfg_patch.return_value.get.return_value = {
            "filter": True,
            "filter_logs": ["gui.status.request"],
        }
        server = _build_server(_make_config())
        handler = server._route._receive_handler
        conn = _make_conn()
        payload = '{"type":"gui.status.request","data":{},"context":{}}'
        handler(conn, payload)
        conn.broadcast.assert_called_once()


class TestOnDisconnect(unittest.TestCase):

    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def _get_handler(self, cfg_patch):
        cfg_patch.return_value.get.return_value = {}
        server = _build_server(_make_config())
        return server._route._disconnect_handler

    def test_does_not_raise_with_code_and_reason(self):
        handler = self._get_handler()
        conn = _make_conn()
        handler(conn, 1001, "going away")  # must not raise

    def test_does_not_raise_with_none_args(self):
        handler = self._get_handler()
        conn = _make_conn()
        handler(conn, None, None)  # must not raise


class TestLifecycleHooks(unittest.TestCase):

    def test_on_ready_logs(self):
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            on_ready()
            log.info.assert_called_once()

    def test_on_error_logs(self):
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            on_error("boom")
            log.info.assert_called_once()
            self.assertIn("boom", log.info.call_args[0][0])

    def test_on_stopping_logs(self):
        with patch("ovos_messagebus.backends.webrockets_backend.LOG") as log:
            on_stopping()
            log.info.assert_called_once()


class TestWaitForServerReady(unittest.TestCase):

    def test_returns_immediately_when_port_open(self):
        import socket as _socket
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            _, port = srv.getsockname()
            _wait_for_server_ready("127.0.0.1", port, timeout=1.0)  # must not raise

    def test_times_out_gracefully_when_port_closed(self):
        """No listening socket — must return (with warning) within timeout."""
        _wait_for_server_ready("127.0.0.1", 19999, timeout=0.2)  # must not raise


class TestMain(unittest.TestCase):

    @patch("ovos_messagebus.backends.webrockets_backend.wait_for_exit_signal")
    @patch("ovos_messagebus.backends.webrockets_backend._wait_for_server_ready")
    @patch("ovos_messagebus.backends.webrockets_backend.threading")
    @patch("ovos_messagebus.backends.webrockets_backend._build_server")
    @patch("ovos_messagebus.backends.webrockets_backend.load_message_bus_config")
    @patch("ovos_messagebus.backends.webrockets_backend.init_service_logger")
    @patch("ovos_messagebus.backends.webrockets_backend.reset_sigint_handler")
    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_calls_lifecycle_hooks(
        self,
        cfg_patch,
        reset_sig,
        init_log,
        load_cfg,
        build_srv,
        threading_mock,
        wait_ready_mock,
        wait_exit,
    ):
        cfg_patch.return_value.get.return_value = {}
        load_cfg.return_value = _make_config()
        build_srv.return_value = MagicMock()
        thread_instance = MagicMock()
        threading_mock.Thread.return_value = thread_instance

        ready = MagicMock()
        error = MagicMock()
        stopping = MagicMock()

        main(ready_hook=ready, error_hook=error, stopping_hook=stopping)

        wait_ready_mock.assert_called_once()
        ready.assert_called_once()
        stopping.assert_called_once()
        error.assert_not_called()

    @patch("ovos_messagebus.backends.webrockets_backend.wait_for_exit_signal")
    @patch("ovos_messagebus.backends.webrockets_backend._wait_for_server_ready")
    @patch("ovos_messagebus.backends.webrockets_backend.threading")
    @patch("ovos_messagebus.backends.webrockets_backend._build_server",
           side_effect=RuntimeError("build failed"))
    @patch("ovos_messagebus.backends.webrockets_backend.load_message_bus_config")
    @patch("ovos_messagebus.backends.webrockets_backend.init_service_logger")
    @patch("ovos_messagebus.backends.webrockets_backend.reset_sigint_handler")
    @patch("ovos_messagebus.backends.webrockets_backend.Configuration")
    def test_calls_error_hook_on_build_failure(
        self,
        cfg_patch,
        reset_sig,
        init_log,
        load_cfg,
        build_srv,
        threading_mock,
        wait_ready_mock,
        wait_exit,
    ):
        cfg_patch.return_value.get.return_value = {}
        load_cfg.return_value = _make_config()

        error = MagicMock()
        with self.assertRaises(RuntimeError):
            main(error_hook=error)

        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
