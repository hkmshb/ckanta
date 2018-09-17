import pytest
import os.path as fs
from ckanta.common import get_config_instance, Config, ConfigError, ApiClient


HERE = fs.abspath(fs.dirname(__file__))


class TestConfig:

    def test_instantiation_without_name(self):
        cfg = Config(urlbase='urlbase', apikey='apikey')
        assert cfg is not None
        assert cfg.name is None

    def test_instantiation_with_name(self):
        cfg = Config(name='name', urlbase='urlbase', apikey='apikey')
        assert cfg is not None
        assert cfg.name == 'name'

    def test_get_instance(self, cfg_s):
        config = get_config_instance(cfg_s, 'local')
        assert config is not None
        assert isinstance(config, Config)

    def test_fails_for_unknown_instance_name(self, cfg_s):
        with pytest.raises(ConfigError):
            get_config_instance(cfg_s, 'x-local')


class TestApiClient:

    def test_building_action_url(self):
        default_urlsubpath = ApiClient.API_URL_SUBPATH
        expected_url = 'http://localhost/{}/group_list'.format(
            default_urlsubpath
        )
        client = ApiClient('http://localhost', '*secret*')
        assert expected_url == client.build_action_url('group_list')

    def test_asserts_post_actions_have_payload(self):
        client = ApiClient('http://localhost', '*secret*')
        with pytest.raises(AssertionError):
            client('group_list', as_get=False)
