FROM python:2

COPY deepomatic/dmake /dmake
ENV PYTHONPATH /dmake
ENV PATH /dmake:/dmake/utils:${PATH}
