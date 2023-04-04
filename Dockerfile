FROM ghcr.io/openvoiceos/core:dev

COPY . /tmp/ovos-messagebus
RUN pip3 install /tmp/ovos-messagebus

USER mycroft
ENTRYPOINT ovos-messagebus