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

Need to run houndigrade? Use docker-compose!

    make start-compose

This will also mount the `./houndigrade` folder inside the container, so you can
continue working on code and it will auto-reload in the container. AWS Access
within Docker is handled via environment variables. See the AWS account setup
section for details.

## Python virtual environment setup

All of houndigrade's dependencies should be stored in a virtual environment.
These instructions assume it is acceptable for you to use
[pipenv](https://docs.pipenv.org), but if you wish
to use another technology, that's your prerogative!

To create a virtualenv and install the project dependencies run:

    pipenv install

If you need to add a dependancy to the project use:

    pipenv install <dependency-name>

Finally, if you need to install a dev only dependency, use:

    pipenv install --dev <dependecy-name>


## Common commands

### Running

### Testing

To run all local tests as well as our code-quality checking commands:

    tox

If you wish to run a higher-level suite of integration tests, see
[integrade](https://github.com/cloudigrade/integrade).
