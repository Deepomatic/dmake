ARG REPO
ARG BRANCH_NAME
ARG PYTHON_VERSION
ARG BUILD_ID

FROM ubuntu:16.04

ENV DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP 1
ENV DMAKE_DEBUG 1

RUN apt-get update && \
    apt-get install curl g++ python${PYTHON_VERSION} && \


RUN update-alternatives --install /usr/bin/python python /usr/bin/python${PYTHON_VERSION} 1

RUN curl https://bootstrap.pypa.io/get-pip.py | python
