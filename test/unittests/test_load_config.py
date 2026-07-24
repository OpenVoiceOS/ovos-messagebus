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
"""Unit tests for ovos_messagebus.load_config."""
import pytest
from unittest.mock import patch, MagicMock


VALID_WS_CONFIG = {
    "websocket": {
        "host": "127.0.0.1",
        "port": 8181,
        "route": "/core",
        "ssl": False,
    },
}


def _make_config(data):
    cfg = MagicMock()
    cfg.__getitem__.side_effect = data.__getitem__
    cfg.get.side_effect = data.get
    return cfg


class TestLoadMessageBusConfig:
    def test_returns_named_tuple_with_correct_fields(self):
        from ovos_messagebus.load_config import load_message_bus_config
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(VALID_WS_CONFIG)):
            result = load_message_bus_config()

        assert result.host == "127.0.0.1"
        assert result.port == 8181
        assert result.route == "/core"
        assert result.ssl is False

    def test_overrides_take_precedence_over_config(self):
        from ovos_messagebus.load_config import load_message_bus_config
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(VALID_WS_CONFIG)):
            result = load_message_bus_config(host="127.0.0.1", port=9999)

        assert result.host == "127.0.0.1"
        assert result.port == 9999
        assert result.route == "/core"  # unchanged

    def test_raises_key_error_when_websocket_section_missing(self):
        from ovos_messagebus.load_config import load_message_bus_config
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config({})):
            with pytest.raises(KeyError):
                load_message_bus_config()

    def test_raises_value_error_when_required_field_missing(self):
        from ovos_messagebus.load_config import load_message_bus_config
        incomplete = {
            "websocket": {"host": "0.0.0.0"},  # missing port and route
            "ssl": False,
        }
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(incomplete)):
            with pytest.raises(ValueError, match="Missing one or more websocket configs"):
                load_message_bus_config()

    def test_named_tuple_fields(self):
        from ovos_messagebus.load_config import MessageBusConfig
        assert set(MessageBusConfig._fields) == {"host", "port", "route", "ssl"}

    def test_ssl_override_false_takes_precedence_over_true_config(self):
        """ssl=False override must win even when config has ssl=True."""
        from ovos_messagebus.load_config import load_message_bus_config
        cfg_with_ssl = {
            "websocket": {**VALID_WS_CONFIG["websocket"], "ssl": True},
        }
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(cfg_with_ssl)):
            result = load_message_bus_config(ssl=False)
        assert result.ssl is False

    def test_ssl_override_true_takes_precedence_over_false_config(self):
        """ssl=True override must win when config has ssl=False."""
        from ovos_messagebus.load_config import load_message_bus_config
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(VALID_WS_CONFIG)):
            result = load_message_bus_config(ssl=True)
        assert result.ssl is True

    def test_ssl_falls_back_to_websocket_config_when_not_overridden(self):
        """When ssl is not in overrides, value comes from websocket config key."""
        from ovos_messagebus.load_config import load_message_bus_config
        cfg_ssl_true = {
            "websocket": {**VALID_WS_CONFIG["websocket"], "ssl": True},
        }
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(cfg_ssl_true)):
            result = load_message_bus_config()
        assert result.ssl is True

    def test_ssl_is_read_from_websocket_section_not_top_level(self):
        """websocket.ssl must be honoured, not a top-level 'ssl' key."""
        from ovos_messagebus.load_config import load_message_bus_config
        cfg = {
            "websocket": {**VALID_WS_CONFIG["websocket"], "ssl": True},
            "ssl": False,  # top-level decoy value, must NOT be used
        }
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(cfg)):
            result = load_message_bus_config()
        assert result.ssl is True

    def test_ssl_defaults_to_falsy_when_absent(self):
        """When ssl is absent from both overrides and config, it defaults falsy."""
        from ovos_messagebus.load_config import load_message_bus_config
        cfg = {
            "websocket": {
                "host": "0.0.0.0",
                "port": 8181,
                "route": "/core",
            },
        }
        with patch("ovos_messagebus.load_config.Configuration",
                   return_value=_make_config(cfg)):
            result = load_message_bus_config()
        assert not result.ssl
