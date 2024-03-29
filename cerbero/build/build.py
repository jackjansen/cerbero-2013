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

import os

from cerbero.config import Platform, Architecture, Distro
from cerbero.utils import shell, to_unixpath
from cerbero.utils import messages as m
import shutil


class Build (object):
    '''
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    _properties_keys = []

    def configure(self):
        '''
        Configures the module
        '''
        raise NotImplemented("'configure' must be implemented by subclasses")

    def compile(self):
        '''
        Compiles the module
        '''
        raise NotImplemented("'make' must be implemented by subclasses")

    def install(self):
        '''
        Installs the module
        '''
        raise NotImplemented("'install' must be implemented by subclasses")

    def check(self):
        '''
        Runs any checks on the module
        '''
        pass


class CustomBuild(Build):

    def configure(self):
        pass

    def compile(self):
        pass

    def install(self):
        pass


def modify_environment(func):
    ''' Decorator to modify the build environment '''
    def call(*args):
        self = args[0]
        append_env = self.append_env
        new_env = self.new_env.copy()
        if self.use_system_libs and self.config.allow_system_libs:
            self._add_system_libs(new_env)
        old_env = self._modify_env(append_env, new_env)
        res = func(*args)
        self._restore_env(old_env)
        return res

    call.func_name = func.func_name
    return call


class MakefilesBase (Build):
    '''
    Base class for makefiles build systems like autotools and cmake
    '''

    config_sh = ''
    configure_tpl = ''
    configure_options = ''
    force_configure = False
    make = 'make'
    make_install = 'make install'
    make_check = None
    make_clean = 'make clean'
    use_system_libs = False
    allow_parallel_build = True
    srcdir = '.'
    append_env = None
    new_env = None

    def __init__(self):
        Build.__init__(self)
        if self.append_env is None:
            self.append_env = {}
        if self.new_env is None:
            self.new_env = {}
        self.make_dir = os.path.abspath(os.path.join(self.build_dir,
                                                     self.srcdir))
        if self.config.allow_parallel_build and self.allow_parallel_build \
                and self.config.num_of_cpus > 1:
            self.make += ' -j%d' % self.config.num_of_cpus
        self._old_env = None

    @modify_environment
    def configure(self):
        shell.call(self.configure_tpl % {'config-sh': self.config_sh,
            'prefix': to_unixpath(self.config.prefix),
            'libdir': to_unixpath(self.config.libdir),
            'host': self.config.host,
            'target': self.config.target,
            'build': self.config.build,
            'options': self.configure_options},
            self.make_dir)

    @modify_environment
    def compile(self):
        shell.call(self.make, self.make_dir)

    @modify_environment
    def install(self):
        shell.call(self.make_install, self.make_dir)

    @modify_environment
    def clean(self):
        shell.call(self.make_clean, self.make_dir)

    @modify_environment
    def check(self):
        if self.make_check:
            shell.call(self.make_check, self.build_dir)

    def _modify_env(self, append_env, new_env):
        '''
        Modifies the build environment appending the values in
        append_env or replacing the values in new_env
        '''
        if self._old_env is not None:
            return None

        self._old_env = {}
        for var in append_env.keys() + new_env.keys():
            self._old_env[var] = os.environ.get(var, None)

        for var, val in append_env.iteritems():
            os.environ[var] = os.environ.get(var, '') + val

        for var, val in new_env.iteritems():
            if val is None:
                del os.environ[var]
            else:
                os.environ[var] = val
        return self._old_env

    def _restore_env(self, old_env):
        ''' Restores the old environment '''
        if old_env is None:
            return

        for var, val in old_env.iteritems():
            if val is None:
                del os.environ[var]
            else:
                os.environ[var] = val
        self._old_env = None

    def _add_system_libs(self, new_env):
        '''
        Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
        can be found.
        '''
        arch = self.config.target_arch
        libdir = 'lib'
        if arch == Architecture.X86:
            arch = 'i386'
        else:
            if self.config.distro == Distro.REDHAT:
                libdir = 'lib64'
        search_paths = [os.environ['PKG_CONFIG_LIBDIR'],
            '/usr/%s/pkgconfig' % libdir, '/usr/share/pkgconfig',
            '/usr/lib/%s-linux-gnu/pkgconfig' % arch]
        new_env['PKG_CONFIG_PATH'] = ':'.join(search_paths)


class Autotools (MakefilesBase):
    '''
    Build handler for autotools project
    '''

    autoreconf = False
    autoreconf_sh = 'autoreconf -f -i'
    config_sh = './configure'
    configure_tpl = "%(config-sh)s --prefix %(prefix)s "\
                    "--libdir %(libdir)s %(options)s"
    make_check = 'make check'
    add_host_build_target = True
    can_use_configure_cache = True
    supports_cache_variables = True

    def configure(self):
        if self.supports_non_src_build:
            self.config_sh = os.path.join(self.repo_dir, self.config_sh)
        # skip configure if we are already configured
        if os.path.exists(os.path.join(self.make_dir, 'configure')) and\
                os.path.exists(os.path.join(self.make_dir, 'Makefile')):
            if not self.force_configure and not self.force:
                return

        # Only use --disable-maintainer mode for real autotools based projects
        if os.path.exists(os.path.join(self.make_dir, 'configure.in')) or\
                os.path.exists(os.path.join(self.make_dir, 'configure.ac')):
            self.configure_tpl += " --disable-maintainer-mode "
            self.configure_tpl += " --disable-silent-rules "

        if self.autoreconf:
            shell.call(self.autoreconf_sh, self.make_dir)

        files = shell.check_call('find %s -type f -name config.guess' %
                                 self.make_dir).split('\n')
        files.remove('')
        for f in files:
            o = os.path.join(self.config._relative_path('data'), 'autotools',
                             'config.guess')
            m.action("copying %s to %s" % (o, f))
            shutil.copy(o, f)

        files = shell.check_call('find %s -type f -name config.sub' %
                                 self.make_dir).split('\n')
        files.remove('')
        for f in files:
            o = os.path.join(self.config._relative_path('data'), 'autotools',
                             'config.sub')
            m.action("copying %s to %s" % (o, f))
            shutil.copy(o, f)

        if self.config.platform == Platform.WINDOWS and \
                self.supports_cache_variables:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in os.environ.iteritems():
                if k[2:6] == '_cv_':
                    self.configure_tpl += ' %s="%s"' % (k, v)

        if self.add_host_build_target:
            if self.config.host is not None:
                self.configure_tpl += ' --host=%(host)s'
            if self.config.build is not None:
                self.configure_tpl += ' --build=%(build)s'
            if self.config.target is not None:
                self.configure_tpl += ' --target=%(target)s'

        use_configure_cache = self.config.use_configure_cache
        if self.use_system_libs and self.config.allow_system_libs:
            use_configure_cache = False

        if self.new_env or self.append_env:
            use_configure_cache = False

        if use_configure_cache and self.can_use_configure_cache:
            cache = os.path.join(self.config.sources, '.configure.cache')
            self.config_sh += ' --cache-file=%s' % cache

        MakefilesBase.configure(self)


class CMake (MakefilesBase):
    '''
    Build handler for cmake projects
    '''

    config_sh = 'cmake'
    configure_tpl = '%(config-sh)s -DCMAKE_INSTALL_PREFIX=%(prefix)s '\
                    '-DCMAKE_LIBRARY_OUTPUT_PATH=%(libdir)s %(options)s '\
                    '-DCMAKE_BUILD_TYPE=Release '\
                    '-DCMAKE_FIND_ROOT_PATH=$CERBERO_PREFIX '

    @modify_environment
    def configure(self):
        cc = os.environ.get('CC', 'gcc')
        cxx = os.environ.get('CXX', 'g++')
        cflags = os.environ.get('CFLAGS', '')
        cxxflags = os.environ.get('CXXFLAGS', '')
        # FIXME: CMake doesn't support passing "ccache $CC"
        if self.config.use_ccache:
            cc = cc.replace('ccache ', '')
            cxx = cxx.replace('ccache ', '')

        if self.config.target_platform == Platform.WINDOWS:
            self.configure_options += ' -DCMAKE_C_COMPILER=%s '\
                                      ' -DCMAKE_CXX_COMPILER=%s '\
                                      ' -DCMAKE_SYSTEM_NAME=Windows '\
                                      % (cc, cxx)
        if self.config.platform == Platform.WINDOWS:
            self.configure_options += ' -G\\"Unix Makefiles\\"'
        self.configure_options += ' -DCMAKE_C_FLAGS="%s"' % cflags
        self.configure_options += ' -DCMAKE_CXX_FLAGS="%s"' % cxxflags
        self.configure_options += ' -DLIB_SUFFIX=%s ' % self.config.lib_suffix
        MakefilesBase.configure(self)


class BuildType (object):

    CUSTOM = CustomBuild
    MAKEFILE = MakefilesBase
    AUTOTOOLS = Autotools
    CMAKE = CMake
