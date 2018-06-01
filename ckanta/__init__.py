__version__ = '0.1.0'


import os
import sys
import json
import requests
from tabulate import tabulate
from urllib.parse import urljoin
from collections import OrderedDict, namedtuple
from cleo import Application, Command



class TableDef(namedtuple('TableDef', ['columns', 'headers'])):

    __Info = namedtuple('TableInfo', ['headers', 'values'])

    def __new__(cls, columns, headers=None):
        headers = (headers or [])
        if isinstance(headers, str):
            headers = headers.split(':')

        headers = headers[:len(columns)]
        if len(columns) > len(headers):
            headers += [''] * (len(columns) - len(headers))

        for i, col in enumerate(columns):
            if not headers[i]:
                headers[i] = col.replace('_', ' ').title()
        return super().__new__(cls, columns, headers)

    def extract_data(self, result_data):
        table = []
        for data in result_data:
            row = [data[c] for c in self.columns]
            table.append(row)
        return self.__Info(self.headers, table)


class CommandBase(Command):
    _API_URL_SUBPATH = '/api/3/action/'

    def __init__(self, automator, name=None):
        super(CommandBase, self).__init__(name)
        self.automator = automator

    def _build_url(self, action):
        conf = self.automator._conf
        return urljoin(conf.urlbase + self._API_URL_SUBPATH, action)

    def _api_get(self, action):
        '''Perform an API get request.

        :param action: the relative url path for the API endpoint.
        '''
        conf = self.automator._conf
        urlpath = self._build_url(action)
        headers = {'Authorization': conf.apikey}
        resp = requests.get(urlpath, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        return result

    def _api_post(self, action, payload=None):
        '''Perform an API post request.

        :param action: the relative url path for the API endpoint.
        :param payload: payload to include in the request.
        '''
        conf = self.automator._conf
        urlpath = self._build_url(action)
        headers = {
            'Authorization': conf.apikey, 
            'Content-Type': 'application/json; charset=utf8'
        }
        resp = requests.post(urlpath, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        result = resp.json()
        return result


class UserCommand(CommandBase):
    '''Manage users on CKAN

    user
        {--l|list : If set, list all users}
    '''
    _DEFAULT_TDEF = TableDef('id:name:fullname:state:sysadmin'.split(':'))

    def handle(self):
        list_users = self.option('list')
        if not list_users:
            self.line('Tada!')
            return

        result = self._api_get('user_list')
        if result['success']:
            info = self._DEFAULT_TDEF.extract_data(result['result'])
            if info.values:
                self.line(tabulate(info.values, info.headers))
                self.line('\ndone!')
            else:
                self.line('No records found')


class UserMembershipCommand(CommandBase):
    '''Manages Organization and Group membership for a CKAN user.

    user:membership
        {userid : id or username for a registered CKAN user}
        {--g|group : id or name for a group on the CKAN portal}
        {--o|org : id or name for an organization on the CKAN portal}
    '''
    _DEFAULT_TDEF = TableDef('id:title:state'.split(':'))

    def handle(self):
        userid = self.argument('userid')
        group = self.option('group')
        org = self.option('org')
        if not (group and org):
            action_name = 'organization_list_for_user'
            result = self._api_post(action_name, payload={"id": userid})
            if result['success']:
                info = self._DEFAULT_TDEF.extract_data(result['result'])
                if info.values:
                    self.line(tabulate(info.values, info.headers))
                    self.line('\ndone')
                else:
                    self.line('No records found')


class Automator(Application):
    ENVVAR_PREFIX = 'CKANTA_'

    class Config:
        apikey = None
        urlbase = None
        username = None

    def __init__(self):
        super(Automator, self).__init__()
        self.add(UserCommand(self))
        self.add(UserMembershipCommand(self))

    @classmethod
    def init(cls):
        '''Build an instance of the Automator.Config class from environment
        variables.
        '''
        conf = Automator.Config()
        for attrname in [n for n in dir(conf) if not n.startswith('__')]:
            varname = '{}{}'.format(cls.ENVVAR_PREFIX, attrname.upper())
            value = os.environ.get(varname)
            if not value:
                print("error: please set the '{}' env variable".format(varname))
                sys.exit(1)
            setattr(conf, attrname, value)
        
        cls._conf = conf
