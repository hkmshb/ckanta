import pkg_resources


def get_version():
    '''Retrieves the package version details.
    '''
    import pkg_resources
    packages = pkg_resources.require('ckanta')
    return packages[0].version
