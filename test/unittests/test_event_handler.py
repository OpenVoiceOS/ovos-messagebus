# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for ovos_messagebus.event_handler."""
import json
import pytest
from unittest.mock import patch, MagicMock, call


def _make_handler():
    """Create a MessageBusEventHandler without tornado's __init__."""
    from ovos_messagebus.event_handler import MessageBusEventHandler
    handler = object.__new__(MessageBusEventHandler)
    # Minimal EventEmitter init so .on() works
    from pyee import EventEmitter
    handler.emitter = EventEmitter()
    return handler


class TestMessageBusEventHandlerProperties:
    def test_filter_false_by_default(self):
        handler = _make_handler()
        ws_cfg = {"websocket": {}}
        with patch("ovos_messagebus.event_handler.Configuration",
                   return_value=ws_cfg):
            assert handler.filter is False

    def test_filter_true_when_configured(self):
        handler = _make_handler()
        ws_cfg = {"websocket": {"filter": True}}
        with patch("ovos_messagebus.event_handler.Configuration",
                   return_value=ws_cfg):
            assert handler.filter is True

    def test_max_message_size_default_10mb(self):
        handler = _make_handler()
        ws_cfg = {"websocket": {}}
        with patch("ovos_messagebus.event_handler.Configuration",
                   return_value=ws_cfg):
            assert handler.max_message_size == 10 * 1024 * 1024

    def test_max_message_size_custom(self):
        handler = _make_handler()
        ws_cfg = {"websocket": {"max_msg_size": 5}}
        with patch("ovos_messagebus.event_handler.Configuration",
                   return_value=ws_cfg):
            assert handler.max_message_size == 5 * 1024 * 1024

    def test_filter_logs_defaults(self):
        handler = _make_handler()
        ws_cfg = {"websocket": {}}
        with patch("ovos_messagebus.event_handler.Configuration",
                   return_value=ws_cfg):
            logs = handler.filter_logs
        assert "gui.status.request" in logs
        assert "gui.page.upload" in logs


class TestClientConnections:
    def test_open_adds_connection(self):
        from ovos_messagebus import event_handler
        handler = _make_handler()
        handler.write_message = MagicMock()
        original_connections = list(event_handler.client_connections)
        try:
            event_handler.client_connections.clear()
            handler.open()
            assert handler in event_handler.client_connections
        finally:
            event_handler.client_connections.clear()
            event_handler.client_connections.extend(original_connections)

    def test_on_close_removes_connection(self):
        from ovos_messagebus import event_handler
        handler = _make_handler()
        handler.write_message = MagicMock()
        original_connections = list(event_handler.client_connections)
        try:
            event_handler.client_connections.clear()
            event_handler.client_connections.append(handler)
            handler.on_close()
            assert handler not in event_handler.client_connections
        finally:
            event_handler.client_connections.clear()
            event_handler.client_connections.extend(original_connections)


class TestOnMessage:
    """Tests for MessageBusEventHandler.on_message broadcast behaviour."""

    def _make_handler_with_clients(self):
        from ovos_messagebus import event_handler
        handler = _make_handler()
        handler.write_message = MagicMock()
        # Register handler as the only subscriber
        original = list(event_handler.client_connections)
        event_handler.client_connections.clear()
        event_handler.client_connections.append(handler)
        return handler, event_handler, original

    def test_filter_false_broadcasts_valid_message(self):
        handler, event_handler, original = self._make_handler_with_clients()
        try:
            ws_cfg = {"websocket": {"filter": False}}
            with patch("ovos_messagebus.event_handler.Configuration", return_value=ws_cfg):
                handler.on_message('{"type":"test","data":{},"context":{}}')
            handler.write_message.assert_called_once()
        finally:
            event_handler.client_connections.clear()
            event_handler.client_connections.extend(original)

    def test_filter_true_broadcasts_valid_message(self):
        handler, event_handler, original = self._make_handler_with_clients()
        try:
            ws_cfg = {"websocket": {"filter": True, "filter_logs": []}}
            with patch("ovos_messagebus.event_handler.Configuration", return_value=ws_cfg):
                with patch("ovos_messagebus.event_handler.Message") as msg_mock:
                    with patch("ovos_messagebus.event_handler.SessionManager"):
                        fake_msg = MagicMock()
                        fake_msg.msg_type = "test.type"
                        msg_mock.deserialize.return_value = fake_msg
                        handler.on_message('{"type":"test.type","data":{},"context":{}}')
            handler.write_message.assert_called_once()
        finally:
            event_handler.client_connections.clear()
            event_handler.client_connections.extend(original)

    def test_filter_true_broadcasts_malformed_json(self):
        """Malformed frames must still be broadcast even when filter=True."""
        handler, event_handler, original = self._make_handler_with_clients()
        try:
            ws_cfg = {"websocket": {"filter": True, "filter_logs": []}}
            with patch("ovos_messagebus.event_handler.Configuration", return_value=ws_cfg):
                handler.on_message("not-valid-json")
            handler.write_message.assert_called_once_with("not-valid-json")
        finally:
            event_handler.client_connections.clear()
            event_handler.client_connections.extend(original)

    def test_filter_true_broadcasts_non_ovos_dict(self):
        """JSON that parses but lacks OVOS fields must still be broadcast."""
        handler, event_handler, original = self._make_handler_with_clients()
        try:
            ws_cfg = {"websocket": {"filter": True, "filter_logs": []}}
            payload = '{"hello": "world"}'
            with patch("ovos_messagebus.event_handler.Configuration", return_value=ws_cfg):
                handler.on_message(payload)
            handler.write_message.assert_called_once_with(payload)
        finally:
            event_handler.client_connections.clear()
            event_handler.client_connections.extend(original)


class TestEmit:
    def test_emit_serializable_object(self):
        from ovos_bus_client.message import Message
        handler = _make_handler()
        handler.write_message = MagicMock()
        msg = Message("test.msg", {"key": "value"})
        handler.emit(msg)
        handler.write_message.assert_called_once_with(msg.serialize())

    def test_emit_plain_dict(self):
        handler = _make_handler()
        handler.write_message = MagicMock()
        data = {"type": "test", "data": {}}
        handler.emit(data)
        handler.write_message.assert_called_once_with(json.dumps(data))

    def test_check_origin_always_true(self):
        handler = _make_handler()
        assert handler.check_origin("http://any.origin") is True
        assert handler.check_origin("") is True
