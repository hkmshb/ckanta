import logging
from .common import CKANTAError


_log = logging.getLogger()


class CommandError(CKANTAError):
    '''Expection raise for Command execution related errors.
    '''
    pass


class CommandBase:

    def __init__(self, api_client, **action_args):
        self._validate_action_args(action_args)
        self.api_client = api_client
        self.action_args = action_args

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

    def __init__(self, api_client, userid, check_group=False):
        super().__init__(api_client, object=self.COMMAND)
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
