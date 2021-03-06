import csv
import os
import ast
import sys
import json
import logging
import requests
from urllib.parse import urljoin
from functools import update_wrapper

import click
from ckanta.deprecated import CommandBase


DEFAULT_PAGE_SIZE = 5
_log = logging.getLogger(__name__)


class ApiClient:
    ENV_VAR_PREFIX = "CKANTA_"
    API_URL_SUBPATH = '/api/3/action/'

    class Config:
        apikey = None
        urlbase = None
        username = None

        @classmethod
        def build_from_env(cls):
            '''Builds an instance of ApiClient.Config class from environment
            variables.
            '''
            conf = ApiClient.Config()
            for attrname in [n for n in dir(conf) if not n.startswith('__')]:
                varname = '{}{}'.format(
                    ApiClient.ENV_VAR_PREFIX, 
                    attrname.upper()
                )
                value = os.environ.get(varname)
                setattr(conf, attrname, value)
            return conf

    def __init__(self, site_url, username, apikey):
        self.site_url = site_url
        self.username = username
        self.apikey = apikey

    def _build_url(self, action):
        return urljoin(
            self.site_url + self.API_URL_SUBPATH,
            action
        )

    def get(self, action):
        '''Performs an API get request.

        :param action: the relative url path for the API endpoint.
        '''
        urlpath = self._build_url(action)
        headers = {
            'Authorization': self.apikey
        }
        resp = requests.get(urlpath, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def post(self, action, payload=None):
        '''Performs an API post request.

        :param action: the relative url path for the API endpoint.
        :param payload: payload to include in the request.
        '''
        urlpath = self._build_url(action)
        headers = {
            'Authorization': self.apikey,
            'Content-Type': 'application/json; charset=utf8'
        }
        resp = requests.post(
            urlpath,
            headers=headers,
            data=json.dumps(payload)
        )
        resp.raise_for_status()
        return resp.json()

    def __repr__(self):
        return "<ApiClient ({}, {}, {})>".format(
            self.site_url, self.username,
            "***"
        )

    @classmethod
    def from_conf(cls, conf=None):
        if conf is None:
            conf = ApiClient.Config.build_from_env()
        return ApiClient(
            site_url = conf.urlbase,
            username = conf.username,
            apikey = conf.apikey
        )


class OrganizationCommand:
    '''Command for handling Organization data on a CKAN data portal.
    '''

    def __init__(self, api_client, is_group=False):
        self.org_type = 'group' if is_group else 'organization'
        self._api_client = api_client
        self.is_group = is_group

    def list(self, simple, page_no=1, page_size=5, offset=0):
        '''Returns a list of Organizations witihin a CKAN data portal.
        '''
        action = '{}_list'.format(self.org_type)
        result = self._api_client.post(
            action, 
            payload={'all_fields': False}
        )
        if simple:
            return {'data': result['result']}
        else:
            action = '{}_show'.format(self.org_type)
            sorted_names = sorted(result['result'])

            page_no = page_no or 1
            page_size = page_size or DEFAULT_PAGE_SIZE
            start_idx = offset + (page_no * page_size) - page_size

            result_list = list(map(
                lambda n: self.show(n),
                sorted_names[start_idx: start_idx + page_size]
            ))
            return {
                'data': result_list,
                'pager': {
                    'no': page_no, 'size': page_size,
                    'offset': offset
                }
            }

    def show(self, id, bare=True):
        '''Returns the detail for an Organization identified by the specified id.
        '''
        action = '{}_show'.format(self.org_type)
        payload = {'id': id}
        if bare:
            payload.update({
                'include_users': False,
                'include_groups': False,
                'include_tags': False,
                'include_followers': False
            })

        result = self._api_client.post(action, payload)
        return {'data': [result['result']]}

    def create(self, data_dict):
        action = '{}_create'.format(self.org_type)
        result = self._api_client.post(action, data_dict)
        return result


class DatasetCommand:

    def __init__(self, api_client):
        self._api_client = api_client

    def list(self):
        action = 'package_list'
        result = self._api_client.post(action, {})
        return {
            'data': result['result']
        }

    def show(self, id):
        action = 'package_show'
        result = self._api_client.post(action, {'id': id})

        # exclude resources
        exclude_fields = [
            'resources', 'num_resources', 'num_tags', 'revision_id',
            'license_url'
            ]
        for field in exclude_fields:
            # error free way to delete/drop entries
            result['result'].pop(field, None)

        return {
            'data': [result['result']]
        }

    def create(self, data_dict):
        action = 'package_create'
        result = self._api_client.post(action, data_dict)
        return result


@click.group()
def ckanta():
    pass


@ckanta.group()
def organization():
    pass


@organization.command(name='list')
@click.option('-s', '--simple', is_flag=True, default=False)
@click.option('--is_group', is_flag=True, default=False)
@click.option('-n', '--page_no', type=int, default=1)
@click.option('-n', '--page_size', type=int, default=5)
@click.option('-o', '--offset', type=int, default=0)
def organization_list(simple, is_group, page_no, page_size, offset):
    api_client = ApiClient.from_conf()
    orgcmd = OrganizationCommand(api_client, is_group)
    try:
        result = orgcmd.list(simple, page_no, page_size, offset)
    except Exception as ex:
        _log.error("error: %s", ex)
        return

    if simple:
        print(result)
    else:
        persist_csv(result)


def persist_csv(result, filename='output-%04d.csv'):
    # extract records
    records = list(map(lambda d: d['data'][0], result['data']))
    fieldnames = list(records[0].keys())

    fn = filename % 1
    with open(fn, 'w') as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(row)

        fp.flush()
    click.echo('Done!')


@organization.command(name='upload')
@click.argument('input', type=click.File('r'))
@click.option('--is_group', is_flag=True, default=False)
def organization_upload(input, is_group):
    # *** groups ***
    # display_name,description,image_display_url,package_count,created,name,is_organization,
    # state,extras,image_url,type,title,revision_id,num_followers,id,approval_status

    api_client = ApiClient.from_conf()
    orgcmd = OrganizationCommand(api_client, is_group)

    extra_fields = ['code', 'slogan', 'website_url']
    exclude_fields = [
        'image_display_url', 'package_count', 'created', 'image_url', 
         'revision_id', 'num_followers', 'extras'
    ]

    # read csv file
    reader = csv.DictReader(input, delimiter=',')
    for row in reader:
        # build data dict
        data_dict = {field: row[field] 
            for field in row.keys()
            if field not in exclude_fields
        }
        if not orgcmd.is_group:
            data_dict['extras'] = [
                {'key': field, 'value': row[field]}
                    for field in extra_fields
            ]

        try:
            orgcmd.create(data_dict)
            _log.info("org created: %s", data_dict['name'])
        except Exception as ex:
            _log.error("error: %s", ex)
            _log.info("info: unable to create org: %s", data_dict['name'])


@ckanta.group()
def dataset():
    pass


@dataset.command(name='list')
def dataset_list():
    api_client = ApiClient.from_conf()
    cmd = DatasetCommand(api_client)
    print(cmd.list())


@dataset.command(name='dump')
@click.option('--limit', type=int, default=5)
@click.option('--offset', type=int, default=0)
@click.option('--output', type=click.Path(), default='datasets-%04d.csv')
def dataset_dump(limit, offset, output):
    api_client = ApiClient.from_conf()
    cmd = DatasetCommand(api_client)

    # retrieve dataset list
    try:
        result = cmd.list()
    except Exception as ex:
        _log.error("error: %s", ex)
        return

    sorted_names = sorted(result['data'])
    if not sorted_names:
        _log.info('No datasets found')
        return

    sorted_names = sorted_names[offset : offset + limit]
    result_list = list(map(lambda n: cmd.show(n), sorted_names))
    result = {'data': result_list}
    persist_csv(result, output)


@dataset.command(name='show')
def dataset_show():
    api_client = ApiClient.from_conf()
    cmd = DatasetCommand(api_client)
    print(cmd.show('abia-administrative-boundaries'))


@dataset.command(name='upload')
@click.argument('input', type=click.File('r'))
def dataset_upload(input):
    # *** groups ***
    # display_name,description,image_display_url,package_count,created,name,is_organization,
    # state,extras,image_url,type,title,revision_id,num_followers,id,approval_status

    api_client = ApiClient.from_conf()
    cmd = DatasetCommand(api_client)

    extra_fields = []

    # read csv file
    reader = csv.DictReader(input, delimiter=',')
    for row in reader:
        # build data dict
        data_dict = {field: row[field] 
            for field in row.keys()
            if field not in extra_fields
        }

        data_dict['extras'] = [
            {'key': field, 'value': row[field]}
                for field in extra_fields
        ]

        # process python dict, sequence that got converted to string
        for field in (
            'groups', 'tags', 'relationships_as_object', 'relationships_as_subject'
        ):
            value = data_dict.pop(field, None)
            if value:
                value = ast.literal_eval(value)
                data_dict[field] = value

        try:
            data_dict['sector_id'] = data_dict['groups'][0]['id']
            print('*' * 20)
            print(data_dict)
            print('*' * 20)
            cmd.create(data_dict)
            _log.info("dataset created: %s", data_dict['name'])
        except Exception as ex:
            _log.info("info: unable to create org: %s", data_dict['name'])
            _log.error("error: %s", ex)
            raise
