import pytest
import os.path as fs
from ckanta.config import get_instance, Config, ConfigError


HERE = fs.abspath(fs.dirname(__file__))


class TestConfig:

    def test_get_instance(self, cfg_s):
        config = get_instance(cfg_s, 'local')
        assert config is not None
        assert isinstance(config, Config)

    def test_fails_for_unknown_instance_name(self, cfg_s):
        with pytest.raises(ConfigError):
            get_instance(cfg_s, 'x-local')
