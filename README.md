# houndigrade

[![license](https://img.shields.io/github/license/cloudigrade/houndigrade.svg)]()
[![Build Status](https://travis-ci.org/cloudigrade/houndigrade.svg?branch=master)](https://travis-ci.org/cloudigrade/houndigrade)
[![codecov](https://codecov.io/gh/cloudigrade/houndigrade/branch/master/graph/badge.svg)](https://codecov.io/gh/cloudigrade/houndigrade)
[![Updates](https://pyup.io/repos/github/cloudigrade/houndigrade/shield.svg)](https://pyup.io/repos/github/cloudigrade/houndigrade/)
[![Python 3](https://pyup.io/repos/github/cloudigrade/houndigrade/python-3-shield.svg)](https://pyup.io/repos/github/cloudigrade/houndigrade/)

# What is houndigrade?

houndigrade is the scanning component of cloudigrade.

# Developing houndigrade

This document provides instructions for setting up houndigrade's development
environment and some commands for testing and running it.

## Local system setup (macOS)

Install [homebrew](https://brew.sh/):

    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

Use homebrew to install modern Python and gettext:

    brew update
    brew install python gettext
    brew link gettext --force

Get into the houndigrade project code:

    git clone git@github.com:cloudigrade/houndigrade.git
    cd houndigrade

## Python virtual environment setup

All of houndigrade's dependencies should be stored in a virtual environment.
These instructions assume it is acceptable for you to use
[poetry](https://python-poetry.org/docs/), but if you wish
to use another technology, that's your prerogative!

To create a virtualenv and install the project dependencies run:

    pip install poetry
    poetry install

If you need to add a dependancy to the project use:

    poetry add <dependency-name>

Finally, if you need to install a dev only dependency, use:

    poetry add --dev <dependecy-name>


## Common commands

### Running

Before running, you must have set and exported the following environment variables so houndigrade can talk to Amazon SQS to share its results:

    - `QUEUE_CONNECTION_URL`
    - `AWS_SQS_QUEUE_NAME_PREFIX`

`AWS_SQS_QUEUE_NAME_PREFIX` should match what you use when running cloudigrade, and that is probably `${USER}-`.

`QUEUE_CONNECTION_URL` must be a well-formed SQS URL that includes your Amazon SQS access key and secret key. Many Amazon keys have URL-unfriendly characters. You may want to use a small helper script like this to generate a valid URL:

```python
from os import environ
from urllib.parse import quote
print('sqs://{}:{}@'.format(
    quote(environ['AWS_SQS_ACCESS_KEY_ID'], safe=''),
    quote(environ['AWS_SQS_SECRET_ACCESS_KEY'], safe='')
))
```

To run houndigrade locally against minimal test disk images, follow these steps:

1. Sync and update the submodule for the `test-data` directory:
    ```
    git submodule sync --recursive
    git submodule update --init --recursive --force
    ```
2. Verify that the submodule was populated:
    ```
    ls -l ./test-data/disks/
    ```
3. Use `docker-compose` to run houndigrade locally with the test data:
    ```
    docker-compose build --no-cache && docker-compose up --force-recreate
    ```
    or if you want to build and run over cached images:
    ```
    docker-compose up --build --force-recreate
    ```
    This will mount `test-data` as a shared directory volume, create loop devices for each disk, and perform houndigrade's inspection for each device. houndigrade should put a message on the configured queue for each inspection, and its console output should produce something like during operation:
    ```
    ...
    app_1  | ####################################
    app_1  | # Inspection for disk file: /test-data/disks/centos_release
    app_1  | Provided cloud: aws
    app_1  | Provided drive(s) to inspect: (('ami-centos_release', '/dev/loop10'),)
    app_1  | Checking drive /dev/loop10
    app_1  | Checking partition /dev/loop10p1
    app_1  | RHEL not found via release file on: /dev/loop10p1
    app_1  | RHEL not found via product certificate on: /dev/loop10p1
    ...
    ```
4. After `docker-compose` completes, force update the submodule because `docker-compose` has a tendency to touch the disk files despite mounting the volume as read-only.
    ```
    git submodule update --init --recursive --force
    ```

### Testing

To run all local tests as well as our code-quality checking commands:

    tox

To run just our code-quality checking commands:

    tox -e flake8

To run just our tests:

    tox -e py37

If you wish to run a higher-level suite of integration tests, see
[integrade](https://github.com/cloudigrade/integrade).

### Manually running in AWS

If you want to manually run houndigrade in AWS so that you can watch its output in real-time, you can *simulate* how the cloudigrade ECS task runs houndigrade by SSH-ing to an EC2 instance (running an ECS AMI) and running Docker with the arguments that would be used in the ECS task definition. For example:

    docker run \
        --mount type=bind,source=/dev,target=/dev \
        --privileged --rm -i -t \
        -e AWS_ACCESS_KEY_ID=AWS_SQS_ACCESS_KEY_ID \
        -e AWS_DEFAULT_REGION="us-east-1" \
        -e AWS_SECRET_ACCESS_KEY="AWS_SQS_SECRET_ACCESS_KEY" \
        -e EXCHANGE_NAME="" \
        -e QUEUE_CONNECTION_URL="sqs://AWS_SQS_ACCESS_KEY_ID:AWS_SQS_SECRET_ACCESS_KEY@" \
        -e RESULTS_QUEUE_NAME="HOUNDIGRADE_RESULTS_QUEUE_NAME" \
        --name houndi \
        "registry.gitlab.com/cloudigrade/houndigrade:latest" \
        -c aws \
        -t ami-13469000000000000 /dev/sdf \
        -t ami-12345678900000000 /dev/sdg

You will need to set appropriate values for the `-e` variables passed into the environment, each of the `-t` arguments that define the inspection targets, and the specific version of the houndigrade image you wish to use. When you attach volumes in AWS, you can define the device paths they'll use, and they should match your target arguments here. Alternatively, you can describe the running EC2 instance to get the device paths.
