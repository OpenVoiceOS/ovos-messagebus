# Configuration

`ovos-messagebus` reads all connection and behavior settings from `mycroft.conf` under the `websocket` key. The config file lives at `~/.config/mycroft/mycroft.conf` (user) or `/etc/mycroft/mycroft.conf` (system).

---

## Full reference

```json
{
  "websocket": {
    "host": "127.0.0.1",
    "port": 8181,
    "route": "/core",
    "ssl": false,
    "ssl_cert": "",
    "ssl_key": "",
    "max_msg_size": 25,
    "filter": false,
    "filter_logs": ["gui.status.request", "gui.page.upload"]
  }
}
```

The defaults come from `ovos_config/mycroft.conf` in the `ovos-config` package.

---

## Options

### `host`

**Type:** string
**Default:** `"127.0.0.1"` (per `ovos_config/mycroft.conf`)
**Source:** `load_config.py` → `MessageBusConfig`

The network interface the Tornado server binds to.

- `"127.0.0.1"`: loopback only. This is the default. It restricts connections to the local host, since all OVOS services run on the same host.
- `"0.0.0.0"`: accepts connections from any interface. Use this when HiveMind satellites or remote services connect over the network.

Every OVOS service that connects through `ovos-bus-client` reads `host` from the same `mycroft.conf` to find the bus.

---

### `port`

**Type:** integer
**Default:** `8181`
**Source:** `load_config.py` → `MessageBusConfig`

The TCP port the WebSocket server listens on. The standard OVOS port is `8181`. `ovos-gui` uses a separate port (`18181` by default) for its own WebSocket.

---

### `route`

**Type:** string
**Default:** `"/core"`
**Source:** `load_config.py` → `MessageBusConfig`

The URL path `MessageBusEventHandler` mounts on. The full WebSocket URL becomes `ws://<host>:<port><route>`, for example `ws://localhost:8181/core`.

Every `ovos-bus-client` connection uses the same `route` value from config.

---

### `ssl`

**Type:** boolean
**Default:** `false`
**Source:** `load_config.py` → `MessageBusConfig`, read from `mycroft.conf["websocket"]["ssl"]` (`load_config.py:46`)

When `true`, the Tornado server starts with SSL/TLS enabled and serves `wss://` directly. When `false`, the server uses plain WebSocket (`ws://`).

---

### `ssl_cert` / `ssl_key`

**Type:** string (file path)
**Default:** unset
**Source:** `__main__.py::_get_ssl_options()`, read from `mycroft.conf["websocket"]["ssl_cert"]` / `["ssl_key"]`

Paths to a PEM certificate and private key the Tornado server uses for its TLS listener when `ssl` is `true`. If you leave them unset, the server generates a self-signed certificate and key pair automatically (through `ovos_messagebus/ssl_utils.py`, RSA-2048/SHA-256) and caches the pair under the XDG data directory. This requires the `cryptography` package (the `ssl` extra: `pip install "ovos-messagebus[ssl]"`).

The webrockets backend does not terminate TLS itself. It has no cert or key parameters to set. To serve `wss://`, use the Tornado backend, or put a TLS-terminating reverse proxy in front of the webrockets backend instead.

---

### `max_msg_size`

**Type:** integer (megabytes)
**Default:** `10`
**Source:** `event_handler.py` → `MessageBusEventHandler.max_message_size`

The maximum WebSocket frame size in megabytes. The server computes it as:

```python
config.get("websocket", {}).get("max_msg_size", 25) * 1024 * 1024
```

Default per `ovos_config/mycroft.conf`: `25` MB. Messages larger than this limit cause Tornado to close the connection. Increase this value if you pass large payloads (for example base64-encoded images through `gui.page.upload`).

---

### `filter`

**Type:** boolean
**Default:** `false`
**Source:** `event_handler.py` → `MessageBusEventHandler.filter`

When `true`, the server enables debug logging of all message types before it broadcasts them. Each log entry shows the message type, source list, destination list, and the current session state.

Message types listed in `filter_logs` are excluded from this log to reduce noise.

Enabling `filter` does **not** affect message delivery.

---

### `filter_logs`

**Type:** list of strings
**Default:** `["gui.status.request", "gui.page.upload"]`
**Source:** `event_handler.py` → `MessageBusEventHandler.filter_logs`

When `filter` is `true`, the server does not log message types in this list. The default excludes high-frequency GUI polling messages that would flood the log.

This setting only has an effect when `filter: true`.

---

## `load_message_bus_config()` override

`load_message_bus_config()` accepts keyword arguments that override values read from `mycroft.conf`. The `main()` entry point uses this internally to apply command-line arguments:

```python
from ovos_messagebus.load_config import load_message_bus_config

# Use port 8182 regardless of config file
config = load_message_bus_config(port=8182)
```

---

## Further reading

- [Server](server.md): `MessageBusEventHandler`, `load_message_bus_config()`, `main()`
- [Events](events.md): message types that flow through the bus
- [ovos-config](https://github.com/OpenVoiceOS/ovos-config): `mycroft.conf` location and loading

---
[← Server](server.md) · [Home](index.md) · [Events →](events.md)
