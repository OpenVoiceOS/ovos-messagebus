# Server

## `MessageBusEventHandler`

**Module:** `ovos_messagebus.event_handler.MessageBusEventHandler`

`MessageBusEventHandler` is a Tornado `WebSocketHandler` subclass that implements the OVOS message bus. All connected clients share a single module-level connection list (`client_connections` in `event_handler.py:27`). The handler broadcasts every received message to every client.

---

### Module attributes

| Attribute | Type | Description |
|---|---|---|
| `client_connections` | `list` | Module-level list of all open `MessageBusEventHandler` instances |

---

### Key methods

#### `open()`

Tornado calls `open()` when a new WebSocket connection opens. The method writes a `connected` message (with `context.session.session_id = "default"`) to the new client only, then appends `self` to the module-level `client_connections` list.

#### `on_message(message)`

Tornado calls `on_message()` for each incoming WebSocket frame. The handler broadcasts the raw message string to **all** connections in `client_connections` (including the sender) by calling `write_message()` on each.

When `self.filter` is `True` (read from `mycroft.conf["websocket"]["filter"]`), the handler deserializes the message first and logs its type, source, destination, and session, unless the type is in `filter_logs`. If deserialization fails, the handler logs the failure at DEBUG level and still broadcasts the raw frame unchanged. This filter mode supports debug monitoring only. It does not affect delivery.

#### `on_close()`

Removes the handler from `client_connections` when the connection drops.

#### `check_origin(origin) → bool`

Always returns `True`. OVOS does not enforce CORS or origin checks. Any WebSocket client can connect.

#### `max_message_size` (property)

Returns the configured maximum WebSocket message size in bytes:

```python
config.get("websocket", {}).get("max_msg_size", 10) * 1024 * 1024
```

Default: 10 MB.

---

### Broadcast behavior

The bus is a pure fan-out. It does no routing, no filtering, and no topic subscriptions at the server level. The bus forwards every message from every client to every client. Subscription filtering happens entirely in the client library (`ovos-bus-client`).

---

## `load_message_bus_config()`

**Module:** `ovos_messagebus.load_config`

```python
from ovos_messagebus.load_config import load_message_bus_config

config = load_message_bus_config()
# config.host, config.port, config.route, config.ssl
```

`load_message_bus_config()` reads `mycroft.conf["websocket"]` and returns a `MessageBusConfig` namedtuple:

| Field | Source key | Default |
|---|---|---|
| `host` | `host` | `0.0.0.0` |
| `port` | `port` | `8181` |
| `route` | `route` | `/core` |
| `ssl` | `ssl` | `False` |

Keyword arguments passed to `load_message_bus_config()` override values from the config file:

```python
config = load_message_bus_config(port=8182)
```

---

## `main()`

**Module:** `ovos_messagebus.__main__`

Entry point for the bus server process.

```python
from ovos_messagebus.__main__ import main

main()
```

Execution flow:

1. Call `load_message_bus_config()` to get the host, port, route, and ssl settings.
2. Build a Tornado `web.Application` that maps `config.route` to `MessageBusEventHandler`.
3. If `config.ssl` is truthy, resolve `ssl_options` from `websocket.ssl_cert` and `websocket.ssl_key`
   (generating and caching a self-signed certificate under the XDG data directory when unset),
   then bind the application to `config.port` and `config.host` with those `ssl_options`, serving
   `wss://`. Otherwise bind it plainly, serving `ws://`.
4. Start the Tornado `IOLoop` in a **daemon thread**.
5. Block the main thread on `wait_for_exit_signal()` (from `ovos-utils`).
6. On signal (SIGTERM or SIGINT), the daemon thread exits with the process.

Because the IOLoop runs in a daemon thread, it terminates automatically when the main thread receives a shutdown signal. No explicit cleanup step is needed.

---
[Home](index.md) · [Configuration →](configuration.md)
