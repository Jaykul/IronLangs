"""Tests for distutils.command.sdist."""
import os
import unittest
import shutil
import zipfile
import tarfile

# zlib is not used here, but if it's not available
# the tests that use zipfile may fail
try:
    import zlib
except ImportError:
    zlib = None

try:
    import grp
    import pwd
    UID_GID_SUPPORT = True
except ImportError:
    UID_GID_SUPPORT = False

from os.path import join
import sys
import tempfile
import warnings

from test.test_support import check_warnings
from test.test_support import captured_stdout

from distutils.command.sdist import sdist
from distutils.command.sdist import show_formats
from distutils.core import Distribution
from distutils.tests.test_config import PyPIRCCommandTestCase
from distutils.errors import DistutilsExecError, DistutilsOptionError
from distutils.spawn import find_executable
from distutils.tests import support
from distutils.log import WARN
from distutils.archive_util import ARCHIVE_FORMATS

SETUP_PY = """
from distutils.core import setup
import somecode

setup(name='fake')
"""

MANIFEST = """\
README
inroot.txt
setup.py
data%(sep)sdata.dt
scripts%(sep)sscript.py
some%(sep)sfile.txt
some%(sep)sother_file.txt
somecode%(sep)s__init__.py
somecode%(sep)sdoc.dat
somecode%(sep)sdoc.txt
"""

class SDistTestCase(PyPIRCCommandTestCase):

    def setUp(self):
        # PyPIRCCommandTestCase creates a temp dir already
        # and put it in self.tmp_dir
        super(SDistTestCase, self).setUp()
        # setting up an environment
        self.old_path = os.getcwd()
        os.mkdir(join(self.tmp_dir, 'somecode'))
        os.mkdir(join(self.tmp_dir, 'dist'))
        # a package, and a README
        self.write_file((self.tmp_dir, 'README'), 'xxx')
        self.write_file((self.tmp_dir, 'somecode', '__init__.py'), '#')
        self.write_file((self.tmp_dir, 'setup.py'), SETUP_PY)
        os.chdir(self.tmp_dir)

    def tearDown(self):
        # back to normal
        os.chdir(self.old_path)
        super(SDistTestCase, self).tearDown()

    def get_cmd(self, metadata=None):
        """Returns a cmd"""
        if metadata is None:
            metadata = {'name': 'fake', 'version': '1.0',
                        'url': 'xxx', 'author': 'xxx',
                        'author_email': 'xxx'}
        dist = Distribution(metadata)
        dist.script_name = 'setup.py'
        dist.packages = ['somecode']
        dist.include_package_data = True
        cmd = sdist(dist)
        cmd.dist_dir = 'dist'
        def _warn(*args):
            pass
        cmd.warn = _warn
        return dist, cmd

    @unittest.skipUnless(zlib, "requires zlib")
    def test_prune_file_list(self):
        # this test creates a package with some vcs dirs in it
        # and launch sdist to make sure they get pruned
        # on all systems

        # creating VCS directories with some files in them
        os.mkdir(join(self.tmp_dir, 'somecode', '.svn'))
        self.write_file((self.tmp_dir, 'somecode', '.svn', 'ok.py'), 'xxx')

        os.mkdir(join(self.tmp_dir, 'somecode', '.hg'))
        self.write_file((self.tmp_dir, 'somecode', '.hg',
                         'ok'), 'xxx')

        os.mkdir(join(self.tmp_dir, 'somecode', '.git'))
        self.write_file((self.tmp_dir, 'somecode', '.git',
                         'ok'), 'xxx')

        # now building a sdist
        dist, cmd = self.get_cmd()

        # zip is available universally
        # (tar might not be installed under win32)
        cmd.formats = ['zip']

        cmd.ensure_finalized()
        cmd.run()

        # now let's check what we have
        dist_folder = join(self.tmp_dir, 'dist')
        files = os.listdir(dist_folder)
        self.assertEquals(files, ['fake-1.0.zip'])

        zip_file = zipfile.ZipFile(join(dist_folder, 'fake-1.0.zip'))
        try:
            content = zip_file.namelist()
        finally:
            zip_file.close()

        # making sure everything has been pruned correctly
        self.assertEquals(len(content), 4)

    @unittest.skipUnless(zlib, "requires zlib")
    def test_make_distribution(self):

        # check if tar and gzip are installed
        if (find_executable('tar') is None or
            find_executable('gzip') is None):
            return

        # now building a sdist
        dist, cmd = self.get_cmd()

        # creating a gztar then a tar
        cmd.formats = ['gztar', 'tar']
        cmd.ensure_finalized()
        cmd.run()

        # making sure we have two files
        dist_folder = join(self.tmp_dir, 'dist')
        result = os.listdir(dist_folder)
        result.sort()
        self.assertEquals(result,
                          ['fake-1.0.tar', 'fake-1.0.tar.gz'] )

        os.remove(join(dist_folder, 'fake-1.0.tar'))
        os.remove(join(dist_folder, 'fake-1.0.tar.gz'))

        # now trying a tar then a gztar
        cmd.formats = ['tar', 'gztar']

        cmd.ensure_finalized()
        cmd.run()

        result = os.listdir(dist_folder)
        result.sort()
        self.assertEquals(result,
                ['fake-1.0.tar', 'fake-1.0.tar.gz'])

    @unittest.skipUnless(zlib, "requires zlib")
    def test_add_defaults(self):

        # http://bugs.python.org/issue2279

        # add_default should also include
        # data_files and package_data
        dist, cmd = self.get_cmd()

        # filling data_files by pointing files
        # in package_data
        dist.package_data = {'': ['*.cfg', '*.dat'],
                             'somecode': ['*.txt']}
        self.write_file((self.tmp_dir, 'somecode', 'doc.txt'), '#')
        self.write_file((self.tmp_dir, 'somecode', 'doc.dat'), '#')

        # adding some data in data_files
        data_dir = join(self.tmp_dir, 'data')
        os.mkdir(data_dir)
        self.write_file((data_dir, 'data.dt'), '#')
        some_dir = join(self.tmp_dir, 'some')
        os.mkdir(some_dir)
        self.write_file((self.tmp_dir, 'inroot.txt'), '#')
        self.write_file((some_dir, 'file.txt'), '#')
        self.write_file((some_dir, 'other_file.txt'), '#')

        dist.data_files = [('data', ['data/data.dt',
                                     'inroot.txt',
                                     'notexisting']),
                           'some/file.txt',
                           'some/other_file.txt']

        # adding a script
        script_dir = join(self.tmp_dir, 'scripts')
        os.mkdir(script_dir)
        self.write_file((script_dir, 'script.py'), '#')
        dist.scripts = [join('scripts', 'script.py')]

        cmd.formats = ['zip']
        cmd.use_defaults = True

        cmd.ensure_finalized()
        cmd.run()

        # now let's check what we have
        dist_folder = join(self.tmp_dir, 'dist')
        files = os.listdir(dist_folder)
        self.assertEquals(files, ['fake-1.0.zip'])

        zip_file = zipfile.ZipFile(join(dist_folder, 'fake-1.0.zip'))
        try:
            content = zip_file.namelist()
        finally:
            zip_file.close()

        # making sure everything was added
        self.assertEquals(len(content), 11)

        # checking the MANIFEST
        manifest = open(join(self.tmp_dir, 'MANIFEST')).read()
        self.assertEquals(manifest, MANIFEST % {'sep': os.sep})

    @unittest.skipUnless(zlib, "requires zlib")
    def test_metadata_check_option(self):
        # testing the `medata-check` option
        dist, cmd = self.get_cmd(metadata={})

        # this should raise some warnings !
        # with the `check` subcommand
        cmd.ensure_finalized()
        cmd.run()
        warnings = self.get_logs(WARN)
        self.assertEquals(len(warnings), 2)

        # trying with a complete set of metadata
        self.clear_logs()
        dist, cmd = self.get_cmd()
        cmd.ensure_finalized()
        cmd.metadata_check = 0
        cmd.run()
        warnings = self.get_logs(WARN)
        self.assertEquals(len(warnings), 0)

    def test_check_metadata_deprecated(self):
        # makes sure make_metadata is deprecated
        dist, cmd = self.get_cmd()
        with check_warnings() as w:
            warnings.simplefilter("always")
            cmd.check_metadata()
            self.assertEquals(len(w.warnings), 1)

    def test_show_formats(self):
        with captured_stdout() as stdout:
            show_formats()

        # the output should be a header line + one line per format
        num_formats = len(ARCHIVE_FORMATS.keys())
        output = [line for line in stdout.getvalue().split('\n')
                  if line.strip().startswith('--formats=')]
        self.assertEquals(len(output), num_formats)

    def test_finalize_options(self):

        dist, cmd = self.get_cmd()
        cmd.finalize_options()

        # default options set by finalize
        self.assertEquals(cmd.manifest, 'MANIFEST')
        self.assertEquals(cmd.template, 'MANIFEST.in')
        self.assertEquals(cmd.dist_dir, 'dist')

        # formats has to be a string splitable on (' ', ',') or
        # a stringlist
        cmd.formats = 1
        self.assertRaises(DistutilsOptionError, cmd.finalize_options)
        cmd.formats = ['zip']
        cmd.finalize_options()

        # formats has to be known
        cmd.formats = 'supazipa'
        self.assertRaises(DistutilsOptionError, cmd.finalize_options)

    @unittest.skipUnless(zlib, "requires zlib")
    @unittest.skipUnless(UID_GID_SUPPORT, "Requires grp and pwd support")
    def test_make_distribution_owner_group(self):

        # check if tar and gzip are installed
        if (find_executable('tar') is None or
            find_executable('gzip') is None):
            return

        # now building a sdist
        dist, cmd = self.get_cmd()

        # creating a gztar and specifying the owner+group
        cmd.formats = ['gztar']
        cmd.owner = pwd.getpwuid(0)[0]
        cmd.group = grp.getgrgid(0)[0]
        cmd.ensure_finalized()
        cmd.run()

        # making sure we have the good rights
        archive_name = join(self.tmp_dir, 'dist', 'fake-1.0.tar.gz')
        archive = tarfile.open(archive_name)
        try:
            for member in archive.getmembers():
                self.assertEquals(member.uid, 0)
                self.assertEquals(member.gid, 0)
        finally:
            archive.close()

        # building a sdist again
        dist, cmd = self.get_cmd()

        # creating a gztar
        cmd.formats = ['gztar']
        cmd.ensure_finalized()
        cmd.run()

        # making sure we have the good rights
        archive_name = join(self.tmp_dir, 'dist', 'fake-1.0.tar.gz')
        archive = tarfile.open(archive_name)

        # note that we are not testing the group ownership here
        # because, depending on the platforms and the container
        # rights (see #7408)
        try:
            for member in archive.getmembers():
                self.assertEquals(member.uid, os.getuid())
        finally:
            archive.close()

    def test_get_file_list(self):
        # make sure MANIFEST is recalculated
        dist, cmd = self.get_cmd()

        # filling data_files by pointing files in package_data
        dist.package_data = {'somecode': ['*.txt']}
        self.write_file((self.tmp_dir, 'somecode', 'doc.txt'), '#')
        cmd.ensure_finalized()
        cmd.run()

        f = open(cmd.manifest)
        try:
            manifest = [line.strip() for line in f.read().split('\n')
                        if line.strip() != '']
        finally:
            f.close()

        self.assertEquals(len(manifest), 4)

        # adding a file
        self.write_file((self.tmp_dir, 'somecode', 'doc2.txt'), '#')

        # make sure build_py is reinitinialized, like a fresh run
        build_py = dist.get_command_obj('build_py')
        build_py.finalized = False
        build_py.ensure_finalized()

        cmd.run()

        f = open(cmd.manifest)
        try:
            manifest2 = [line.strip() for line in f.read().split('\n')
                         if line.strip() != '']
        finally:
            f.close()

        # do we have the new file in MANIFEST ?
        self.assertEquals(len(manifest2), 5)
        self.assertIn('doc2.txt', manifest2[-1])


def test_suite():
    return unittest.makeSuite(SDistTestCase)

if __name__ == "__main__":
    unittest.main(defaultTest="test_suite")
