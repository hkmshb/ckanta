import os.path as fs
from pathlib import Path
from collections import namedtuple
from configparser import ConfigParser



class ConfigError(Exception):
    pass


Config = namedtuple('Config', ['urlbase', 'apikey'])


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
