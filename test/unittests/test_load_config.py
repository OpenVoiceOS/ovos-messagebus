import unittest
from unittest.mock import patch

from ovos_messagebus.load_config import load_message_bus_config


class TestLoadMessageBusConfig(unittest.TestCase):
    @patch('ovos_messagebus.load_config.Configuration')
    def test_ssl_is_read_from_websocket_section(self, mock_configuration):
        """websocket.ssl must be honoured, not the top-level 'ssl' key."""
        mock_configuration.return_value = {
            'websocket': {
                'host': '0.0.0.0',
                'port': 8181,
                'route': '/core',
                'ssl': True
            },
            'ssl': False  # top-level decoy value, must NOT be used
        }

        config = load_message_bus_config()

        self.assertEqual(config.host, '0.0.0.0')
        self.assertEqual(config.port, 8181)
        self.assertEqual(config.route, '/core')
        self.assertTrue(config.ssl)

    @patch('ovos_messagebus.load_config.Configuration')
    def test_ssl_defaults_to_falsy_when_absent(self, mock_configuration):
        mock_configuration.return_value = {
            'websocket': {
                'host': '0.0.0.0',
                'port': 8181,
                'route': '/core'
            }
        }

        config = load_message_bus_config()

        self.assertFalse(config.ssl)

    @patch('ovos_messagebus.load_config.Configuration')
    def test_override_takes_precedence_over_websocket_ssl(self, mock_configuration):
        mock_configuration.return_value = {
            'websocket': {
                'host': '0.0.0.0',
                'port': 8181,
                'route': '/core',
                'ssl': False
            }
        }

        config = load_message_bus_config(ssl=True)

        self.assertTrue(config.ssl)


if __name__ == '__main__':
    unittest.main()
