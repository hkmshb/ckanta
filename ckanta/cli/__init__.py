'''Command-Line Interface for CKANTA
'''
import sys
import enum
import click
import logging
from pprint import pprint
from ckanta.common import read_config, get_instance_config, \
     get_config, log_error, ConfigError, ApiClient, Config, \
     CKANTAContext, CKANObject, MembershipRole
from ckanta.commands import CommandError, ListCommand, ShowCommand, \
     MembershipCommand, MembershipGrantCommand, UploadCommand


_log = logging.getLogger(__name__)
CONFIG_PATH = '~/.config/ckanta.conf'


def _configure_logger_dev():
    '''Configures the default logger for development.
    '''
    logging.basicConfig(level=logging.DEBUG)


@click.group()
@click.option('-u', '--urlbase')
@click.option('-k', '--apikey')
@click.option('-i', '--instance', default='local')
@click.option('-p', '--post', default=False, is_flag=True)
@click.option('-d', '--debug', default=False, is_flag=True)
@click.pass_context
def ckanta(ctx, urlbase, apikey, instance, post, debug):
    if debug:
        _configure_logger_dev()

    try:
        configp = read_config(CONFIG_PATH)
    except ConfigError as ex:
        _log.info('Config file not found: {}'.format(CONFIG_PATH))

    # mutually exclused: (urlbase, apikey) and instance
    if urlbase is not None and apikey is not None:
        client = ApiClient(urlbase, apikey)
    else:
        try:
            cfg = get_instance_config(configp, instance)
        except ConfigError as ex:
            click.echo('Try providing the config parameters directly instead.\n')
            sys.exit()
        client = ApiClient(cfg.urlbase, cfg.apikey)

    # context to hold ckanta specific context
    context = CKANTAContext(configp, client, not post, debug)
    ctx.obj = context


@ckanta.command()
@click.option('-i', '--instance', default='local')
@click.option('-l', '--list', default=False, is_flag=True)
@click.option('--show-key', default=False, is_flag=True)
@click.pass_obj
def config(context, instance, list, show_key):
    '''Explore configured settings for CKANTA.
    '''
    client = context.client

    if list and instance != 'local':
        click.echo('error: The options -i/--instance and -l/--list are '
                   'mutually exclusive. Use just one!\n')
        sys.exit()

    def _show_config_item(conf):
        click.echo('urlbase: {}'.format(conf.urlbase))
        click.echo('apikey: {}'.format(
            '***' if not show_key else conf.apikey
        ))
        click.echo()

    def _show_config():
        if instance == 'local':
            _show_config_item(Config(client.urlbase, client.apikey))
            return

        try:
            conf = _load_config(instance)
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


@ckanta.command('list')
@click.argument('object', type=click.Choice(ListCommand.TARGET_OBJECTS))
@click.option('-o', '--option', multiple=True)
@click.pass_obj
def ckanta_list(context, object, option):
    '''Retrieve a list of objects (dataset, group, organization, user) from
    a CKAN instance.
    '''
    # option -> List; item format: key=value
    option_dict = dict(map(
        lambda opt: (x.strip() for x in opt.split('=')),
        option
    ))
    _log.debug('parsed options: {}'.format(option_dict))

    try:
        cmd = ListCommand(context, object=object, **option_dict)
        result = cmd.execute(as_get=context.as_get)
        pprint(result['result'])
    except CommandError as ex:
        func = _log.error if not context.debug else _log.exception
        func('error: {}'.format(ex))


@ckanta.command()
@click.argument('object', type=click.Choice(ShowCommand.TARGET_OBJECTS))
@click.argument('id', type=str)
@click.option('-o', '--option', multiple=True)
@click.pass_obj
def show(context, object, id, option):
    '''Show an object (dataset, group, organization, user) in detail.
    '''
    # option -> List; item format: key=value
    option_dict = dict(map(
        lambda opt: (x.strip() for x in opt.split('=')),
        option
    ))
    _log.debug('parsed options: {}'.format(option_dict))
    result = {}

    try:
        cmd = ShowCommand(context, object=object, id=id, **option_dict)
        result = cmd.execute(as_get=context.as_get)
    except CommandError as ex:
        func = _log.error if not context.debug else _log.exception
        func('error: {}'.format(ex))
        return
    pprint(result)


@ckanta.group()
@click.pass_obj
def membership(context):
    '''Manage user membership across objects on a CKAN instance.
    '''
    pass


@membership.command('list')
@click.argument('userid', type=str)
@click.option('-g', '--check-groups', default=False, is_flag=True)
@click.pass_obj
def membership_list(context, userid, check_groups):
    '''Retrieves and returns organizations which user with specified user
    Id has membership.

    :param userid: Id of user whose memberships are to be retrieved.
    :type userid: string

    :param check_groups: Indicates whether to retrieve groups for which the user
        with specified user Id has membership.
    :type check_groups: boolean
    '''
    result = {}
    try:
        cmd = MembershipCommand(context, userid, check_groups)
        result = cmd.execute(as_get=False)
    except CommandError as ex:
        func = _log.error if not context.debug else _log.exception
        func('error: {}'.format(ex))
        return
    pprint(result)


@membership.command('grant')
@click.argument('userid', type=str)
@click.argument('role', type=click.Choice(MembershipRole.names()))
@click.option('-d', '--dataset', 'datasets', multiple=True)
@click.option('-g', '--group', 'groups', multiple=True)
@click.option('-o', '--org', 'orgs', multiple=True)
@click.pass_obj
def membership_grant(context, userid, role, datasets, groups, orgs):
    '''Grants user access priviledge on a group, organization or dataset.
    '''
    if datasets:
        click.echo('Processing user access grant for dataset(s)...')
        obj_type = CKANObject.DATASET
        cmd = MembershipGrantCommand(context, userid, role, datasets, obj_type)
        result = cmd.execute(as_get=False)
        pprint(result)

    for (objects, obj_type) in (
        (groups, CKANObject.GROUP), 
        (orgs, CKANObject.ORGANIZATION)
    ):
        if not objects:
            continue

        click.echo('Processing user membership for {}(s)...'.format(
            obj_type.name.lower()))

        cmd = MembershipGrantCommand(context, userid, role, objects, obj_type)
        result = cmd.execute(as_get=False)
        pprint(result)


@ckanta.command()
@click.argument('object', type=click.Choice(UploadCommand.TARGET_OBJECTS))
@click.argument('infile', type=click.File('r'))
@click.option('--org', 'owner_orgs', multiple=True)
@click.confirmation_option(help="Have you reviewed parameters and want to proceed?")
@click.pass_obj
def upload(context, object, infile, owner_orgs):
    '''Create objects (dataset) on a CKAN instance.
    '''
    try:
        kwargs = {'object': object, 'infile': infile, 'owner_orgs': owner_orgs}
        cmd = UploadCommand(context, **kwargs)
        result = cmd.execute(as_get=False)
        pprint(result)
    except CommandError as ex:
        log_error(ex, context, _log)


if __name__ == '__main__':
    ckanta()
