#!/usr/bin/env python

import ecron_util
import os

edata = ecron_util.EcronData()

# fake it here
edata.crons_dir = '/home/huangch/ECRON_TEST/CRONS'

# check if ecrons_dir exist
if not os.access(edata.crons_dir, os.F_OK):
	os.makedirs(edata.crons_dir)

names_and_nodes = edata.get_all_names_and_nodes()
for i in names_and_nodes:
	print i[0], i[1]
	dir = os.path.join(edata.crons_dir, i[1].split('.')[0])
	# check if the directory exists
	if not os.access(dir, os.F_OK):
		os.makedirs(dir)
	res = edata.get_result(i[0], i[1], ecron_util.one_week_ago())
	edata.plot(os.path.join(dir, i[0]), i[0], res)
