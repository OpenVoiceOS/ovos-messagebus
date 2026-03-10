
# Server

## `MessageBusEventHandler`

**Module:** `ovos_messagebus.event_handler.MessageBusEventHandler`

Tornado `WebSocketHandler` subclass that implements the OVOS message bus. All connected clients share a single module-level connection list (`client_connections` in `event_handler.py:27`); every received message is broadcast to every client.

---

### Module Attributes

| Attribute | Type | Description |
|---|---|---|
| `client_connections` | `list` | Module-level list of all open `MessageBusEventHandler` instances |

---

### Key Methods

#### `open()`

Called when a new WebSocket connection is established. Writes a `connected` message (with `context.session.session_id = "default"`) to the new client only, then appends `self` to the module-level `client_connections` list.

#### `on_message(message)`

Called for each incoming WebSocket frame. Broadcasts the raw message string to **all** connections in `client_connections` (including the sender) by calling `write_message()` on each.

When `self.filter` is `True` (read from `mycroft.conf["websocket"]["filter"]`), the message is first deserialized and its type, source, destination, and session are logged — unless the type is in `filter_logs`. If deserialization fails the failure is logged at DEBUG level and the raw frame is still broadcast unchanged. This is used for debug monitoring and does **not** affect delivery.

#### `on_close()`

Removes the handler from `client_connections` when the connection drops.

#### `check_origin(origin) → bool`

Always returns `True`. OVOS does not enforce CORS/origin checks — any WebSocket client can connect.

#### `max_message_size` (property)

Returns the configured maximum WebSocket message size in bytes:

```python
config.get("websocket", {}).get("max_msg_size", 10) * 1024 * 1024
```

Default: 10 MB.

---

### Broadcast Behaviour

The bus is a pure fan-out: no routing, no filtering, no topic subscriptions at the server level. Every message every client sends is forwarded to every client. Subscription filtering is handled entirely in the client library (`ovos-bus-client`).

---

## `load_message_bus_config()`

**Module:** `ovos_messagebus.load_config`

```python
from ovos_messagebus.load_config import load_message_bus_config

config = load_message_bus_config()
# config.host, config.port, config.route, config.ssl
```

Reads `mycroft.conf["websocket"]` and returns a `MessageBusConfig` namedtuple:

| Field | Source key | Default |
|---|---|---|
| `host` | `host` | `0.0.0.0` |
| `port` | `port` | `8181` |
| `route` | `route` | `/core` |
| `ssl` | `ssl` | `False` |

Keyword arguments passed to `load_message_bus_config()` override values from config:

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

1. Call `load_message_bus_config()` to get host/port/route/ssl settings
2. Build a Tornado `web.Application` mapping `config.route` → `MessageBusEventHandler`
3. Bind the application to `config.port` / `config.host`
4. Start the Tornado `IOLoop` in a **daemon thread**
5. Block the main thread on `wait_for_exit_signal()` (from `ovos-utils`)
6. On signal (SIGTERM/SIGINT), the daemon thread exits with the process

The daemon thread design means the IOLoop is automatically terminated when the main thread receives a shutdown signal — no explicit cleanup is required.
