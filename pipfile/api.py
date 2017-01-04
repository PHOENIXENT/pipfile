import json
import hashlib
import platform
import sys
import os
from collections import OrderedDict


def format_full_version(info):
    version = '{0.major}.{0.minor}.{0.micro}'.format(info)
    kind = info.releaselevel
    if kind != 'final':
        version += kind[0] + str(info.serial)
    return version


def walk_up(bottom):
    """mimic os.walk, but walk 'up' instead of down the directory tree.
    From: https://gist.github.com/zdavkeos/1098474
    """

    bottom = os.path.realpath(bottom)

    # get files in current dir
    try:
        names = os.listdir(bottom)
    except Exception as e:
        print e
        return

    dirs, nondirs = [], []
    for name in names:
        if os.path.isdir(os.path.join(bottom, name)):
            dirs.append(name)
        else:
            nondirs.append(name)

    yield bottom, dirs, nondirs

    new_path = os.path.realpath(os.path.join(bottom, '..'))

    # see if we are at the top
    if new_path == bottom:
        return

    for x in walk_up(new_path):
        yield x



class PipfileParser(object):
    def __init__(self, filename='Pipfile'):
        self.filename = filename
        self.sources = []
        self.groups = OrderedDict({
            'default': [],
            'develop': []
        })
        self.group_stack = ['default']
        self.requirements = []

    def __repr__(self):
        return '<PipfileParser path={0!r}'.format(self.filename)

    def parse(self):
        with open(self.filename) as f:
            content = f.read()
        exec(content, {'__builtins__': None}, self.locals)
        data = OrderedDict({
            '_meta': {
                'sources': self.sources,
                'requires': self.requirements
            },
        })
        data.update(self.groups)
        return data

    @property
    def locals(self):
        return {
            'source': self.add_source,
            'package': self.add_package,
            'dev_package': self.add_dev_package,
            'requires': self.requires,
            'requires_python': self.requires_python,
            'True': True,
            'False': False,
        }

    def add_source(self, url, **kwargs):
        source = OrderedDict({'url': url})
        source.update(kwargs)
        self.sources.append(source)

    def add_package(self, name, version=None, **kwargs):
        package = OrderedDict()
        package['name'] = name
        if version:
            package['version'] = version
        package.update(kwargs)
        self.groups['default'].append(package)

    def add_dev_package(self, name, version=None, **kwargs):
        package = OrderedDict()
        package['name'] = name
        if version:
            package['version'] = version
        package.update(kwargs)
        self.groups['develop'].append(package)

    def requires(self, marker, specifier):
        requirement = OrderedDict()
        requirement['marker'] = marker
        requirement['specifier'] = specifier
        self.requirements.append(requirement)

    def requires_python(self, python_version):
        self.requires('python_version', python_version)

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        self.group_stack.pop()


class Pipfile(object):
    def __init__(self, filename):
        super(Pipfile, self).__init__()
        self.filename = filename
        self.data = None

    @staticmethod
    def find(max_depth=3):
        """Returns the path of a Pipfile in parent directories."""
        i = 0
        for c, d, f in walk_up(os.getcwd()):
            i += 1

            if i < max_depth:
                if 'Pipfile':
                    return '{}/Pipfile'.format(c)

    @classmethod
    def load(klass, filename):
        """Load a Pipfile from a given filename."""
        p = PipfileParser(filename=filename)
        pipfile = klass(filename=filename)
        pipfile.data = p.parse()
        return pipfile

    @property
    def hash(self):
        """Returns the SHA256 of the pipfile."""
        return hashlib.sha256(self.contents).hexdigest()

    @property
    def contents(self):
        """Returns the contents of the pipfile."""
        with open(self.filename, 'r') as f:
            return f.read()

    def freeze(self):
        """Returns a JSON representation of the Pipfile."""
        data = self.data
        data['_meta']['Pipfile-sha256'] = self.hash
        return json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))

    def assert_requirements(self):
        """"Asserts PEP 508 specifiers."""

        # Support for 508's implementation_version.
        if hasattr(sys, 'implementation'):
            implementation_version = format_full_version(sys.implementation.version)
        else:
            implementation_version = "0"

        # Default to cpython for 2.7.
        if hasattr(sys, 'implementation'):
            implementation_name = sys.implementation.name
        else:
            implementation_name = 'cpython'

        lookup = {
            'os_name': os.name,
            'sys_platform': sys.platform,
            'platform_machine': platform.machine(),
            'platform_python_implementation': platform.python_implementation(),
            'platform_release': platform.release(),
            'platform_system': platform.system(),
            'platform_version': platform.version(),
            'python_version': platform.python_version()[:3],
            'python_full_version': platform.python_version(),
            'implementation_name': implementation_name,
            'implementation_version': implementation_version
        }

        # Assert each specified requirement.
        for requirement in self.data['_meta']['requires']:
            marker = requirement['marker']
            specifier = requirement['specifier']

            if marker in lookup:
                try:
                    assert lookup[marker] == specifier
                except AssertionError:
                    raise AssertionError('Specifier {!r} does not match {!r}.'.format(marker, specifier))



def load(pipfile_path):
    return Pipfile.load(filename=pipfile_path)