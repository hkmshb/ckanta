import re
import csv
import click
import logging
from itertools import chain
from urllib.parse import unquote

from furl import furl
from slugify import slugify
from collections import OrderedDict, namedtuple
from .common import CKANTAError, CKANObject, MembershipRole, ApiClient


_log = logging.getLogger()


class CommandError(CKANTAError):
    '''Expection raise for Command execution related errors.
    '''
    pass


class CommandBase:
    TARGET_OBJECTS = []

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
                # title = action_name.split('_')[0]
                result = self.api_client(action_name, payload, as_get)
                results.append(result)
        except Exception as ex:
            raise CommandError('API request failed.') from ex
        return results


class MembershipGrantCommand(CommandBase):
    TARGET_OBJECTS = ('user',)

    def __init__(self, context, userid, role, objects, object_type):
        super().__init__(context, object='user')
        self.role = MembershipRole.from_name(role)
        self.object_type = object_type
        self.objects = objects
        self.userid = userid

    def _get_access_request_payload(self, object_id, user_dict):
        return {
            'fullname': '{} (via CKANTA)'.format(user_dict['display_name']),
            'email': user_dict['email'],
            'contact_phone_number': '000-0000-0000'.replace('-', ''),
            'entity_id': object_id,
            'entity_type': 'dataset',
            'description': (
                'Access request initiated from CKAN task automation tool '
                'for official purpose.'),
            'org_name': user_dict['org_name'],
            'org_category': user_dict['org_category'],
            'country_state': user_dict['country_state']
        }

    def _create_membership(self, object_id):
        if self.role == MembershipRole.NONE:
            click.echo('Skipping operation as dropping membership (role=none) '
                       'is not supported yet')
            return

        role_name = self.role.name.lower()
        target_object = self.object_type.name.lower()
        action_name = '{}_member_create'.format(target_object)
        payload = {
            'id': object_id, 'username': self.userid, 
            'role': role_name
        }
        self.api_client(action_name, data=payload, as_get=False)

    def _grant_dataset_access(self):
        passed, action_result = (0, [])
        total = len(self.objects)
        result = {}

        # 1: first retrieve apikey for user to be granted access
        _log.info('Retrieving details for user requiring access...')
        try:
            action_name = 'user_show'
            result = self.api_client(action_name, {'id': self.userid}, False)
            result = result['result']
            _log.info('Requesting user details retrieved')
        except Exception as ex:
            _log.info('Failed retrieving details for user needing access')
            return self._build_result_summary(action_result, total, passed)

        # 2: make access request using retrieved user details
        fullname = result['display_name']
        _log.info("Making access request as '{}'".format(fullname))
        for objectid in self.objects:
            try:
                # make request as user whom needs access
                action_name = 'eoc_request_create'
                payload = self._get_access_request_payload(objectid, result)
                client = ApiClient(self.api_client.urlbase, result['apikey'])
                result = client(action_name, payload, False)
                request_id = result['result']['id']
                _log.info('Access request made for {}. Got: {}'.format(
                    objectid, request_id))

                # patch request as user running script
                action_name = 'eoc_request_patch'
                payload = {'id': request_id, 'status': 'approved'}
                result = self.api_client(action_name, payload, False)
                _log.info('Access request granted\n')

                passed += 1
            except Exception as ex:
                action_result.append('. {}: err: {}'.format(objectid, ex))

        result = self._build_result_summary(action_result, total, passed)
        return result

    def _build_result_summary(self, action_result, total, passed):
        return {
            'result': action_result,
            'summary': {
                'total': total, 'passed': passed, 'failed': total - passed
            }
        }

    def execute(self, as_get):
        if self.object_type == CKANObject.DATASET:
            result = self._grant_dataset_access()
        elif self.object_type in (CKANObject.GROUP, CKANObject.ORGANIZATION):
            passed, action_result = (0, [])
            for obj in self.objects:
                try:
                    self._create_membership(obj)
                    action_result.append('+ {}'.format(obj))
                    passed += 1
                except Exception as ex:
                    action_result.append('. {}: err: {}'.format(obj, ex))
            
            total = len(self.objects)
            result = self._build_result_summary(action_result, total, passed)
        return result


class UploadCommand(CommandBase):
    '''Creates an object on a CKAN instance.
    '''
    NATIONAL_KEY = 'national:'
    TARGET_OBJECTS = ('group', 'organization')

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

    def _get_group_payload_factory(self, payload_method, file_obj):
        reader = csv.DictReader(file_obj, delimiter=',')
        for row in reader:
            yield payload_method(row)

    def _build_group_payload(self, row_dict):
        row_dict.setdefault('state', 'active')
        row_dict.setdefault('name', slugify(row_dict.get('title')))
        return row_dict

    def _get_organization_payload_factory(self, payload_method, file_obj):
        reader = csv.DictReader(file_obj, delimiter=',')
        extras = list(filter(lambda k: k.startswith('extras:'), reader.fieldnames))
        for row in reader:
            yield payload_method(row, extras)

    def _build_organization_payload(self, row_dict, extras=None):
        row_dict.setdefault('state', 'active')
        row_dict.setdefault('name', slugify(row_dict.get('title')))

        # handle extras
        extras_list = []
        for entry in (extras or []):
            _, field = [e for e in entry.split(':') if e][:2]
            value = row_dict.pop(entry)
            if value:
                extras_list.append({
                    'key': field, 
                    'value': value
                })

        if extras_list:
            row_dict['extras'] = extras_list
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


class UploadDatasetCommand(CommandBase):
    '''Create datasets on a CKAN instance.
    '''
    VARTAG_STATE = '${state_code}'
    REPTTN_STATE = re.compile("state(?:code|_code)='(.+)'")
    NATIONAL_KEY = 'national:'
    TARGET_OBJECTS = ('dataset',)
    TARGET_FORMATS = {
        'CSV': 'csv',
        'JSON': 'application/json',
        'GeoJSON': 'application/json',
    }

    def __init__(self, context, infile, owner_orgs, urlbase, authkey, format):
        super().__init__(context, object=self.TARGET_OBJECTS[0])
        self.infile = infile
        self.urlbase = urlbase
        self.authkey = authkey
        self.format = format

        if not isinstance(owner_orgs, (list, tuple)):
            owner_orgs = owner_orgs.split(',')
        self.owner_orgs = owner_orgs

    def _get_package_payload_factory(self, payload_method, file_obj):
        reader = csv.DictReader(file_obj, delimiter=',')

        norm = lambda n: n.replace(self.NATIONAL_KEY, '')
        for row in reader:
            for orgname in self.owner_orgs:
                row.setdefault('owner_org', norm(orgname))
                row.setdefault('locations', norm(orgname))
                yield payload_method(row, orgname)

    def _build_package_payload(self, row_dict, orgname):
        ## required package attributes:
        #   name, private, state:active, type:dataset, owner_org,
        #   sector_id, locations

        # adjust title
        if not orgname.startswith(self.NATIONAL_KEY):
            title = row_dict.pop('title')
            row_dict['title'] = '{} {}'.format(
                self.context.national_states[orgname].name,
                title
            )

        row_dict.setdefault('type', 'dataset')
        row_dict.setdefault('state', 'active')
        row_dict.setdefault('private', 'false')
        row_dict.setdefault('name', slugify(row_dict.get('title')))

        # use sector_id to define sector
        sector_id = row_dict.get('sector_id', '')
        row_dict['groups'] = [{'name': sector_id}]

        ## build resource
        res_dict = self._build_resource_payload(row_dict, orgname)
        if res_dict:
            row_dict['resources'] = [res_dict]

        return row_dict

    def _build_resource_payload(self, row_dict, orgname):
        ## required resource attributes
        #     res:name, res:url, 
        ## optinal resource attributes
        #     res:description
        res_dict = {
            k[4:]: row_dict[k]
            for k in row_dict.keys()
            if k.startswith('res:') and k[4:] and row_dict[k]
        }
        if not res_dict or 'url' not in res_dict:
            return

        # if name not provided use package title
        org_fullname = self.context.national_states[orgname].name
        pkg_title = row_dict.get('title')
        if org_fullname in pkg_title:
            pkg_title = pkg_title.replace(org_fullname, '').strip()
        res_dict.setdefault('name', pkg_title)

        # process url further
        built_url = self._build_resource_url(res_dict['url'], orgname)
        res_dict['url'] = built_url
        return res_dict

    def _build_resource_url(self, res_url, orgname):
        built_url = None
        if res_url.startswith('http'):
            built_url = furl(unquote(res_url))
        else:
            config_name = 'grid-geoserver-urlbase'
            urlbase = self.urlbase or self.context.get_config(config_name)
            if not urlbase:
                raise CKANTAError(
                    "Please provide '-u/--urlbase' option or set "
                    "'{0}' in the config file".format(config_name)
                )
            built_url = furl(urlbase)

            # add in what we currently have as res_url
            for (key, value) in zip(
                ('typeName', 'CQL_FILTER'),
                [p.strip() for p in res_url.split(';')]
            ):
                built_url.args[key] = value

        # add in other stuff from config
        for qryparam in (
            'service', 'version', 'request', 'outputFormat', 'authkey'
        ):
            if qryparam not in built_url.args:
                conf_key = 'grid-geoserver-{}'.format(qryparam)
                value = self.context.get_config(conf_key)
                if not value:
                    raise CKANTAError(
                        "Please set '{0}' in the config file".format(conf_key)
                    )
                built_url.args[qryparam] = value

        # overwrite query params provide on the cli
        for (param_key, param_value) in (
            ('outputFormat', self.format), ('authkey', self.authkey)
        ):
            if param_value:
                built_url.args[param_key] = param_value

        # replace state_code in CQL_FILTER
        cql_filter = built_url.args['CQL_FILTER']
        state_code = self.context.national_states[orgname].code
        if self.VARTAG_STATE in cql_filter:
            cql_filter = cql_filter.replace(self.VARTAG_STATE, state_code)
            built_url.args['CQL_FILTER'] = cql_filter
        else:
            match = self.REPTTN_STATE.search(cql_filter)
            if match:
                found = match.groups()[0]
                cql_filter = cql_filter.replace(found, state_code)
                built_url.args['CQL_FILTER'] = cql_filter
        return built_url.url

    def execute(self, as_get=True):
        file_obj = self.infile
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


class PurgeCommand(CommandBase):
    """Purge existing objects on a CKAN instance.
    """
    TARGET_OBJECTS = ('dataset', 'group')

    def __init__(self, context, object, infile, ids):
        super().__init__(context, object=object)
        self.infile = infile
        self.ids = ids

    def execute(self, as_get=False):
        target_object = self.action_args.pop('object')
        target_object = target_object.replace('package', 'dataset')
        action_name = '{}_purge'.format(target_object)

        ids_list = list(filter(
            lambda id: id and id.strip() != "",
            chain(*[id.split(',') for id in self.ids])
        ))

        if self.infile:
            lines = self.infile.readlines()
            ids_list.extend([ln.strip() for ln in lines])

        result = []
        for obj_id in ids_list:
            try:
                self.api_client(action_name, {'id': obj_id}, as_get=as_get)
                result.append('+ {}'.format(obj_id))
            except Exception as ex:
                result.append('. {}'.format(obj_id))
        return result
