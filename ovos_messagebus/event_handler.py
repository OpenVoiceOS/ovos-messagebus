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

from ovos_utils.fakebus import Message
from ovos_utils.log import LOG
from ovos_config import Configuration
from pyee import EventEmitter
from tornado.websocket import WebSocketHandler
from ovos_bus_client.session import SessionManager

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

    def on_message(self, message):
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
                return

            if deserialized_message.msg_type not in self.filter_logs:
                LOG.debug(deserialized_message.msg_type +
                        f' source: {deserialized_message.context.get("source", [])}' +
                        f' destination: {deserialized_message.context.get("destination", [])}\n'
                        f'SESSION: {SessionManager.get(deserialized_message).serialize()}')

            try:
                self.emitter.emit(deserialized_message.msg_type,
                                deserialized_message)
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
