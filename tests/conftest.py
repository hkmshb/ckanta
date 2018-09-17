import pytest
from configparser import ConfigParser


@pytest.fixture(scope='function')
def cfg_s():
    cfg = ConfigParser()
    cfg.read_string('''
        [instance:local]
        urlbase=http://localhost:5000
        apikey=29dc8b28d78g923basd43w

        [instance:dev]
        urlbase=http://dev.local.io:5000
        apikey=29chibads978237dluw072as3
    ''')
    return cfg
