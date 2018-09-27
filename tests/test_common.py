import pytest
import os.path as fs
from ckanta.common import get_instance_config, Config, ConfigError, \
     ApiClient, MembershipRole


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
        config = get_instance_config(cfg_s, 'local')
        assert config is not None
        assert isinstance(config, Config)

    def test_fails_for_unknown_instance_name(self, cfg_s):
        with pytest.raises(ConfigError):
            get_instance_config(cfg_s, 'x-local')


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


class TestMembershipRole:

    def test_names_returns_roles_as_string(self):
        expected = set(('none', 'member', 'editor', 'admin'))
        assert set(MembershipRole.names()) == expected

    @pytest.mark.parametrize('name, expected', [
        ('none', MembershipRole.NONE), ('member', MembershipRole.MEMBER),
        ('editor', MembershipRole.EDITOR), ('admin', MembershipRole.ADMIN)
    ])
    def test_creating_role_using_from_name(self, name, expected):
        value = MembershipRole.from_name(name)
        assert value == expected

    def test_creating_role_from_invalid_name_fails(self):
        with pytest.raises(ValueError):
            MembershipRole.from_name('bad-name')

    def test_name_exclusions(self):
        exclude_list = (MembershipRole.NONE, MembershipRole.ADMIN)
        names = MembershipRole.names(exclude_list)
        assert names and len(names) == 2
        assert MembershipRole.ADMIN.name.lower() not in names
        assert MembershipRole.NONE.name.lower() not in names
