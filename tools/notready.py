#!/usr/bin/env python

import sys
import os
import string

filelist = sys.argv[1:]

print "Checking files..."

for file in filelist[:]:

    working_revision = repository_revision = production_revision = '(none)'
    if os.path.isdir(file):
        print file, "is a directory, ignoring"
        filelist.remove(file)
        continue
    
    cvsinfo = os.popen('cvs status -v %s 2>/dev/null' % (file,)).readlines()
    L = len(cvsinfo)
    if not cvsinfo or L<6:
        print "A Cannot parse cvs output", cvsinfo, L
        sys.exit(1)

    if string.find(cvsinfo[4], "No revision control file\n") > 0:
        print file, "\t not in CVS, skipping"
        filelist.remove(file)
        continue

    if L<8:
        print "B Cannot parse cvs output", cvsinfo, L
        sys.exit(1)
        
    if string.find(cvsinfo[3], '   Working revision') != 0:
        print "Cannot find Working revision", cvsinfo
        sys.exit(1)
    tokens = string.split(cvsinfo[3])
    if len(tokens) <3:
        print "Cannot parse Working revision", cvsinfo[3], len(tokens),
        sys.exit(1)
    working_revision = tokens[2]

    if string.find(cvsinfo[4], '   Repository revision') != 0:
        print "Cannot find Repository revision", cvsinfo
        sys.exit(1)
    tokens = string.split(cvsinfo[4])
    if len(tokens) <3:
        print "Cannot parse Repository revision", cvsinfo
        sys.exit(1)
    repository_revision = tokens[2]
        
    found = 0
    for line in cvsinfo[5:L]:
        if string.find(line, "production") >= 0:
            tokens = string.split(line)
            if len(tokens) <3:
                print "Cannot parse production", line
                sys.exit(1)
            production_revision = tokens[2][0:-1] # strip off trailing }
            found = 1
            break

    if repository_revision != production_revision or working_revision != production_revision :
        print '%s\t Working revision=%s  Repository revision=%s  Production revision=%s'%(file,working_revision, repository_revision, production_revision)
    else:
        print '%s\t ok'%(file,)
        
