#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#

import enstore

def do_work():
    # admin mode
    mode = 0

    intf = enstore.EnstoreInterface(mode)
    if intf.error is None:
	en = enstore.Enstore(intf)
	en.do_work()

if __name__ == "__main__" :

    do_work()
