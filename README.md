# OVOS MessageBus

messagebus service, the nervous system of OpenVoiceOS

## Alternative implementations

- [OVOS Bus Server](https://github.com/OpenVoiceOS/ovos-bus-server/) - Alternative C++ messagebus server implementation using WebSocket++


# Configuration

under mycroft.conf

```javascript
{
  // The mycroft-core messagebus websocket
  "websocket": {
    "host": "0.0.0.0",
    "port": 8181,
    "route": "/core",
    "ssl": false,
    // in mycroft-core all skills share a bus, this allows malicious skills
    // to manipulate it and affect other skills, this option ensures each skill
    // gets its own websocket connection
    "shared_connection": true,
    // filter out messages of certain types
    "filter": false,
    // which messages to filter if filter is enabled
    "filter_ogs": ["gui.status.request", "gui.page.upload"]
  }
}
```