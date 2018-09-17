import logging
from .common import CKANTAError


_log = logging.getLogger()


class CommandError(CKANTAError):
    '''Expection raise for Command execution related errors.
    '''
    pass


class ListCommand:
    '''Retrieve and list objects from a CKAN instance.
    '''
    TARGET_OBJECTS = ('group', 'organization')

    def __init__(self, api_client, **action_args):
        self._validate_cli_args(action_args)
        self.api_client = api_client
        self.action_args = action_args

    def _validate_cli_args(self, args):
        '''Validate that cli args provided for the `list` command are valid.
        '''
        assert 'object' in args, 'Target object to be listed required'
        assert args.get('object', None) in self.TARGET_OBJECTS, (
            'Invalid target object. Any of these expected: {}'.format(
                self.TARGET_OBJECTS
            ))

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

    def execute(self):
        target_object = self.action_args.pop('object')
        action_name = '{}_list'.format(target_object)

        method_name = '_build_{}_payload'.format(target_object)
        if not hasattr(self, method_name):
            errmsg = 'Payload builder method not found: {}'
            raise CommandError(errmsg.format(method_name))

        payload = getattr(self, method_name)()
        _log.debug('action: {}, payload: {}'.format(
            action_name, payload
        ))
        try:
            result = self.api_client(action_name, payload)
        except Exception as ex:
            raise CommandError('API request failed.') from ex

        return result
