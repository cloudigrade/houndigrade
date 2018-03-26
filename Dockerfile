FROM python:3.6-alpine

RUN apk --no-cache --update add util-linux
RUN mkdir -p /mnt/inspect

COPY Pipfile .
COPY Pipfile.lock .
RUN pip install pipenv \
    && pipenv install --system \
    && rm -rf Pipfile*

WORKDIR /opt/houndigrade
COPY houndigrade/cli.py .

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
