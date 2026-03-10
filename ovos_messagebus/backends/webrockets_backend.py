"""Optional webrockets backend for ovos-messagebus.

Replaces the Tornado WebSocket server with a Rust-powered webrockets server
(https://github.com/ploMP4/webrockets) while keeping identical OVOS protocol
semantics: every message published by any client is broadcast to all clients.

Install the extra dependency::

    pip install "ovos-messagebus[webrockets]"

Run as a drop-in replacement::

    python -m ovos_messagebus.backends.webrockets_backend

Or call :func:`main` directly with the same lifecycle hooks as Tornado::

    from ovos_messagebus.backends.webrockets_backend import main
    main()

Architecture
------------
webrockets uses a room-based broadcast model.  All clients are placed in a
single room (``_GLOBAL_ROOM``) via the route's ``default_group`` so that
``conn.broadcast([_GLOBAL_ROOM], message)`` fans out to every subscriber —
equivalent to the explicit loop in
``ovos_messagebus.event_handler.MessageBusEventHandler.on_message``.

Backwards-compatibility matrix
-------------------------------
=========================  ===========  ===========
Feature                    Tornado      webrockets
=========================  ===========  ===========
Port / route               configurable configurable
Initial "connected" msg    ✓            ✓
Fan-out to all clients     ✓ (incl.     ✓ (incl.
(including sender)          sender)      sender)
Optional msg filtering     ✓            ✓
max_msg_size config        ✓            ✗ (not exposed in Python API)
SSL                        ✓            ✗ (not in v0.1.x)
Per-handler emitter (.on)  ✓            ✗ (Tornado-specific; not used externally)
=========================  ===========  ===========

Limitations
-----------
* ``max_msg_size`` is silently ignored; large messages are NOT capped.
* SSL termination must be handled by a reverse proxy (nginx/caddy) when using
  this backend.
* The internal ``MessageBusEventHandler.on()`` / ``emitter`` API is not
  replicated because it is only used by the Tornado server internally.
"""

from __future__ import annotations

import threading
import time

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager
from ovos_config import Configuration
from ovos_messagebus.load_config import load_message_bus_config
from ovos_utils import wait_for_exit_signal
from ovos_utils.log import LOG, init_service_logger
from ovos_utils.process_utils import reset_sigint_handler

try:
    from webrockets import WebsocketServer  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "webrockets is not installed.  "
        "Run: pip install 'ovos-messagebus[webrockets]'"
    ) from exc

# Single broadcast room — every client is placed here via `default_group` on
# create_route(), so conn.broadcast([_GLOBAL_ROOM], msg) reaches everyone.
_GLOBAL_ROOM: str = "__ovos_bus__"


def _build_server(config) -> WebsocketServer:  # noqa: ANN001
    """Construct and configure a :class:`WebsocketServer` matching *config*.

    Parameters
    ----------
    config:
        A ``MessageBusConfig`` namedtuple as returned by
        :func:`ovos_messagebus.load_config.load_message_bus_config`.
        Used fields: ``host``, ``port``, ``route``.

    Returns
    -------
    WebsocketServer
        Ready-to-start server with the OVOS fan-out route registered.

    Notes
    -----
    ``config.ssl`` and ``config.max_msg_size`` are **not** forwarded to
    webrockets — see module-level backwards-compatibility table.
    """
    ovos_cfg: dict = Configuration().get("websocket", {})
    filter_enabled: bool = ovos_cfg.get("filter", False)
    filter_logs: list = ovos_cfg.get(
        "filter_logs", ["gui.status.request", "gui.page.upload"]
    )

    if config.ssl:
        LOG.warning(
            "webrockets backend: SSL is configured in mycroft.conf but is NOT "
            "supported by webrockets v0.1.x.  Use a reverse proxy for TLS "
            "termination or switch to the Tornado backend."
        )

    server = WebsocketServer(host=config.host, port=config.port)

    # Normalise route path — webrockets expects no leading slash and no scheme.
    route_path = config.route.lstrip("/")

    # default_group auto-joins every new connection to _GLOBAL_ROOM, so the
    # @connect handler only needs to send the greeting.
    route = server.create_route(route_path, default_group=_GLOBAL_ROOM)

    @route.connect(when="after")  # type: ignore[arg-type]
    def _on_connect(conn) -> None:  # noqa: ANN001
        """Send the mandatory OVOS "connected" greeting."""
        greeting = Message(
            "connected",
            context={"session": {"session_id": "default"}},
        ).serialize()
        conn.send(greeting)
        LOG.debug("webrockets: client connected")

    @route.receive  # type: ignore[arg-type]
    def _on_message(conn, data: str) -> None:  # noqa: ANN001
        """Fan-out every incoming message to all connected clients.

        Mirrors :meth:`MessageBusEventHandler.on_message` — the raw JSON
        string is forwarded **unmodified**, including to the sender
        (``exclude_self=False``, which is the webrockets default).
        """
        if filter_enabled:
            try:
                msg = Message.deserialize(data)
                if msg.msg_type not in filter_logs:
                    LOG.debug(
                        msg.msg_type
                        + f' source: {msg.context.get("source", [])}'
                        + f' destination: {msg.context.get("destination", [])}\n'
                        + f'SESSION: {SessionManager.get(msg).serialize()}'
                    )
            except Exception:
                pass  # non-OVOS or malformed message — still broadcast it

        # Broadcast to the global room; exclude_self=False ensures the sender
        # also receives its own message, matching Tornado behaviour.
        conn.broadcast([_GLOBAL_ROOM], data, exclude_self=False)

    @route.disconnect  # type: ignore[arg-type]
    def _on_disconnect(conn, code=None, reason=None) -> None:  # noqa: ANN001
        LOG.debug(f"webrockets: client disconnected (code={code})")

    return server


def on_ready() -> None:
    LOG.info("Message bus service started! (webrockets backend)")


def on_error(e: str = "Unknown") -> None:
    LOG.info(f"Message bus failed to start ({e!r}) — webrockets backend")


def on_stopping() -> None:
    LOG.info("Message bus is shutting down... (webrockets backend)")


def main(
    ready_hook=on_ready,
    error_hook=on_error,
    stopping_hook=on_stopping,
) -> None:
    """Drop-in replacement for :func:`ovos_messagebus.__main__.main`.

    Accepts identical lifecycle hooks (``ready_hook``, ``error_hook``,
    ``stopping_hook``) so callers that inject custom hooks continue to work
    without modification.
    """
    reset_sigint_handler()
    init_service_logger("bus")
    LOG.info("Starting message bus service (webrockets backend)...")

    config = load_message_bus_config()

    try:
        server = _build_server(config)
    except Exception as exc:
        error_hook(str(exc))
        raise

    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    # Allow the Rust runtime a moment to bind the socket before advertising ready.
    time.sleep(0.3)
    ready_hook()
    wait_for_exit_signal()
    stopping_hook()


if __name__ == "__main__":
    main()
