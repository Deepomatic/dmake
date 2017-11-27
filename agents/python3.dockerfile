FROM python:3.6

ENV DMAKE_DIR /usr/local/lib/python3.6/site-packages/dmake
ENV DMAKE_CONFIG_DIR /etc/dmake

COPY dmake ${DMAKE_DIR}
COPY requirements.txt ${DMAKE_DIR}/
COPY install.sh       ${DMAKE_CONFIG_DIR}/

RUN pip3 install -r ${DMAKE_DIR}/requirements.txt
RUN ${DMAKE_CONFIG_DIR}/install.sh

ENV PATH ${DMAKE_DIR}:${DMAKE_DIR}/utils:${PATH}
