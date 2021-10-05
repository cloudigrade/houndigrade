#!/bin/bash

# Run the PR Check build stage
docker build --target pr_check .

mkdir -p artifacts
cat << EOF > artifacts/junit-dummy.xml
<testsuite tests="1">
    <testcase classname="dummy" name="dummytest"/>
</testsuite>
EOF
