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



class ActionDef(namedtuple('ActionDef', ['name', 'table_def'])):

    def __new__(cls, name, table_def=None):
        if table_def and isinstance(table_def, str):
            table_def = TableDef(table_def.split(':'))
        return super().__new__(cls, name, table_def)


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
                    'item or tuple of string and TableDef items')
            if len(item) != 2 or not isinstance(item[1], TableDef):
                raise ValueError('Tuple item expected to contain string '
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


Actions = ActionDefList(
    ActionDef('user_list', TableDef([
        'id', 'name', 'fullname', 'state', 'sysadmin'])),
    ActionDef('group_list', TableDef([
        'id', 'name', 'title', 'state', 'package_count'])),
    ActionDef('organization_list', TableDef([
        'id', 'name', 'title', 'state', 'package_count'])),
    ActionDef('package_list', TableDef(['id',])),
    ActionDef('organization_list_for_user', TableDef([
        'id', 'title', 'state'])),
    ActionDef('group_list_authz', TableDef([
        'id', 'title', 'state'])),
    ActionDef('group_member_create'),
    ActionDef('organization_member_create'),
)


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
    _ACTIONS = {
        'user': Actions.get('user_list'),
        'group': Actions.get('group_list'),
        'organization': Actions.get('organization_list'),
        'dataset': Actions.get('package_list')
    }

    validation = {
        '--object': Choice(['dataset', 'group', 'organization', 'user'])
    }

    def handle(self):
        objectkey = self.option('object')
        actiondef = self._ACTIONS.get(objectkey)
        if objectkey in ('group', 'organization'):
            data = {'all_fields': True}
            result = self._api_post(actiondef.name, payload=data)
        else:
            result = self._api_get(actiondef.name)

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
        {--g|groups=* : id or name for an groupson the CKAN portal}
        {--o|orgs=* : id or name for an organization on the CKAN portal}
    '''
    _DEFAULT_ROLE = 'member'
    _ACTIONS = {
        'list_groups': Actions.get('group_list_authz'),
        'list_orgs': Actions.get('organization_list_for_user'),
        'create_group_member': Actions.get('group_member_create'),
        'create_org_member': Actions.get('organization_member_create'),
    }

    validation = {
        '--role': Choice([None, 'member', 'editor', 'admin'])
    }

    def handle(self):
        userid = self.argument('userid')
        add_member = self.option('add')
        if not add_member:
            # list organizations user belongs to
            action = self._ACTIONS['list_orgs']
            result = self._api_post(action.name, payload={"id": userid})
            if result['success']:
                info = action.table_def.extract_data(result['result'])
                if info.values:
                    self.line('User Organizations')
                    self.line(tabulate(info.values, info.headers))
                else:
                    self.line('No organization records found')

            # list groups user can edit
            action = self._ACTIONS['list_groups']
            result = self._api_post(action.name, payload={})
            if result['success']:
                info = action.table_def.extract_data(result['result'])
                if info.values:
                    self.line('\nUser Groups')
                    self.line(tabulate(info.values, info.headers))
                else:
                    self.line('No group records found')
        else:
            self.create_member(userid)

    def create_member(self, userid):
        role = self.option('role') or self._DEFAULT_ROLE
        groups = self.option('groups') or []
        orgs = self.option('orgs') or []

        for label, action, items in (
            ('Organizations', self._ACTIONS['create_org_member'], orgs), 
            ('Groups', self._ACTIONS['create_group_member'], groups)
        ):
            if items:
                self.line('\n>> Add {} to {}'.format(userid, label))

            for item in items:
                data = {'id': item, 'username': userid, 'role': role}
                try:
                    result = self._api_post(action.name, payload=data)
                    if result['success']:
                        self.line('{}: +'.format(item))
                except Exception as ex:
                    self.line('{}: x -{}'.format(item, str(ex)))


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
