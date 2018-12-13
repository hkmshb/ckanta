#!/bin/bash

set -eux

## create system admin
if [ "$*" == "create-admin" ]; then
    echo Creating SysAdmin User
    echo ======================

    cd ${wp}/grid-data-portal
    docker-compose exec ckan /opt/ckan/create_admin_user.sh
fi

if  [ "$*" == "upload-data" ]; then
    echo Uploading states and sectors data
    echo =================================

    cd ${wp}/ckanta
    py=$(pyenv root)/versions/eha/bin/python

    ${py} -m ckanta.cli upload group ./_fixtures/grid-sectors.txt
    ${py} -m ckanta.cli upload organization ./_fixtures/grid-states.txt
fi