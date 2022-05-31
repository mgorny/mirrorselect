#!/usr/bin/env python
# coding: utf-8

from __future__ import print_function


import logging
import re
import sys
import os
import io
import unittest
from setuptools import setup, Command


__version__ = os.getenv('VERSION', default=os.getenv('PVR', default='9999'))

cwd = os.getcwd()

# establish the eprefix, initially set so eprefixify can
# set it on install
EPREFIX = "@GENTOO_PORTAGE_EPREFIX@"

# check and set it if it wasn't
if "GENTOO_PORTAGE_EPREFIX" in EPREFIX:
    EPREFIX = ''


# Python files that need `version = ""` subbed, relative to this dir:
python_scripts = [os.path.join(cwd, path) for path in (
	'mirrorselect/version.py',
)]

manpage = [os.path.join(cwd, path) for path in (
	'mirrorselect.8',
)]


class set_version(Command):
	"""Set python version to our __version__."""
	description = "hardcode scripts' version using VERSION from environment"
	user_options = []  # [(long_name, short_name, desc),]

	def initialize_options (self):
		pass

	def finalize_options (self):
		pass

	def run(self):
		ver = 'git' if __version__ == '9999' else __version__
		print("Setting version to %s" % ver)
		def sub(files, pattern):
			for f in files:
				updated_file = []
				with io.open(f, 'r', 1, 'utf_8') as s:
					for line in s:
						newline = re.sub(pattern, '"%s"' % ver, line, 1)
						if newline != line:
							logging.info("%s: %s" % (f, newline))
						updated_file.append(newline)
				with io.open(f, 'w', 1, 'utf_8') as s:
					s.writelines(updated_file)
		quote = r'[\'"]{1}'
		python_re = r'(?<=^version = )' + quote + '[^\'"]*' + quote
		sub(python_scripts, python_re)
		man_re = r'(?<=^.TH "mirrorselect" "8" )' + quote + '[^\'"]*' + quote
		sub(manpage, man_re)


class TestCommand(Command):
	user_options = []

	def initialize_options(self):
		pass

	def finalize_options(self):
		pass

	def run(self):
		suite = unittest.TestSuite()
		tests = unittest.defaultTestLoader.discover('tests')
		suite.addTests(tests)
		result = unittest.TextTestRunner(verbosity=2).run(suite)
		if result.errors or result.failures:
			raise SystemExit(1)


test_data = {
	'mirrorselect': [
	]
}

setup(
	name='mirrorselect',
	version=__version__,
	description='Tool for selecting Gentoo source and rsync mirrors.',
	author='',
	author_email='',
	maintainer='Gentoo Portage Tools Team',
	maintainer_email='tools-portage@gentoo.org',
	url='http://www.gentoo.org/proj/en/portage/tools/index.xml',
	download_url='http://distfiles.gentoo.org/distfiles/mirrorselect-%s.tar.gz'\
		% __version__,
	packages=['mirrorselect'],
	#package_data = test_data,
	scripts=(['bin/mirrorselect']),
	data_files=(
		(os.path.join(os.sep, EPREFIX.lstrip(os.sep), 'usr/share/man/man8'),
		['mirrorselect.8']),
	),
	cmdclass={
		'test': TestCommand,
		'set_version': set_version,
	},
)

