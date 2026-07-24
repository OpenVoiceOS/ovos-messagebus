import unittest
from collections import namedtuple
from unittest.mock import patch, MagicMock

from ovos_messagebus.__main__ import _run_bus

FakeConfig = namedtuple('FakeConfig', ['host', 'port', 'route', 'ssl'])


class TestRunBusSSL(unittest.TestCase):
    def _patch_common(self):
        """Patch the asyncio/tornado plumbing that isn't under test."""
        return (
            patch('ovos_messagebus.__main__.asyncio.new_event_loop'),
            patch('ovos_messagebus.__main__.asyncio.set_event_loop'),
            patch('ovos_messagebus.__main__.ioloop'),
        )

    def test_plain_ws_no_ssl_options(self):
        """ssl: false -> listen() called with no ssl_options at all."""
        config = FakeConfig(host='0.0.0.0', port=8181, route='/core', ssl=False)
        p1, p2, p3 = self._patch_common()
        with p1, p2, p3, \
                patch('ovos_messagebus.__main__.web.Application') as mock_app:
            mock_application = MagicMock()
            mock_app.return_value = mock_application

            _run_bus(config)

            mock_application.listen.assert_called_once_with(
                config.port, config.host)
            args, kwargs = mock_application.listen.call_args
            self.assertNotIn('ssl_options', kwargs)

    def test_ssl_with_configured_cert(self):
        """ssl: true with configured cert/key -> those exact paths passed through."""
        config = FakeConfig(host='0.0.0.0', port=8181, route='/core', ssl=True)
        p1, p2, p3 = self._patch_common()
        with p1, p2, p3, \
                patch('ovos_messagebus.__main__.web.Application') as mock_app, \
                patch('ovos_messagebus.__main__.Configuration') as mock_conf:
            mock_conf.return_value = {
                'websocket': {'ssl_cert': '/etc/certs/mine.crt',
                              'ssl_key': '/etc/certs/mine.key'}
            }
            mock_application = MagicMock()
            mock_app.return_value = mock_application

            _run_bus(config)

            mock_application.listen.assert_called_once_with(
                config.port, config.host,
                ssl_options={"certfile": "/etc/certs/mine.crt",
                             "keyfile": "/etc/certs/mine.key"})

    def test_ssl_generates_self_signed_when_unconfigured(self):
        """ssl: true with nothing configured -> generation triggered, generated paths passed through."""
        config = FakeConfig(host='0.0.0.0', port=8181, route='/core', ssl=True)
        p1, p2, p3 = self._patch_common()
        with p1, p2, p3, \
                patch('ovos_messagebus.__main__.web.Application') as mock_app, \
                patch('ovos_messagebus.__main__.Configuration') as mock_conf, \
                patch('ovos_utils.security.create_self_signed_cert') as mock_gen:
            mock_conf.return_value = {'websocket': {}}
            mock_gen.return_value = ('/generated/ovos-messagebus.crt',
                                      '/generated/ovos-messagebus.key')
            mock_application = MagicMock()
            mock_app.return_value = mock_application

            _run_bus(config)

            mock_gen.assert_called_once()
            mock_application.listen.assert_called_once_with(
                config.port, config.host,
                ssl_options={"certfile": "/generated/ovos-messagebus.crt",
                             "keyfile": "/generated/ovos-messagebus.key"})

    def test_ssl_without_pyopenssl_raises_and_does_not_fall_back(self):
        """pyopenssl missing while ssl: true -> raises clearly, never falls back to plain ws."""
        config = FakeConfig(host='0.0.0.0', port=8181, route='/core', ssl=True)
        p1, p2, p3 = self._patch_common()
        with p1, p2, p3, \
                patch('ovos_messagebus.__main__.web.Application') as mock_app, \
                patch('ovos_messagebus.__main__.Configuration') as mock_conf, \
                patch('ovos_utils.security.create_self_signed_cert',
                      side_effect=ImportError):
            mock_conf.return_value = {'websocket': {}}
            mock_application = MagicMock()
            mock_app.return_value = mock_application

            with self.assertRaises(RuntimeError):
                _run_bus(config)

            mock_application.listen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
