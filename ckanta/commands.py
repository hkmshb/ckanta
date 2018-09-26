import csv
import logging
import itertools
from slugify import slugify
from collections import OrderedDict, namedtuple
from .common import CKANTAError


_log = logging.getLogger()


class CommandError(CKANTAError):
    '''Expection raise for Command execution related errors.
    '''
    pass


class CommandBase:

    def __init__(self, context, **action_args):
        self._validate_action_args(action_args)
        self.api_client = context.client
        self.action_args = action_args
        self.context = context

    def _validate_action_args(self, args):
        '''Validates that action args provided on the cli are valid.

        Subclasses should override to perform command specific checks.
        '''
        assert 'object' in args, 'Target object to be listed required'

        target_object = args.get('object', None)
        assert target_object in self.TARGET_OBJECTS, (
            'Invalid target object. Any of these expected: {}'.format(
                self.TARGET_OBJECTS
            ))

        # normalize object name; dataset in particular
        if target_object == 'dataset':
            args['object'] = 'package'


class ListCommand(CommandBase):
    '''Retrieve and list objects from a CKAN instance.
    '''
    TARGET_OBJECTS = ('dataset', 'group', 'organization', 'user')

    def _build_group_payload(self):
        payload = {
            'sort': 'name asc',
            'all_fields': False
        }
        payload.update(self.action_args)
        return payload

    def _build_organization_payload(self):
        payload = {
            'sort': 'name asc',
            'all_fields': False
        }
        payload.update(self.action_args)
        return payload

    def _build_package_payload(self):
        payload = {}
        payload.update(self.action_args)
        return payload

    def _build_user_payload(self):
        payload = {
            'all_fields': False
        }
        payload.update(self.action_args)
        return payload

    def execute(self, as_get=True):
        target_object = self.action_args.pop('object')
        action_name = '{}_list'.format(target_object)

        method_name = '_build_{}_payload'.format(target_object)
        if not hasattr(self, method_name):
            errmsg = 'Payload builder method not found: {}'
            raise CommandError(errmsg.format(method_name))

        payload = getattr(self, method_name)()
        _log.debug('action: {}, unified payload: {}'.format(
            action_name, payload
        ))
        try:
            result = self.api_client(action_name, payload, as_get=as_get)
        except Exception as ex:
            raise CommandError('API request failed.') from ex
        return result


class ShowCommand(CommandBase):
    '''Retrieve and show an object from a CKAN instance.
    '''
    TARGET_OBJECTS = ('dataset', 'group', 'organization', 'user')

    def _validate_action_args(self, args):
        '''Validates that action args provided on the cli are valid.
        '''
        super()._validate_action_args(args)
        id = args.get('id', None)
        assert id is not None, 'Target object Id required'

    def _build_dataset_payload(self):
        return {}

    def execute(self, as_get=True):
        object_id = self.action_args.pop('id')
        target_object = self.action_args.pop('object')
        action_name = '{}_show'.format(target_object)

        payload = {'id': object_id}
        try:
            result = self.api_client(action_name, payload, as_get=as_get)
        except Exception as ex:
            raise CommandError('API request failed.') from ex
        return result


class MembershipCommand(CommandBase):
    COMMAND = '::list'
    TARGET_OBJECTS = (COMMAND,)
    TARGET_ACTIONS = ('organization_list_for_user', 'group_list_authz')

    def __init__(self, context, userid, check_group=False):
        super().__init__(context, object=self.COMMAND)
        self.check_group = check_group
        self.userid = userid

    def execute(self, as_get):
        payload = {'id': self.userid}
        action_names = self.TARGET_ACTIONS
        _log.debug('action_names: {}; payload: {}'.format(
            action_names, payload)
        )

        results = []
        targets = action_names[:1] if not self.check_group else action_names
        try:
            for action_name in targets:
                title = action_name.split('_')[0]
                result = self.api_client(action_name, payload, as_get)
                results.append(result)
        except Exception as ex:
            raise CommandError('API request failed.') from ex
        return results


class UploadCommand(CommandBase):
    '''Creates an object on a CKAN instance.
    '''
    NATIONAL_KEY = 'national:'
    TARGET_OBJECTS = ('dataset',)

    @property
    def national_states(self):
        key = '__national_states'
        if not hasattr(self, key):
            states = OrderedDict()
            State = namedtuple('State', ['code', 'name'])

            value = self.context.get_config('national-states')
            for entry in itertools.chain(*[
                ln.split('  ') for ln in value.split('\n') if ln
            ]):
                code, name = entry.strip().split(':')
                name = name.replace("'", '').strip()
                states[slugify(name)] = State(code, name)

            setattr(self, key, states)
        return getattr(self, key)

    def _validate_action_args(self, args):
        '''Validates that action args provided on the cli are valid.

        Expects a file argument to be provided in addition to the object
        argument.
        '''
        # checks that object argument is provide
        super()._validate_action_args(args)

        # check that file argument is provided
        file_arg = args.get('infile', None)
        assert file_arg is not None, "'infile' argument expected"

    def _get_package_payload_factory(self, payload_method, file_obj):
        reader = csv.DictReader(file_obj, delimiter=',')
        owner_orgs = self.action_args.pop('owner_orgs', [])

        norm = lambda n: n.replace(self.NATIONAL_KEY, '')
        for row in reader:
            for orgname in owner_orgs:
                row.setdefault('owner_org', norm(orgname))
                row.setdefault('locations', norm(orgname))
                yield payload_method(row, orgname)

    def _build_package_payload(self, row_dict, orgname):
        # required: name, private, state:active, type:dataset, owner_org,
        #           sector_id, locations
        # adjust title
        if not orgname.startswith(self.NATIONAL_KEY):
            title = row_dict.pop('title')
            row_dict['title'] = '{} {}'.format(
                self.national_states[orgname].name,
                title
            )

        row_dict.setdefault('type', 'dataset')
        row_dict.setdefault('state', 'active')
        row_dict.setdefault('private', 'false')
        row_dict.setdefault('name', slugify(row_dict.get('title')))

        # use sector_id to define sector
        sector_id = row_dict.get('sector_id', '')
        row_dict['groups'] = [{'name': sector_id}]
        return row_dict

    def execute(self, as_get=True):
        file_obj = self.action_args.pop('infile')
        target_object = self.action_args.pop('object')
        action_name = '{}_create'.format(target_object)

        method_name = '_build_{}_payload'.format(target_object)
        if not hasattr(self, method_name):
            errmsg = 'Payload builder method not found: {}'
            raise CommandError(errmsg.format(method_name))

        payload_method = getattr(self, method_name)

        method_name = '_get_{}_payload_factory'.format(target_object)
        if not hasattr(self, method_name):
            errmsg = 'Payload factory method not found: {}'
            raise CommandError(errmsg.format(method_name))

        factory_method = getattr(self, method_name)
        _log.debug('action: {}, payload-method: {}, payload-factory: {}'.format(
            action_name, payload_method.__name__, factory_method.__name__)
        )

        factory = factory_method(payload_method, file_obj)
        passed, action_result = (0, [])
        for payload in factory:
            _log.debug('{} payload: {}'.format(target_object, payload))
            try:
                self.api_client(action_name, payload, as_get=False)
                action_result.append('+ {}'.format(payload.get('name', '?')))
                passed += 1
            except Exception as ex:
                _log.error('API request failed. {}'.format(ex))
                action_result.append('x {}'.format(payload.get('name', '?')))

        total_items = len(action_result)
        return {
            'result': action_result, 
            'summary': {
                'total': total_items, 'passed': passed,
                'failed': total_items - passed
            }
        }
