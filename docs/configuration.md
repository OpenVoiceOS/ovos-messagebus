
# Configuration

`ovos-messagebus` reads all connection and behaviour settings from `mycroft.conf` under the `websocket` key. The config file is located at `~/.config/mycroft/mycroft.conf` (user) or `/etc/mycroft/mycroft.conf` (system).

---

## Full Reference

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

Defaults are sourced from `ovos_config/mycroft.conf` in the `ovos-config` package.

---

## Options

### `host`

**Type:** string
**Default:** `"127.0.0.1"` (per `ovos_config/mycroft.conf`)
**Source:** `load_config.py` → `MessageBusConfig`

The network interface the Tornado server binds to.

- `"127.0.0.1"` — loopback only (default; restricts to local process connections — all OVOS services run on the same host)
- `"0.0.0.0"` — accept connections from any interface (required when HiveMind satellites or remote services connect over the network)

All OVOS services that connect via `ovos-bus-client` read `host` from the same `mycroft.conf` to know where to connect.

---

### `port`

**Type:** integer
**Default:** `8181`
**Source:** `load_config.py` → `MessageBusConfig`

TCP port the WebSocket server listens on. The standard OVOS port is `8181`. The `ovos-gui` service uses a separate port (`18181` by default) for its own WebSocket.

---

### `route`

**Type:** string
**Default:** `"/core"`
**Source:** `load_config.py` → `MessageBusConfig`

The URL path that `MessageBusEventHandler` is mounted on. The full WebSocket URL becomes `ws://<host>:<port><route>`, e.g. `ws://localhost:8181/core`.

All `ovos-bus-client` connections use the same `route` value from config.

---

### `ssl`

**Type:** boolean
**Default:** `false`
**Source:** `load_config.py` → `MessageBusConfig` — read from `mycroft.conf["websocket"]["ssl"]` (`load_config.py:46`)

When `true`, the Tornado server starts with SSL/TLS enabled and serves `wss://` directly. When `false`, the server uses plain WebSocket (`ws://`).

---

### `ssl_cert` / `ssl_key`

**Type:** string (file path)
**Default:** unset
**Source:** `__main__.py::_get_ssl_options()` — read from `mycroft.conf["websocket"]["ssl_cert"]` / `["ssl_key"]`

Paths to a PEM certificate and private key used for the Tornado server's TLS listener when `ssl` is `true`. If left unset, a self-signed certificate/key pair is generated automatically (via `ovos_messagebus/ssl_utils.py`, RSA-2048/SHA-256) and cached under the XDG data directory; this requires the `cryptography` package (the `ssl` extra: `pip install "ovos-messagebus[ssl]"`).

The webrockets backend does not terminate TLS itself — it has no cert/key parameters to set. To serve `wss://` use the Tornado backend, or put a TLS-terminating reverse proxy in front of the webrockets backend instead.

---

### `max_msg_size`

**Type:** integer (megabytes)
**Default:** `10`
**Source:** `event_handler.py` → `MessageBusEventHandler.max_message_size`

Maximum WebSocket frame size in megabytes. Computed as:

```python
config.get("websocket", {}).get("max_msg_size", 25) * 1024 * 1024
```

Default per `ovos_config/mycroft.conf`: `25` MB. Messages larger than this limit cause Tornado to close the connection. Increase this value if you are passing large payloads (e.g. base64-encoded images via `gui.page.upload`).

---

### `filter`

**Type:** boolean
**Default:** `false`
**Source:** `event_handler.py` → `MessageBusEventHandler.filter`

When `true`, enables debug logging of all message types before broadcast. Each message logs its type, source list, destination list, and the current session state.

Messages listed in `filter_logs` are excluded from this log to reduce noise.

Enabling `filter` does **not** affect message delivery.

---

### `filter_logs`

**Type:** list of strings
**Default:** `["gui.status.request", "gui.page.upload"]`
**Source:** `event_handler.py` → `MessageBusEventHandler.filter_logs`

When `filter` is `true`, message types in this list are not logged. The default excludes high-frequency GUI polling messages that would flood the log.

Only has an effect when `filter: true`.

---

## `load_message_bus_config()` Override

The `load_message_bus_config()` function accepts keyword arguments that override values read from `mycroft.conf`. This is used internally by the `main()` entry point to apply command-line arguments:

```python
from ovos_messagebus.load_config import load_message_bus_config

# Use port 8182 regardless of config file
config = load_message_bus_config(port=8182)
```

---

## Further Reading

- [Server](server.md) — `MessageBusEventHandler`, `load_message_bus_config()`, `main()`
- [Events](events.md) — Message types that flow through the bus
- [ovos-config](https://github.com/OpenVoiceOS/ovos-config) — `mycroft.conf` location and loading
