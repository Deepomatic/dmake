ARG BASE_IMAGE
FROM ${BASE_IMAGE} as builder

ARG WORKDIR
WORKDIR ${WORKDIR}

COPY ./worker .
COPY ./web /web

RUN make -j$(nproc) install prefix=/usr/local/worker
ARG BUILD_HOSTNAME
RUN echo build hostname: ${BUILD_HOSTNAME}


FROM ${BASE_IMAGE} as runtime

WORKDIR /app/test/worker

COPY --from=builder /usr/local/worker .
COPY --from=builder /web/requirements.txt /web-requirements.txt

CMD ["deploy/start.sh"]
ENTRYPOINT ["/app/test/worker/deploy/entrypoint.sh"]
