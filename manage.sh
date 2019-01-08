#!/bin/bash

set -eux

show_help() {
  echo """
  Commands:
    create-admin            : create admin user
    upload-data             : upload data to instance
  """
}

perform_action() {
  ## create system admin
  if [ "$*" == "create-admin" ]; then
    echo Creating SysAdmin User
    echo ======================

    cd ${wp}/grid-data-portal
    docker-compose exec ckan /opt/ckan/create_admin_user.sh
  fi

  ## upload data to instance
  if  [ "$*" == "upload-data" ]; then
    echo Uploading states and sectors data
    echo =================================

    cd ${wp}/ckanta
    py=$(pyenv root)/versions/eha/bin/python

    ${py} -m ckanta.cli upload group ./_fixtures/grid-sectors.txt
    ${py} -m ckanta.cli upload organization ./_fixtures/grid-states.txt
  fi
}

case "$*" in
  help )
    show_help
  ;;
  * )
    perform_action $*
  ;;
esac
