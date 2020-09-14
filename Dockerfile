FROM registry.access.redhat.com/ubi8/ubi-minimal:8.2

ENV LANG=en_US.utf8

COPY poetry.lock .
COPY pyproject.toml .

RUN microdnf update \
    && microdnf install util-linux which python38-pip lvm2 udev \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.8 /usr/bin/pip ; fi \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.8 /usr/bin/python; fi \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install -n --no-dev \
    && microdnf clean all \
    && mkdir -p /mnt/inspect

WORKDIR /opt/houndigrade
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
