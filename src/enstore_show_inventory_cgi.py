#!/usr/bin/env python

import os
import sys
import string
import socket

inv_dir = "/enstore/tape_inventory"

host = string.split(socket.gethostname(), '.')[0]
if host[:2] == "d0":
	cluster = "d0en"
elif host[:3] == "stk":
	cluster = "stken"
elif host[:3] == "cdf":
	cluster = "cdfen"
else:
	cluster = host

special = ['TOTAL_BYTES_ON_TAPE', 'VOLUMES', 'VOLUMES_DEFINED.html', 'VOLUMES_TOO_MANY_MOUNTS', 'VOLUME_QUOTAS', 'VOLUME_SIZE', 'LAST_ACCESS', 'NOACCESS', 'CLEANING', 'VOLUME_CROSS_CHECK', 'COMPLETE_FILE_LISTING', 'DECLARATION_ERROR', 'MIGRATED_VOLUMES', 'RECYCLABLE_VOLUMES', 'WRITE_PROTECTION_ALERT', 'WEEKLY_SUMMARY', 'TAB_FLIPPING_WATCH']

if cluster == "d0en":
	special.append('TAB_FLIPPING_WATCH-samlto2')
	special.append('TAB_FLIPPING_WATCH-D0-LTO4G1')
	special.append('TAB_FLIPPING_WATCH-D0-LTO4F1')
	special.append('STK-VOLUMES.html')
	special.append('AML2-VOLUMES.html')
	special.append('SL8500G1-VOLUMES.html')
	special.append('SL8500F1-VOLUMES.html')
	special.append('MIGRATION_SUMMARY.html')
elif cluster == "stken":
	special.append('TAB_FLIPPING_WATCH-SL8500G1')
	special.append('STK-VOLUMES.html')
	special.append('SL8500-VOLUMES.html')
	special.append('MIGRATION_STATUS')
	special.append('QUOTA_ALERT')
	special.append('VOLUME_QUOTAS_UPDATE')
	special.append('CMS_VOLUMES_WITH_ONLY_DELETED_FILES')
elif cluster == "cdfen":
	special.append('TAB_FLIPPING_WATCH-CDF-LTO3')
	special.append('STK-VOLUMES.html')
	special.append('STKD0-VOLUMES.html')
	special.append('SL8500-VOLUMES.html')

catalog = {}

cmd = '. /usr/local/etc/setups.sh; setup enstore; enstore info --labels'

for i in os.popen(cmd).readlines():
	f = string.strip(i)
	if f[-8:] != '.deleted':
		prefix = f[:3]
		if catalog.has_key(prefix):
			catalog[prefix].append(f)
		else:
			catalog[prefix] = [f]

# in the beginning ...

print "Content-type: text/html"
print

# taking care of the header

print '<html>'
print '<head>'
print '<title>Tape Inventory on '+cluster+'</title>'
print '</head>'
print '<body bgcolor="#ffffd0">'
print '<font size=7 color="#ff0000">Enstore Tape Inventory on '+cluster+'</font>'
print '<hr>'

# handle special files

print '<p>'
for i in special:
	if i == 'COMPLETE_FILE_LISTING':
		print '<a href="enstore_file_listing_cgi.py">', string.split(i, '.')[0], '</a>&nbsp;&nbsp;'
	else:
		print '<a href="'+os.path.join(inv_dir, i)+'">', string.split(i, '.')[0], '</a>&nbsp;&nbsp;'
print '<p><a href="'+inv_dir+'">Raw Directory Listing</a>'
print '<hr>'
print '<p>'
print '<h2><font color="#aa0000">Index</font></h2>'
keys = catalog.keys()
keys.sort()

for i in keys:
	print '<a href=#'+i+'>'+i+'</a>&nbsp;&nbsp;'

for i in keys:
	print '<hr>'
	print '<p>'
	print '<h2><a name="'+i+'"><font color="#aa0000">'+i+'</font></a></h2>'
	for j in catalog[i]:
		# print '<a href="'+os.path.join(inv_dir, j)+'">', j, '</a>&nbsp;&nbsp;'
		print '<a href=/cgi-bin/show_volume_cgi.py?volume='+j+'>', j, '</a>&nbsp;&nbsp;'

# the end
print '</body>'
print '</html>'
