__version__ = '0.1.0'


import os
import sys
import json
import requests
from tabulate import tabulate
from urllib.parse import urljoin
from collections import OrderedDict, namedtuple, MutableSequence
from cleo import Application, Command
from cleo.validators import Choice



ActionDef = namedtuple('ActionDef', ['name', 'action', 'table_def'])

class ActionDefList(MutableSequence):

    def __init__(self, *items):
        # validate items
        items = [self.validate_item(i) for i in items]
        self._innerlist = items

    def __delitem__(self, pos):
        del self._innerlist[pos]

    def __getitem__(self, pos):
        return self._innerlist[pos]

    def __setitem__(self, pos, item):
        item = self.validate_item(item)
        self._innerlist[pos] = item

    def __len__(self):
        return len(self._innerlist)

    def insert(self, pos, value):
        print((pos, value))

    def get(self, name):
        for item in self:
            if item.name == name:
                return item
        return None

    def validate_item(self, item):
        if not isinstance(item, ActionDef):
            if not isinstance(item, (list, tuple)):
                raise ValueError('List item expected to be an ActionDef '
                    'item or tuple of strings and TableDef items')
            if len(item) != 3 or not isinstance(item[2], TableDef):
                raise ValueError('Tuple item expected to contain strings '
                    'and TableDef items in that order')
            item = ActionDef(*item)
        return item


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


class ShowCommand(CommandBase):
    '''Displays a listing of the major objects within CKAN

    show
        {--o|object= (choice) : one of 'user', 'group', 'organization' or 'dataset' }
    '''
    _ACTIONS = ActionDefList(
        ('user', 'user_list', TableDef('id:name:fullname:state:sysadmin'.split(':'))),
        ('group', 'group_list', TableDef(('id:name:title:state:package_count'.split(':')))),
        ('organization', 'organization_list', TableDef(('id',))),
        ('dataset', 'package_list', TableDef(('id',)))
    )
    validation = {
        '--object': Choice(['dataset', 'group', 'organization', 'user'])
    }

    def handle(self):
        objectkey = self.option('object')
        actiondef = self._ACTIONS.get(objectkey)
        if objectkey in ('group', 'organization'):
            data = {'all_fields': True}
            result = self._api_post(actiondef.action, payload=data)
        else:
            result = self._api_get(actiondef.action)

        if objectkey not in ('user', 'group'):
            print(result)
            return

        if result['success']:
            table_def = actiondef.table_def
            info = table_def.extract_data(result['result'])
            if info.values:
                self.line(tabulate(info.values, info.headers))
                self.line('\ndone!')
            else:
                self.line('No records found')


class UserMembershipCommand(CommandBase):
    '''Manages the Organization and Group membership for a CKAN user.

    membership
        {userid : id or username for a registered CKAN user}
        {--a|add : If set, adds user as a member of provided group}
        {--r|role=? (choice) : one of 'member', 'editor' or 'admin'}
        {--g|groups=* : id or name for an organization or on the CKAN portal}
    '''
    _ACTION_LIST = 'organization_list_for_user'
    _ACTION_CREATE = 'organization_member_create'
    _DEFAULT_TDEF = TableDef('id:title:state'.split(':'))
    _DEFAULT_ROLE = 'member'

    validation = {
        '--role': Choice([None, 'member', 'editor', 'admin'])
    }

    def handle(self):
        userid = self.argument('userid')
        add_member = self.option('add')
        if not add_member:
            action_name = self._ACTION_LIST
            result = self._api_post(action_name, payload={"id": userid})
            if result['success']:
                info = self._DEFAULT_TDEF.extract_data(result['result'])
                if info.values:
                    self.line(tabulate(info.values, info.headers))
                    self.line('\ndone')
                else:
                    self.line('No records found')
        else:
            self.create_member(userid)

    def create_member(self, userid):
        action_name = self._ACTION_CREATE
        groups = self.option('groups')  or []
        role = self.option('role') or self._DEFAULT_ROLE

        for g in groups:
            data = {'id': g, 'username': userid, 'role': role}
            try:
                result = self._api_post(action_name, payload=data)
                if result['success']:
                    self.line('{}: +'.format(g))
            except Exception as ex:
                self.line('{}: x -{}'.format(g, str(ex)))


class Automator(Application):
    ENVVAR_PREFIX = 'CKANTA_'

    class Config:
        apikey = None
        urlbase = None
        username = None

    def __init__(self):
        super(Automator, self).__init__()
        self.add(ShowCommand(self))
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
