FROM centos:7

ENV LANG=en_US.utf8

RUN mkdir -p /mnt/inspect

RUN yum install centos-release-scl -y \
    && yum-config-manager --enable centos-sclo-rh-testing \
    && yum install which rh-python36 rh-python36-python-pip -y

COPY Pipfile .
COPY Pipfile.lock .
RUN scl enable rh-python36 'pip install pipenv \
    && pipenv install --system \
    && rm -rf Pipfile*'

WORKDIR /opt/houndigrade
COPY houndigrade/cli.py .

ENTRYPOINT ["scl", "enable", "rh-python36", "python", "cli.py"]
CMD ["--help"]
