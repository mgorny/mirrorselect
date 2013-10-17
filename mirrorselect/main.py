#!/usr/bin/env python
#-*- coding:utf-8 -*-


"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2005-2012 Gentoo Foundation

	Copyright (C) 2005 Colin Kingsley <tercel@gentoo.org>
	Copyright (C) 2008 Zac Medico <zmedico@gentoo.org>
	Copyright (C) 2009 Sebastian Pipping <sebastian@pipping.org>
	Copyright (C) 2009 Christian Ruppert <idl0r@gentoo.org>
	Copyright (C) 2012 Brian Dolbec <dolsen@gentoo.org>

Distributed under the terms of the GNU General Public License v2
 This program is free software; you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, version 2 of the License.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

"""


from __future__ import print_function


import os
import socket
import sys
from optparse import OptionParser
from mirrorselect.mirrorparser3 import MIRRORS_3_XML, MIRRORS_RSYNC_DATA
from mirrorselect.output import Output, ColoredFormatter
from mirrorselect.selectors import Deep, Shallow, Interactive
from mirrorselect.extractor import Extractor
from mirrorselect.configs import (get_make_conf_path, write_make_conf,
	write_repos_conf, get_filesystem_mirrors)
from mirrorselect.version import version

# eprefix compatibility
try:
	from portage.const import rootuid
except ImportError:
	rootuid = 0


# establish the eprefix, initially set so eprefixify can
# set it on install
EPREFIX = "@GENTOO_PORTAGE_EPREFIX@"

# check and set it if it wasn't
if "GENTOO_PORTAGE_EPREFIX" in EPREFIX:
    EPREFIX = ''


class MirrorSelect(object):
	'''Main operational class'''

	def __init__(self, output=None):
		'''MirrorSelect class init

		@param output: mirrorselect.output.Ouptut() class instance
			or None for the default instance
		'''
		self.output = output or Output()


	@staticmethod
	def _have_bin(name):
		"""Determines whether a particular binary is available
		on the host system.  It searches in the PATH environment
		variable paths.

		@param name: string, binary name to search for
		@rtype: string or None
		"""
		for path_dir in os.environ.get("PATH", "").split(":"):
			if not path_dir:
				continue
			file_path = os.path.join(path_dir, name)
			if os.path.isfile(file_path) and os.access(file_path, os.X_OK):
				return file_path
		return None


	def change_config(self, hosts, out, config_path, sync=False):
		"""Writes the config changes to the given file, or to stdout.

		@param hosts: list of host urls to write
		@param out: boolean, used to redirect output to stdout
		@param config_path; string
		@param sync: boolean, used to switch between sync-uri repos.conf target,
			SYNC and GENTOO_MIRRORS make.conf variable target
		"""
		if sync:
			if 'repos.conf' in config_path:
				var = "sync-uri"
			else:
				var = 'SYNC'
		else:
			var = 'GENTOO_MIRRORS'

		if hasattr(hosts[0], 'decode'):
			hosts = [x.decode('utf-8') for x in hosts]

		if var == "sync-uri" and out:
			mirror_string = '%s = %s' % (var, ' '.join(hosts))
		else:
			mirror_string = '%s="%s"' % (var, ' '.join(hosts))

		if out:
			self.write_to_output(mirror_string)
		elif var == "sync-uri":
			write_repos_conf(self.output, config_path, var, ' '.join(hosts))
		else:
			write_make_conf(self.output, config_path, var, mirror_string)


	@staticmethod
	def write_to_output(mirror_string):
		print()
		print(mirror_string)
		sys.exit(0)


	def _parse_args(self, argv, config_path):
		"""
		Does argument parsing and some sanity checks.
		Returns an optparse Options object.

		The descriptions, grouping, and possibly the amount sanity checking
		need some finishing touches.
		"""
		desc = "\n".join((
				self.output.white("examples:"),
				"",
				self.output.white("	 automatic:"),
				"		 # mirrorselect -s5",
				"		 # mirrorselect -s3 -b10 -o >> /mnt/gentoo/etc/portage/make.conf",
				"		 # mirrorselect -D -s4",
				"",
				self.output.white("	 interactive:"),
				"		 # mirrorselect -i -r",
				))
		parser = OptionParser(
			formatter=ColoredFormatter(self.output), description=desc,
			version='Mirrorselect version: %s' % version)

		group = parser.add_option_group("Main modes")
		group.add_option(
			"-a", "--all_mirrors", action="store_true", default=False,
			help="This will present a list of all filtered search results "
			"to make it possible to select mirrors you wish to use. "
			" For the -r, --rsync option, it will select the rotation server "
			"only. As multiple rsync URL's are not supported.")
		group.add_option(
			"-i", "--interactive", action="store_true", default=False,
			help="Interactive Mode, this will present a list "
			"to make it possible to select mirrors you wish to use.")
		group.add_option(
			"-D", "--deep", action="store_true", default=False,
			help="Deep mode. This is used to give a more accurate "
			"speed test. It will download a 100k file from "
			"each server. Because of this you should only use "
			"this option if you have a good connection.")

		group = parser.add_option_group(
			"Server type selection (choose at most one)")
		group.add_option(
			"-F", "--ftp", action="store_true", default=False,
			help="ftp only mode. Will not consider hosts of other "
			"types.")
		group.add_option(
			"-H", "--http", action="store_true", default=False,
			help="http only mode. Will not consider hosts of other types")
		group.add_option(
			"-r", "--rsync", action="store_true", default=False,
			help="rsync mode. Allows you to interactively select your"
			" rsync mirror. Requires -i or -a to be used.")
		group.add_option(
			"-4", "--ipv4", action="store_true", default=False,
			help="only use IPv4")
		group.add_option(
			"-6", "--ipv6", action="store_true", default=False,
			help="only use IPv6")
		group.add_option(
			"-c", "--country", action="store", default=None,
			help="only use mirrors from the specified country "
			"NOTE: Names with a space must be quoted "
			"eg.:  -c 'South Korea'")
		group.add_option(
			"-R", "--region", action="store", default=None,
			help="only use mirrors from the specified region "
			"NOTE: Names with a space must be quoted "
			"eg.:  -r 'North America'")

		group = parser.add_option_group("Other options")
		group.add_option(
			"-o", "--output", action="store_true", default=False,
			help="Output Only Mode, this is especially useful "
			"when being used during installation, to redirect "
			"output to a file other than %s" % config_path)
		group.add_option(
			"-b", "--blocksize", action="store", type="int",
			help="This is to be used in automatic mode "
			"and will split the hosts into blocks of BLOCKSIZE for "
			"use with netselect. This is required for certain "
			"routers which block 40+ requests at any given time. "
			"Recommended parameters to pass are: -s3 -b10")
		group.add_option(
			"-t", "--timeout", action="store", type="int",
			default="10", help="Timeout for deep mode. Defaults to 10 seconds.")
		group.add_option(
			"-s", "--servers", action="store", type="int", default=1,
			help="Specify Number of servers for Automatic Mode "
			"to select. this is only valid for download mirrors. "
			"If this is not specified, a default of 1 is used.")
		group.add_option(
			"-d", "--debug", action="store_const", const=2, dest="verbosity",
			default=1, help="debug mode")
		group.add_option(
			"-q", "--quiet", action="store_const", const=0, dest="verbosity",
			help="Quiet mode")

		if len(argv) == 1:
			parser.print_help()
			sys.exit(1)

		options, args = parser.parse_args(argv[1:])

		# sanity checks

		# hack: check if more than one of these is set
		if options.http + options.ftp + options.rsync > 1:
			self.output.print_err('Choose at most one of -H, -f and -r')

		if options.ipv4 and options.ipv6:
			self.output.print_err('Choose at most one of --ipv4 and --ipv6')

		if (options.ipv6 and not socket.has_ipv6) and not options.interactive:
			options.ipv6 = False
			self.output.print_err('The --ipv6 option requires python ipv6 support')

		if options.rsync and not (options.interactive or options.all_mirrors):
			self.output.print_err('rsync servers can only be selected with -i or -a')

		if options.interactive and (
			options.deep or
			options.blocksize or
			options.servers > 1):
			self.output.print_err('Invalid option combination with -i')

		if (not options.deep) and (not self._have_bin('netselect') ):
			self.output.print_err(
				'You do not appear to have netselect on your system. '
				'You must use the -D flag')

		if (os.getuid() != rootuid) and not options.output:
			self.output.print_err('Must be root to write to %s!\n' % config_path)

		if args:
			self.output.print_err('Unexpected arguments passed.')

		# return results
		return options


	def get_available_hosts(self, options):
		'''Returns a list of hosts suitable for consideration by a user
		based on user input

		@param options: parser.parse_args() options instance
		@rtype: list
		'''
		if options.rsync:
			self.output.write("using url: %s" % MIRRORS_RSYNC_DATA, 2)
			hosts = Extractor(MIRRORS_RSYNC_DATA, options, self.output).hosts
		else:
			self.output.write("using url: %s" % MIRRORS_3_XML, 2)
			hosts = Extractor(MIRRORS_3_XML, options, self.output).hosts
		return hosts


	def select_urls(self, hosts, options):
		'''Returns the list of selected host urls using
		the options passed in to run one of the three selector types.
		1) Interactive ncurses dialog
		2) Deep mode mirror selection.
		3) (Shallow) Rapid server selection via netselect

		@param hosts: list of hosts to choose from
		@param options: parser.parse_args() options instance
		@rtype: list
		'''
		if options.interactive:
			selector = Interactive(hosts, options, self.output)
		elif options.deep:
			selector = Deep(hosts, options, self.output)
		else:
			selector = Shallow(hosts, options, self.output)
		return selector.urls


	def get_conf_path(self, rsync=False):
		'''Checks for the existance of repos.conf or make.conf in /etc/portage/
		Failing that it checks for it in /etc/
		Failing in /etc/ it defaults to /etc/portage/make.conf

		@rtype: string
		'''
		if rsync:
			# startwith repos.conf
			config_path = EPREFIX + '/etc/portage/repos.conf/gentoo.conf'
			if not os.access(config_path, os.F_OK):
				self.output.write("Failed access to gentoo.conf: "
					"%s\n" % os.access(config_path, os.F_OK), 2)
				return get_make_conf_path(EPREFIX)
			return config_path
		return get_make_conf_path(EPREFIX)


	def main(self, argv):
		"""Lets Rock!

		@param argv: list of command line arguments to parse
		"""
		config_path = self.get_conf_path()
		options = self._parse_args(argv, config_path)
		self.output.verbosity = options.verbosity
		self.output.write("main(); config_path = %s\n" % config_path, 2)

		# reset config_path to find repos.conf/gentoo.conf if it exists
		if options.rsync:
			config_path = self.get_conf_path(options.rsync)
			self.output.write("main(); reset config_path = %s\n" % config_path, 2)
		else:
			self.output.write("main(); rsync = %s" % str(options.rsync),2)

		fsmirrors = get_filesystem_mirrors(self.output,
			config_path, options.rsync)

		hosts = self.get_available_hosts(options)

		if options.all_mirrors:
			urls = sorted([url for url, args in list(hosts)])
			if options.rsync:
				urls = [urls[0]]
		else:
			urls = self.select_urls(hosts, options)

		if len(urls):
			self.change_config(fsmirrors + urls, options.output,
				config_path, options.rsync)
		else:
			self.output.write("No search results found. "
				"Check your filter settings and re-run mirrorselect\n")
