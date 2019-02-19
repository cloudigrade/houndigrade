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

Use homebrew to install modern Python, pipenv, and gettext:

    brew update
    brew install python pipenv gettext
    brew link gettext --force

Get into the houndigrade project code:

    git clone git@github.com:cloudigrade/houndigrade.git
    cd houndigrade

## Python virtual environment setup

All of houndigrade's dependencies should be stored in a virtual environment.
These instructions assume it is acceptable for you to use
[pipenv](https://docs.pipenv.org), but if you wish
to use another technology, that's your prerogative!

To create a virtualenv and install the project dependencies run:

    pipenv install --dev

If you need to add a dependancy to the project use:

    pipenv install <dependency-name>

Finally, if you need to install a dev only dependency, use:

    pipenv install --dev <dependecy-name>


## Common commands

### Running

Before running, you must have the following environment variables set so houndigrade can talk to Amazon SQS to share its results:

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

To run houndigrade locally, follow these steps:
1. Create a folder called test-disks ie. `mkdir ./test-disks`
2. Download all of the block devices found [here](https://drive.google.com/open?id=1xvxnmqJ6H9UF7iE5bN2twat01F8FwsaD)
3. Move the downloaded block devices to test-disks.
4. Now use docker-compose: `docker-compose up`

This will start the houndigrade container, mount provided block
devices inside said container, and run a scan against it, placing the results
 on the queue. The queue can be accessed at [localhost:15672](http://localhost:15672) with `guest/guest` being the default credentials.

### Testing

To run all local tests as well as our code-quality checking commands:

    tox

To run just our code-quality checking commands:

    tox -e flake8

To run just our tests:

    tox -e py36

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
