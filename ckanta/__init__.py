__version__ = '0.1.0'


import os
import sys
import requests
from urllib.parse import urljoin
from cleo import Application, Command



class CommandBase(Command):

    def __init__(self, automator, name=None):
        super(CommandBase, self).__init__(name)
        self.automator = automator


class UserCommand(CommandBase):
    """Manage users on CKAN

    user:membership
        {--l|list : If set, list all active users}
    """
    def handle(self):
        list_users = self.option('list')
        if not list_users:
            self.line('Tada!')
            return

        conf = self.automator._conf
        url = urljoin(conf.urlbase, 'user_list')
        hdr = {'Authorization': conf.apikey}
        resp = requests.get(url, headers=hdr)
        if resp.status_code != requests.codes.ok:
            resp.raise_for_status()

        result = resp.json()
        self.line(str(result))


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
