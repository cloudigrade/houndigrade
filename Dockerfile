FROM fedora:29

ENV LANG=en_US.utf8

COPY Pipfile .
COPY Pipfile.lock .

RUN dnf update -y \
    && dnf install which -y \
    && if [ ! -e /usr/bin/pip ]; then ln -s /usr/bin/pip3.7 /usr/bin/pip ; fi \
    && if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3.7 /usr/bin/python; fi \
    && pip install pipenv \
    && pipenv install --system \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && mkdir -p /mnt/inspect

WORKDIR /opt/houndigrade
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
