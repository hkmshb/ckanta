import requests
import os.path as fs
from pathlib import Path
from collections import namedtuple
from configparser import ConfigParser



class CKANTAError(Exception):
    '''Base exception for all exceptions defined in CKANTA.
    '''
    pass


class ConfigError(CKANTAError):
    pass


class Config(namedtuple('Config', ['urlbase', 'apikey', 'name'])):
    '''Config object which optional can carry a name.
    '''

    def __new__(cls, urlbase, apikey, name=None):
        return super().__new__(cls, urlbase, apikey, name)


def read_config(fpath):
    '''Reads the CKANTA configuration at the specified path.
    '''
    fpath = fs.expanduser(fpath)
    fpath = fs.expandvars(fpath)

    configp = ConfigParser()
    if fpath not in configp.read(fpath):
        errmsg = 'File not found: {}'.format(fpath)
        raise ConfigError(errmsg)
    return configp


def get_config_instance(configp, name='local'):
    '''Returns the configuration for the named instance.
    '''
    section_name = 'instance:{}'.format(name)
    if section_name not in configp:
        errmsg = 'Config section not found: {}'
        raise ConfigError(errmsg.format(section_name))

    section = configp[section_name]
    values = list(map(
        lambda k: section.get(k), ('urlbase', 'apikey')
    ))
    return Config(*values)


class ApiClient:
    API_URL_SUBPATH = 'api/3/action'

    def __init__(self, urlbase, apikey, action_urlsubpath=None):
        if urlbase and urlbase.endswith('/'):
            urlbase = urlbase[:-1]
        
        if action_urlsubpath:
            if action_urlsubpath.startswith('/'):
                action_urlsubpath = action_urlsubpath[1:]
            if action_urlsubpath.endswith('/'):
                action_urlsubpath = action_urlsubpath[:-1]

        self.action_urlsubpath = action_urlsubpath or self.API_URL_SUBPATH
        self.urlbase = urlbase
        self.apikey = apikey

    def build_action_url(self, action_name):
        urlfmt = '{urlbase}/{urlsubpath}/{action_name}'.format(
            urlbase=self.urlbase, 
            urlsubpath=self.action_urlsubpath,
            action_name=action_name
        )
        return urlfmt

    def __call__(self, action_name, data=None, as_get=True):
        '''Performs an API request.
        
        A GET is made by default if as_get remains True otherwise a POST
        request if set to False.
        '''
        headers = {'Authorization': self.apikey}
        action_url = self.build_action_url(action_name)
        if as_get:
            resp = requests.get(action_url, headers=headers)
        else:
            assert data, "Payload required for making a POST request"

            headers['Content-Type'] = 'application/json; charset=utf8'
            resp = requests.post(action_url, headers=headers,
                                 data=json.dumps(data))

        resp.raise_for_status()
        return resp.json()

    def __repr__(self):
        msgfmt = '<ApiClient (urlbase={}, apikey=***)>'
        return msgfmt.format(self.urlbase)
