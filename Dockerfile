FROM python:3.8-alpine as builder

ENV LANG=en_US.utf8

WORKDIR /opt/houndigrade

COPY poetry.lock .
COPY pyproject.toml .

RUN apk --no-cache --update add util-linux lvm2 udev gcc libffi-dev musl-dev openssl-dev cargo \
    && pip install -U pip \
    && pip install poetry \
    && poetry config virtualenvs.in-project true \
    && poetry install -n --no-dev


FROM python:3.8-alpine

ENV LANG=en_US.utf8
ENV VIRTUAL_ENV=/opt/houndigrade/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
WORKDIR /opt/houndigrade

RUN apk --no-cache --update add util-linux parted lvm2 udev \
    && mkdir -p /mnt/inspect

COPY --from=builder /opt/houndigrade .
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
