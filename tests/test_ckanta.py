from ckanta import __version__
from ckanta import ActionDef


def test_version():
    assert __version__ == '0.1.0'


def test_actiondef():
    action = ActionDef('action')
    assert action is not None
    assert action.table_def is None
