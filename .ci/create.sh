#!/usr/bin/env bash

set -e

appsDir=$1

function run {
  apps=$(ls ${appsDir})
  options="--upsert --grpc-web"
  for app in ${apps[@]}; do
    argocd app create ${app%.yaml} -f ${appsDir}/${app} ${options}
  done
}

function error {
  echo "usage: $(basename $0) appsDir"
}

if [ -z $1 ]; then
  error
  exit 1
fi

run
