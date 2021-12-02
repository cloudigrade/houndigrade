# Builder Stage
FROM registry.access.redhat.com/ubi8/ubi-minimal:8.5 as builder

ENV LANG=en_US.utf8

WORKDIR /opt/houndigrade

COPY poetry.lock .
COPY pyproject.toml .

RUN microdnf update \
    && microdnf install -y \
        cargo \
        gcc \
        lvm2 \
        openssl-devel \
        python39-devel \
        python39-pip \
        udev \
        util-linux  \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.9 /usr/bin/python; fi \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.9 /usr/bin/pip ; fi \
    && pip install -U pip \
    && pip install poetry tox \
    && poetry config virtualenvs.in-project true \
    && poetry install -n --no-dev

# Release Stage
FROM registry.access.redhat.com/ubi8/ubi-minimal:8.5 as release

ENV LANG=en_US.utf8
ENV VIRTUAL_ENV=/opt/houndigrade/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
WORKDIR /opt/houndigrade

RUN microdnf update \
    && microdnf install -y \
        util-linux \
        lvm2 \
        python39 \
        udev \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.9 /usr/bin/python; fi \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.9 /usr/bin/pip ; fi \
    && mkdir -p /mnt/inspect

COPY --from=builder /opt/houndigrade .
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]

# PR Check Stage
FROM builder as pr_check

COPY tox.ini .
COPY houndigrade/ houndigrade/

RUN tox

# Declare "default" stage.
FROM release
