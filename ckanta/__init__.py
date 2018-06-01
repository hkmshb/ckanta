__version__ = '0.1.0'


import os
import sys
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

    def __init__(self, automator, name=None):
        super(CommandBase, self).__init__(name)
        self.automator = automator

    def _api_get(self, rel_urlpath):
        '''Perform an API get request.

        :param rel_urlpath: the relative url path for the API endpoint.
        '''
        conf = self.automator._conf
        urlpath = urljoin(conf.urlbase + '/api/3/action/', rel_urlpath)
        headers = {'Authorization': conf.apikey}
        resp = requests.get(urlpath, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        return result


class UserCommand(CommandBase):
    """Manage users on CKAN

    user
        {--l|list : If set, list all active users}
    """
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


class Automator(Application):
    ENVVAR_PREFIX = 'CKANTA_'

    class Config:
        apikey = None
        urlbase = None
        username = None

    def __init__(self):
        super(Automator, self).__init__()
        self.add(UserCommand(self))

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
