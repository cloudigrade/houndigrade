FROM fedora:31

ENV LANG=en_US.utf8

COPY poetry.lock .
COPY pyproject.toml .

RUN dnf update -y \
    && dnf install which python3-pip -y \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.7 /usr/bin/pip ; fi \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.7 /usr/bin/python; fi \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install -n --no-dev \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && mkdir -p /mnt/inspect

WORKDIR /opt/houndigrade
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
