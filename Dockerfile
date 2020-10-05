FROM python:3.8-alpine

ENV LANG=en_US.utf8

COPY poetry.lock .
COPY pyproject.toml .

RUN apk --no-cache --update add util-linux lvm2 udev gcc libffi-dev musl-dev openssl-dev \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install -n --no-dev \
    && mkdir -p /mnt/inspect \
    && apk --no-cache del gcc libffi-dev musl-dev openssl-dev

WORKDIR /opt/houndigrade
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
