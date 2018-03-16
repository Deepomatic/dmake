FROM ubuntu:16.04

ARG REPO
ARG BRANCH_NAME
ARG PYTHON_VERSION
ARG BUILD_ID

ENV DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP 1
ENV DMAKE_DEBUG 1

RUN apt-get update && \
    apt-get --no-install-recommends -y install \
        apt-transport-https \
        ca-certificates \
        curl \
        g++ \
        python${PYTHON_VERSION} \
    && \
    rm -rf /var/lib/apt/lists/*


RUN update-alternatives --install /usr/bin/python python /usr/bin/python${PYTHON_VERSION} 1

RUN curl https://bootstrap.pypa.io/get-pip.py | python
