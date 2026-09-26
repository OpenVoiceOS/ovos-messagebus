# Bus events

`ovos-messagebus` is a **pure fan-out broker**. It does not publish, filter, or transform any messages. It forwards every message from one client to every connected client, verbatim. This page documents the message types that flow through the bus in a standard OVOS deployment.

The bus itself recognizes only one special message type: `connected` (sent to a new client immediately after it opens a WebSocket connection). Every other message type is an application-level concern of the services that connect to the bus.

---

## `connected` (bus → new client only)

`MessageBusEventHandler.open()` sends this message to the newly connected client when the WebSocket handshake completes. The bus does not broadcast it to other clients.

```json
{
  "type": "connected",
  "data": {},
  "context": {"session": {"session_id": "default"}}
}
```

---

## Message categories (application-level)

The following categories are messages that flow through the bus. The OVOS services listed below publish and consume them. The bus itself does not.

### Core / intent pipeline

| Message type | Publisher | Consumers |
|---|---|---|
| `recognizer_loop:utterance` | `ovos-dinkum-listener` | `ovos-core` |
| `recognizer_loop:wakeword` | `ovos-dinkum-listener` | `ovos-gui`, skills |
| `recognizer_loop:record_begin` | `ovos-dinkum-listener` | GUI clients |
| `recognizer_loop:record_end` | `ovos-dinkum-listener` | GUI clients |
| `recognizer_loop:audio_output_start` | `ovos-audio` | GUI clients |
| `recognizer_loop:audio_output_end` | `ovos-audio` | GUI clients |
| `speak` | `ovos-core` (skills) | `ovos-audio` |
| `complete_intent_failure` | `ovos-core` | fallback skills |
| `ovos.utterance.handled` | `ovos-core` | GUI clients |
| `ovos.utterance.cancelled` | `ovos-core` | GUI clients |
| `mycroft.skill.handler.start` | `ovos-core` | GUI clients |
| `mycroft.skill.handler.complete` | `ovos-core` | GUI clients |

### GUI namespace protocol

| Message type | Publisher | Consumers |
|---|---|---|
| `mycroft.gui.connected` | GUI clients | `ovos-gui` |
| `gui.page.show` | `ovos-gui` | GUI clients |
| `mycroft.session.set` | `ovos-gui` | GUI clients |
| `mycroft.session.list.insert` | `ovos-gui` | GUI clients |
| `mycroft.session.list.remove` | `ovos-gui` | GUI clients |
| `mycroft.gui.list.insert` | `ovos-gui` | GUI clients |
| `mycroft.gui.list.move` | `ovos-gui` | GUI clients |
| `mycroft.gui.list.remove` | `ovos-gui` | GUI clients |
| `mycroft.events.triggered` | GUI clients | `ovos-gui`, skills |
| `gui.status.request` | GUI clients | `ovos-gui` |
| `mycroft.device.show.idle` | `ovos-core` | `ovos-shell`, GUI clients |
| `ovos.homescreen.displayed` | `ovos-skill-homescreen` | `ovos-gui` |

### Homescreen data (raspOVOS / legacy Qt plugin)

| Message type | Publisher | Consumers |
|---|---|---|
| `homescreen.data.time` | `HomescreenManager` (legacy-plugin) | `ovos-shell` QML |
| `homescreen.data.weather` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.data.wallpaper` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.data.notifications` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.data.apps` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.data.examples` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.data.connectivity` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.widget.timer` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.widget.alarm` | `HomescreenManager` | `ovos-shell` QML |
| `homescreen.widget.media` | `HomescreenManager` | `ovos-shell` QML |

### Audio / OCP

| Message type | Publisher | Consumers |
|---|---|---|
| `ovos.common_play.play` | skills | `ovos-audio` |
| `ovos.common_play.pause` | GUI clients, skills | `ovos-audio` |
| `ovos.common_play.track_info.response` | `ovos-audio` | GUI clients |
| `gui.player.media.service.sync.status` | `ovos-audio` | `HomescreenManager` |

### PHAL / system

| Message type | Publisher | Consumers |
|---|---|---|
| `mycroft.network.connected` | `ovos-PHAL` connectivity plugin | `HomescreenManager`, skills |
| `mycroft.internet.connected` | `ovos-PHAL` connectivity plugin | skills |
| `enclosure.notify.no_internet` | `ovos-PHAL` | skills |
| `system.reboot` | `ovos-PHAL-plugin-system` | OS signal handler |
| `system.shutdown` | `ovos-PHAL-plugin-system` | OS signal handler |
| `homescreen.wallpaper.set` | `ovos-PHAL-plugin-wallpaper-manager` | `HomescreenManager` |

---

## Filter / debug mode

When `mycroft.conf["websocket"]["filter"] = true`, the bus logs each message type and session info before it broadcasts the message:

```
DEBUG: <msg_type> source: [...] destination: [...]
       SESSION: {...}
```

The bus excludes message types listed in `filter_logs` from this log (default: `["gui.status.request", "gui.page.upload"]`).

Filter mode does **not** affect message delivery. The bus still broadcasts every message to every client, including malformed or non-OVOS frames that fail deserialization. It logs deserialization failures at DEBUG level and forwards the raw payload unchanged (`MessageBusEventHandler.on_message`, `event_handler.py:61`).

---

## Further reading

- [Server](server.md): `MessageBusEventHandler` implementation
- [Configuration](configuration.md): `filter`, `filter_logs`, and all connection settings
- [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client): client library used by all services

---
[← Configuration](configuration.md) · [Home](index.md) · [Backends & Benchmarks →](backends.md)
