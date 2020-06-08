#!/usr/bin/env bash
DOCKER_IMAGE="abarnaperu/osint-github"
CONTAINER_NAME="osint-github"

docker kill $CONTAINER_NAME
docker rm $CONTAINER_NAME
docker pull $DOCKER_IMAGE

# Running the container
docker run \
    -v $(pwd):/osint-github/mount/ \
    -e GITHUB_USERNAME \
    -e GITHUB_TOKEN \
    -e GITHUB_ORG_NAME \
    -e SLACK_WEBHOOK_URL \
    --name $CONTAINER_NAME $DOCKER_IMAGE