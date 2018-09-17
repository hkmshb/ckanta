import os.path as fs
from pathlib import Path
from collections import namedtuple
from configparser import ConfigParser



class ConfigError(Exception):
    pass


Config = namedtuple('Config', ['urlbase', 'apikey'])


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


def read(fpath):
    '''Reads the CKANTA configuration at the specified path.
    '''
    fpath = fs.expanduser(fpath)
    fpath = fs.expandvars(fpath)

    cfgp = ConfigParser()
    if fpath not in cfgp.read(fpath):
        errmsg = 'File not found: {}'.format(fpath)
        raise ConfigError(errmsg)
    return cfgp


def get_instance(cfgp, name='local'):
    '''Returns the configuration for the named instance.
    '''
    section_name = 'instance:{}'.format(name)
    if section_name not in cfgp:
        errmsg = 'Config section not found: {}'
        raise ConfigError(errmsg.format(section_name))

    section = cfgp[section_name]
    values = list(map(
        lambda k: section.get(k), ('urlbase', 'apikey')
    ))
    return Config(*values)
