ARG BASE_IMAGE
FROM ${BASE_IMAGE}

RUN apt-get -y update && apt-get install -y --no-install-recommends \
            curl \
    && rm -rf /var/lib/apt/lists/*
