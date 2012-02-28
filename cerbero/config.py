# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import logging
import os

from cerbero import enums
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import _, system_info


CONFIG_DIR = os.path.expanduser('~/.cerbero')
CONFIG_EXT = 'cbc'
PROPS_FILENAME = 'properties.%s' % CONFIG_EXT
USER_PROPS_FILE = os.path.join(CONFIG_DIR, PROPS_FILENAME)
GIT_ROOT = 'git://git.keema.collabora.co.uk/gst-sdk/'
CERBERO_UNINSTALLED = 'CERBERO_UNINSTALLED'


Platform = enums.Platform
Architecture = enums.Architecture
Distro = enums.Distro


class Config (object):

    _properties = ['platform', 'target_platform', 'arch', 'target_arch',
                   'prefix', 'recipes_dir', 'host', 'build', 'target',
                   'sources', 'local_sources', 'lib_suffix', 'git_root',
                   'distro', 'environ_dir', 'toolchain_prefix']

    def __init__(self, filename=None):
        if filename is None:
            filename = USER_PROPS_FILE
        self.filename = filename

        self._check_uninstalled()
        self.load_defaults()
        if not os.path.exists(self.filename):
            msg = _('Using default configuration because %s is missing') % \
                    self.filename
            logging.warning(msg)
        else:
            self.parse(self.filename)
        self.setup_env()
        self._load_platform_config()

    def parse(self, filename, reset=True):
        if reset:
            config = {}
        else:
            config = {}
            for prop in self._properties:
                if hasattr(self, prop):
                    config[prop] = getattr(self, prop)

        try:
            execfile(filename, config)
            self.__file__ = self.filename
        except:
            raise FatalError(_('Could not include config file (%s)') %
                             filename)
        for key in self._properties:
            if key in config:
                self.set_property(key, config[key])
        os.environ['CERBERO_PREFIX'] = self.prefix

    def setup_env(self):
        self._create_path(self.prefix)

        libdir = os.path.join(self.prefix, 'lib%s' % self.lib_suffix)
        self.libdir = libdir

        # Get paths for environment variables
        includedir = os.path.join(self.prefix, 'include')
        bindir = os.path.join(self.prefix, 'bin')
        manpathdir = os.path.join(self.prefix, 'share', 'man')
        infopathdir = os.path.join(self.prefix, 'share', 'info')
        pkgconfigdatadir = os.path.join(self.prefix, 'share', 'pkgconfig')
        pkgconfigdir = os.path.join(libdir, 'pkgconfig')
        typelibpath = os.path.join(self.libdir, 'girepository-1.0')
        xdgdatadir = os.path.join(self.prefix, 'share')
        xdgconfigdir = os.path.join(self.prefix, 'etc', 'xdg')
        xcursordir = os.path.join(self.prefix, 'share', 'icons')
        aclocaldir = os.path.join(self.prefix, 'share', 'aclocal')
        perl5lib = os.path.join(self.prefix, 'lib', 'perl5')

        self._create_path(aclocaldir)

        # Most of these variables are extracted from jhbuild
        # FIXME: add python when needed
        env = {'LD_LIBRARY_PATH': libdir,
               'LDFLAGS': '-L%s %s' % (libdir,  os.environ.get('LDFLAGS', '')),
               'C_INCLUDE_PATH': includedir,
               'CPLUS_INCLUDE_PATH': includedir,
               'DYLD_FALLBACK_LIBRARY_PATH': libdir,
               'PATH': self._join_path('PATH', bindir),
               'MANPATH': manpathdir,
               'INFOPATH': infopathdir,
               'PKG_CONFIG_PATH': '%s' % pkgconfigdatadir,
               'PKG_CONFIG_LIBDIR': '%s' % pkgconfigdir,
               'GI_TYPELIB_PATH': typelibpath,
               'XDG_DATA_DIRS': xdgdatadir,
               'XDG_CONFIG_DIRS': xdgconfigdir,
               'XCURSOR_PATH': xcursordir,
               #'ACLOCAL': aclocaldir,
               'PERL5LIB': perl5lib,
               'MONO_PREFIX': self.prefix,
               'MONO_GAC_PREFIX': self.prefix,
               }

        # set all the variables
        self.env = env
        for e, v in env.iteritems():
            os.environ[e] = v

    def _check_uninstalled(self):
        self.uninstalled = int(os.environ.get(CERBERO_UNINSTALLED, 0)) == 1

    def _create_path(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
                raise FatalError(_('directory (%s) can not be created') % path)

    def _join_path(self, env, path):
        if env not in os.environ:
            return path
        else:
            return "%s:%s" % (path, os.environ['PATH'])

    def _load_platform_config(self):
        platform_config = os.path.join(self.environ_dir, '%s.config' %
                                       self.target_platform)
        arch_config = os.path.join(self.environ_dir, '%s_%s.config' %
                                   (self.target_platform, self.target_arch))

        for config in [platform_config, arch_config]:
            if os.path.exists(config):
                self.parse(config, reset=False)

    def load_defaults(self):
        cerbero_home = os.path.expanduser('~/cerbero')
        self.set_property('prefix', os.path.join(cerbero_home, 'dist'))
        self.set_property('sources', os.path.join(cerbero_home, 'sources'))
        self.set_property('local_sources', os.path.join(self.sources, 'local'))
        if not self.uninstalled:
            self.set_property('recipes_dir',
                              os.path.join(cerbero_home, 'recipes'))
        else:
            self.set_property('recipes_dir',
                os.path.join(os.path.dirname(__file__), '..', 'recipes'))
        self.set_property('git_root', GIT_ROOT)
        self.set_property('host', None)
        self.set_property('build', None)
        self.set_property('target', None)
        platform, arch, distro = system_info()
        self.set_property('platform', platform)
        self.set_property('target_platform', platform)
        self.set_property('arch', arch)
        self.set_property('target_arch', arch)
        self.set_property('distro', distro)
        self.set_property('lib_suffix', '')
        if not self.uninstalled:
            self.set_property('environ_dir', os.path.join(CONFIG_DIR))
        else:
            self.set_property('environ_dir',
                os.path.join(os.path.dirname(__file__), '..', 'config'))

    def set_property(self, name, value):
        if name not in self._properties:
            raise ConfigurationError('Unkown key %s' % name)
        setattr(self, name, value)
