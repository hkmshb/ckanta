import pkg_resources


def get_version():
    '''Retrieves the package version details.
    '''
    packages = pkg_resources.require('ckanta')
    return packages[0].version
