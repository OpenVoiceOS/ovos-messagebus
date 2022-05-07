FROM ghcr.io/openvoiceos/core:dev

COPY . /tmp/ovos-bus
RUN pip3 install /tmp/ovos-bus

USER mycroft
ENTRYPOINT mycroft-messagebus