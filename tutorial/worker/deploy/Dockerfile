ARG BASE_IMAGE
FROM ${BASE_IMAGE} as builder

ARG WORKDIR
WORKDIR ${WORKDIR}

COPY . .

RUN make -j$(nproc) install prefix=/usr/local/worker
ARG BUILD_HOSTNAME
RUN echo build hostname: ${BUILD_HOSTNAME}


FROM ${BASE_IMAGE} as runtime

WORKDIR /app/tutorial/worker

COPY --from=builder /usr/local/worker .

CMD ["deploy/start.sh"]
ENTRYPOINT ["/app/tutorial/worker/deploy/entrypoint.sh"]
