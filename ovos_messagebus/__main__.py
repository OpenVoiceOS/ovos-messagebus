# Copyright 2017 Mycroft AI Inc.
#
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
#
""" Message bus service for mycroft-core

The message bus facilitates inter-process communication between mycroft-core
processes. It implements a websocket server so can also be used by external
systems to integrate with the Mycroft system.
"""

import asyncio
import os

from ovos_config.config import Configuration
from ovos_utils import create_daemon, wait_for_exit_signal
from ovos_messagebus.load_config import load_message_bus_config
from ovos_utils.log import LOG, init_service_logger
from ovos_utils.process_utils import reset_sigint_handler
from ovos_utils.xdg_utils import xdg_data_home
from tornado import web, ioloop

from ovos_messagebus.event_handler import MessageBusEventHandler


def on_ready():
    LOG.info('Message bus service started!')


def on_error(e='Unknown'):
    LOG.info('Message bus failed to start ({})'.format(repr(e)))


def on_stopping():
    LOG.info('Message bus is shutting down...')


def _missing_cryptography_error(e: ImportError) -> RuntimeError:
    """Build the RuntimeError raised when a self-signed cert must be
    generated but 'cryptography' (the 'ssl' extra) isn't installed."""
    return RuntimeError(
        "websocket.ssl is enabled but no ssl_cert/ssl_key are "
        "configured and 'cryptography' is not installed to generate a "
        "self-signed certificate. Install it with "
        "'pip install \"ovos-messagebus[ssl]\"' or configure "
        "websocket.ssl_cert/websocket.ssl_key explicitly."
    )


def _get_ssl_options():
    """Determine the certificate/key pair to serve wss:// with.

    Looks for explicit `websocket.ssl_cert` / `websocket.ssl_key` paths in
    the configuration. If either is missing, a self-signed pair is
    generated (or reused, if already present) under XDG_DATA_HOME so it
    survives restarts.

    Raises RuntimeError if `cryptography` (the `ssl` extra) is required
    (i.e. a cert must be generated) but not installed - it never silently
    falls back to plain ws://.
    """
    websocket_config = Configuration().get('websocket', {})
    cert_file = websocket_config.get('ssl_cert')
    key_file = websocket_config.get('ssl_key')

    if cert_file and key_file:
        LOG.info(f'Serving wss:// with configured certificate: {cert_file}')
        return {"certfile": cert_file, "keyfile": key_file}

    try:
        from ovos_messagebus.ssl_utils import create_self_signed_cert
    except ImportError as e:
        raise _missing_cryptography_error(e) from e

    cert_dir = os.path.join(str(xdg_data_home()), "OpenVoiceOS",
                             "ovos-messagebus", "certs")
    try:
        cert_file, key_file = create_self_signed_cert(cert_dir,
                                                        name="ovos-messagebus")
    except ImportError as e:
        raise _missing_cryptography_error(e) from e
    LOG.info(f'Serving wss:// with self-signed certificate: {cert_file}')
    return {"certfile": cert_file, "keyfile": key_file}


def _run_bus(config):
    # Create and set an explicit asyncio event loop for this thread. tornado's
    # IOLoop relies on there being a current asyncio loop, and asyncio no
    # longer creates one implicitly via get_event_loop() on newer versions.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    routes = [(config.route, MessageBusEventHandler)]
    application = web.Application(routes)
    if config.ssl:
        ssl_options = _get_ssl_options()
        application.listen(config.port, config.host, ssl_options=ssl_options)
    else:
        application.listen(config.port, config.host)
    ioloop.IOLoop.current().start()


def main(ready_hook=on_ready, error_hook=on_error, stopping_hook=on_stopping):
    reset_sigint_handler()
    init_service_logger("bus")
    LOG.info('Starting message bus service...')
    config = load_message_bus_config()
    create_daemon(_run_bus, args=(config,))
    ready_hook()
    wait_for_exit_signal()
    stopping_hook()


if __name__ == "__main__":
    main()
