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
"""Define the web socket event handler for the message bus."""
import json
import sys
import traceback

from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager
from ovos_config import Configuration
from ovos_utils.log import LOG
from pyee import EventEmitter
from tornado.websocket import WebSocketHandler

client_connections = []


class MessageBusEventHandler(WebSocketHandler):
    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)
        self.emitter = EventEmitter()

    def on(self, event_name, handler):
        self.emitter.on(event_name, handler)

    @property
    def filter(self) -> bool:
        return Configuration().get("websocket", {}).get("filter", False)

    @property
    def filter_logs(self) -> list:
        return Configuration().get("websocket", {}).get("filter_logs", ["gui.status.request", "gui.page.upload"])

    @property
    def max_message_size(self) -> int:
        return Configuration().get("websocket", {}).get("max_msg_size", 10) * 1024 * 1024

    def _reject_malformed_carrier(self, message: str) -> bool:
        """Drop `message` and broadcast `ovos.session.rejected` if its
        `context.session` is present but not a JSON object (OVOS-SESSION-1
        §2.5). Returns True if the message was rejected (caller must not
        relay it)."""
        try:
            parsed = json.loads(message)
        except Exception:
            return False
        context = parsed.get("context")
        if not isinstance(context, dict):
            return False
        if "session" not in context or context["session"] is None or \
                isinstance(context["session"], dict):
            return False

        msg_type = parsed.get("type")
        LOG.warning(f"dropping message with malformed session carrier: {msg_type}")
        rejection_context = {}
        if context.get("utterance_id"):
            rejection_context["utterance_id"] = context["utterance_id"]
        rejection = Message("ovos.session.rejected",
                             data={"msg_type": msg_type, "reason": "malformed_carrier"},
                             context=rejection_context).serialize()
        for client in client_connections:
            client.write_message(rejection)
        return True

    def on_message(self, message):
        if self._reject_malformed_carrier(message):
            return
        if not self.filter:
            try:
                self.emitter.emit(message)
            except Exception as e:
                LOG.exception(e)
                traceback.print_exc(file=sys.stdout)
                pass
        else:
            try:
                deserialized_message = Message.deserialize(message)
            except Exception:
                LOG.debug("MessageBusEventHandler: failed to deserialize message for filtering")
                deserialized_message = None

            if deserialized_message is not None and deserialized_message.msg_type not in self.filter_logs:
                LOG.debug(deserialized_message.msg_type +
                          f' source: {deserialized_message.context.get("source", [])}' +
                          f' destination: {deserialized_message.context.get("destination", [])}\n'
                          f'SESSION: {SessionManager.get(deserialized_message).serialize()}')

            try:
                if deserialized_message is not None:
                    self.emitter.emit(deserialized_message.msg_type, deserialized_message)
            except Exception as e:
                LOG.exception(e)
                traceback.print_exc(file=sys.stdout)
                pass

        for client in client_connections:
            client.write_message(message)

    def open(self):
        self.write_message(Message("connected",
                                   context={"session": {"session_id": "default"}}).serialize())
        client_connections.append(self)

    def on_close(self):
        client_connections.remove(self)

    def emit(self, channel_message):
        if (hasattr(channel_message, 'serialize') and
                callable(getattr(channel_message, 'serialize'))):
            self.write_message(channel_message.serialize())
        else:
            self.write_message(json.dumps(channel_message))

    def check_origin(self, origin):
        return True
