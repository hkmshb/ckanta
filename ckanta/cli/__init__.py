'''Command-Line Interface for CKANTA
'''
import sys
import enum
import click
import logging
from pprint import pprint
from ckanta.common import read_config, get_config_instance, \
     ConfigError, ApiClient, Config
from ckanta.commands import CommandError, ListCommand, ShowCommand


_log = logging.getLogger(__name__)
CONFIG_PATH = '~/.ckanta/config.ini'


def _configure_logger_dev():
    '''Configures the default logger for development.
    '''
    logging.basicConfig(level=logging.DEBUG)


def _load_config(instance_name):
    try:
        configp = read_config(CONFIG_PATH)
        cfg = get_config_instance(configp, instance_name)
    except ConfigError as ex:
        _log.info('Config file path: {}'.format(CONFIG_PATH))
        click.echo('error: {}'.format(ex))
        raise
    return cfg


@click.group()
@click.option('-u', '--urlbase')
@click.option('-k', '--apikey')
@click.option('-i', '--instance', default='local')
@click.option('--post', default=False, is_flag=True)
@click.option('--debug', default=False, is_flag=True)
@click.pass_context
def ckanta(ctx, urlbase, apikey, instance, post, debug):
    class CKANTAContext: 
        pass

    if debug:
        _configure_logger_dev()

    # mutually exclused: (urlbase, apikey) and instance
    if urlbase is not None and apikey is not None:
        client = ApiClient(urlbase, apikey)
    else:
        try:
            cfg = _load_config(instance)
        except ConfigError as ex:
            click.echo('Try providing the config parameters directly instead.\n')
            sys.exit()
        client = ApiClient(cfg.urlbase, cfg.apikey)

    # context to hold ckanta specific context
    # monkey patching.. really?
    context = CKANTAContext()
    context.client = client
    context.debug = debug
    context.as_get = not post
    ctx.obj = context


@ckanta.command()
@click.option('-n', '--name', default='local')
@click.option('-l', '--list', default=False, is_flag=True)
@click.option('--show-key', default=False, is_flag=True)
@click.pass_obj
def config(context, name, list, show_key):
    client = context.client

    if list and name != 'local':
        click.echo('error: The options -n/--name and -l/--list are '
                   'mutually exclusive. Use just one!\n')
        sys.exit()

    def _show_config_item(conf):
        click.echo('urlbase: {}'.format(conf.urlbase))
        click.echo('apikey: {}'.format(
            '***' if not show_key else conf.apikey
        ))
        click.echo()

    def _show_config():
        if name == 'local':
            _show_config_item(Config(client.urlbase, client.apikey))
            return

        try:
            conf = _load_config(name)
            _show_config_item(conf)
        except ConfigError as ex:
            sys.exit()

    def _list_config_sections():
        try:
            configp = read_config(CONFIG_PATH)
        except ConfigError as ex:
            errmsg = 'error: Config file not found: {}'.format(CONFIG_PATH)
            map(lambda f: f(errmsg), (_log.error, click.echo))
            sys.exit()

        click.echo('Instances:')
        for section in configp.sections():
            click.echo('   {}'.format(section[9:]))
        click.echo()


    if not list:
        _show_config()
    else:
        _list_config_sections()


@ckanta.command()
@click.argument('object', click.Choice(ListCommand.TARGET_OBJECTS))
@click.option('-o', '--option', multiple=True)
@click.pass_obj
def list(context, object, option):
    # option -> List; item format: key=value
    option_dict = dict(map(
        lambda opt: (x.strip() for x in opt.split('=')),
        option
    ))
    _log.debug('parsed options: {}'.format(option_dict))

    try:
        cmd = ListCommand(context.client, object=object, **option_dict)
        result = cmd.execute(as_get=context.as_get)
        pprint(result['result'])
    except CommandError as ex:
        func = _log.error if not context.debug else _log.exception
        func('error: {}'.format(ex))


@ckanta.command()
@click.argument('object', click.Choice(ShowCommand.TARGET_OBJECTS))
@click.argument('id', type=str)
@click.option('-o', '--option', multiple=True)
@click.pass_obj
def show(context, object, id, option):
    # option -> List; item format: key=value
    option_dict = dict(map(
        lambda opt: (x.strip() for x in opt.split('=')),
        option
    ))
    _log.debug('parsed options: {}'.format(option_dict))

    try:
        cmd = ShowCommand(context.client, object=object, id=id, **option_dict)
        result = cmd.execute(as_get=context.as_get)
        pprint(result['result'])
    except CommandError as ex:
        func = _log.error if not context.debug else _log.exception
        func('error: {}'.format(ex))


if __name__ == '__main__':
    ckanta()
