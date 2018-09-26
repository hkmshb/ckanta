import pytest
from ckanta.commands import MembershipCommand


class DummyContext:
    client = None
    debug = False


class TestMembershipCommand:
    
    def test_action_args_has_subcommand(self):
        # TODO: fix use of object() as param values
        cmd = MembershipCommand(DummyContext(), object(), object())
        assert cmd is not None
        assert 'object' in cmd.action_args
        assert cmd.action_args['object'] == cmd.COMMAND
