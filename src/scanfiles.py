#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

import os
import sys
import stat
import string
import time
import errno

import info_client
import option
import pnfs
import volume_family
import e_errors
from encp import e_access  #for e_access().

os.access = e_access   #Hack for effective ids instead of real ids.

infc = None
ff = {} #File Family cache.
ONE_DAY = 24*60*60

def usage():
    print "usage: %s [path [path2 [path3 [ ... ]]]]"%(sys.argv[0])
    print "usage: %s --help"%(sys.argv[0])
    print "usage: %s --infile file"%(sys.argv[0])

def error(s):
    print s, '... ERROR'

def warning(s):
    print s, '... WARNING'

def errors_and_warnings(fname, error, warning):

    print fname +' ...',
    # print warnings
    for i in warning:
        print i + ' ...',
    # print errors
    for i in error:
        print i + ' ...',
    if error:
        print 'ERROR'
    elif warning:
        print 'WARNING'
    else:
        print 'OK'


def layer_file(f, n):
    pn, fn = os.path.split(f)
    return os.path.join(pn, '.(use)(%d)(%s)'%(n, fn))

def check_link(l):

    msg = []
    warn = []
    
    if not os.path.exists(l):
        warn.append("missing the original of link")

    return msg, warn

def check_dir(d):

    msg = []
    warn = []
    
    # skip volmap and .bad and .removed directory
    lc = os.path.split(d)[1]
    if lc == 'volmap' or lc[:3] == '.B_' or lc[:3] == '.A_' \
           or lc[:8] == '.removed':
        return msg, warn
        
    if os.access(d, os.R_OK | os.X_OK):
        for entry in os.listdir(d):

            #Skip blacklisted files.
            if entry[:4] == '.bad' or entry[:8] == '.removed':
                continue

            check(os.path.join(d, entry))
    else:
        msg.append("can not access directory")

    return msg, warn

def check_file(f):

    msg = []
    warn = []

    #If the file is an (P)NFS or encp temporary file, give the error that
    # it still exists.
    if os.path.basename(f)[:4] == ".nfs" \
           or os.path.basename(f)[-5:] == "_lock":
        msg.append("found temporary file")
        return msg, warn

    #Determine if the file exists and we can access it.
    try:
        f_stats = os.stat(f)
    except OSError:
        f = pnfs.get_local_pnfs_path(f)
        try:
            f_stats = os.stat(f)
        except OSError:
            #No read permission is the likeliest at this point...
            msg.append('no read permission')
            return msg, warn

    # get xref from layer 4 (?)
    try:
        pf = pnfs.File(f)
    except (KeyboardInterrupt, SystemExit), msg:
        raise msg
    except OSError:
        msg.append('corrupted layer 4 metadata')
        #return msg, warn

    # get bfid from layer 1
    try:
        f1 = open(layer_file(f, 1))
        bfid = f1.readline()
        f1.close()
    except OSError:
        msg.append('corrupted layer 1 metadata')

    if msg:
        return msg, warn

    #Look for missing pnfs information.
    try:
        if bfid != pf.bfid:
            msg.append('bfid(%s, %s)'%(bfid, pf.bfid))
    except (TypeError, ValueError, IndexError, AttributeError):
    	age = time.time() - f_stats[8]
        if age < ONE_DAY:
            warn.append('younger than 1 day (%d)'%(age))
            return msg, warn
        
        if len(bfid) < 8:
            msg.append('missing layer 1')

        if not hasattr(pf, 'bfid'):
            msg.append('missing layer 4')
            
        if msg or warn:
            return msg, warn

    # Get file database information.
    fr = infc.bfid_info(bfid)
    if fr['status'][0] != e_errors.OK:
        msg.append('not in db')
	return msg, warn

    # Look for missing file database information.
    if not fr.has_key('pnfs_name0'):
        msg.append('no filename in db')
    if not fr.has_key('pnfsid'):
        msg.append('no pnfs id in db')

    if msg or warn:
        return msg, warn

    #Compare pnfs metadata with file database metadata.
    
    # volume label
    try:
        if pf.volume != fr['external_label']:
            msg.append('label(%s, %s)'%(pf.volume, fr['external_label']))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted external_label')
        
    # location cookie
    try:
        # if pf.location_cookie != fr['location_cookie']:
        #    msg.append('location_cookie(%s, %s)'%(pf.location_cookie, fr['location_cookie']))
        p_lc = string.split(pf.location_cookie, '_')[2]
        f_lc = string.split(fr['location_cookie'], '_')[2]
        if p_lc != f_lc:
            msg.append('location_cookie(%s, %s)'%(pf.location_cookie, fr['location_cookie']))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted location_cookie')
        
    # size
    try:
        real_size = os.stat(f)[stat.ST_SIZE]
        if long(pf.size) != long(fr['size']):
            msg.append('size(%d, %d, %d)'%(long(pf.size), long(real_size), long(fr['size'])))
        elif real_size != 1 and long(real_size) != long(pf.size):
            msg.append('size(%d, %d, %d)'%(long(pf.size), long(real_size), long(fr['size'])))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted size')
        
    # file_family
    try:
        if ff.has_key(fr['external_label']):
            file_family = ff[fr['external_label']]
        else:
            vol = infc.inquire_vol(fr['external_label'])
            if vol['status'][0] != e_errors.OK:
                msg.append('missing vol '+fr['external_label'])
                return msg, warn
            file_family = volume_family.extract_file_family(vol['volume_family'])
            ff[fr['external_label']] = file_family
        # take care of MIGRATION, too
        if pf.file_family != file_family and \
            pf.file_family+'-MIGRATION' != file_family:
            msg.append('file_family(%s, %s)'%(pf.file_family, file_family))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted file_family')
        
    # pnfsid
    try:
        pnfs_id = pf.get_pnfs_id()
        if pnfs_id != pf.pnfs_id or pnfs_id != fr['pnfsid']:
            msg.append('pnfsid(%s, %s, %s)'%(pf.pnfs_id, pnfs_id, fr['pnfsid']))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted pnfsid')
        
    # drive
    try:
        if fr.has_key('drive'):	# some do not have this field
            if fr['drive'] != '' and pf.drive != fr['drive']:
                if pf.drive != 'imported' and pf.drive != "missing" \
                    and fr['drive'] != 'unknown:unknown':
                    msg.append('drive(%s, %s)'%(pf.drive, fr['drive']))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted drive')
        
    # path
    try:
        if pf.p_path != fr['pnfs_name0'] and \
               pnfs.get_local_pnfs_path(pf.p_path) != pnfs.get_local_pnfs_path(fr['pnfs_name0']):
            #print layer 4, current name, file database.  ERROR
            msg.append("filename(%s, [%s], %s)" % (pf.p_path, pf.path, fr['pnfs_name0']))
        elif pf.path != pf.p_path and \
                 pnfs.get_local_pnfs_path(pf.path) != pnfs.get_local_pnfs_path(pf.p_path):
            #print current name, then original name.  WARNING
            warn.append('original_pnfs_path(%s, %s)'%(pf.path, pf.p_path))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no or corrupted pnfs_path')

    # deleted
    try:
        if fr['deleted'] != 'no':
            msg.append('deleted(%s)'%(fr['deleted']))
    except (TypeError, ValueError, IndexError, AttributeError):
        msg.append('no deleted field')

    # parent id
    try:
        target = os.path.dirname(f)
        target_name = os.path.join(os.path.dirname(target),
                                   ".(id)(%s)" % os.path.basename(target))
        target_file = open(target_name)
        parent_dir_id = target_file.readline()[:-1]
        target_file.close()
    except:
        parent_dir_id = ""
    if pf.parent_id != parent_dir_id:
        msg.append("parent_id(%s, %s)" % (pf.parent_id, parent_dir_id))

    return msg, warn

def check(f):

    #Do one stat() for each file instead of one for each os.path.isxxx() call.
    try:
        f_stats = os.lstat(f)
    except OSError, msg:
	if msg.errno == errno.ENOENT:
            #Before blindly returning this error, first check the directory
            # listing for this entry.  A known 'ghost' file problem exists
            # and this is how to find out.
            try:
                directory, filename = os.path.split(f)
                dir_list = os.listdir(directory)
                if filename in dir_list:
                    #We have this special error situation.
                    error(f + " ... invalid directory entry")
                    return
            except OSError:
                pass
          
            error(f + " ... does not exist")
            return
        if msg.errno == errno.EACCES or msg.errno == errno.EPERM:
            error(f + " ... permission error")
            return
        
        error(f + " ... " + os.strerror(msg.errno))
        return

    if stat.S_ISLNK(f_stats[stat.ST_MODE]):
        res, wrn = check_link(f)
        errors_and_warnings(f, res, wrn)
        
    # if f is a directory, recursively check its files
    elif stat.S_ISDIR(f_stats[stat.ST_MODE]):
        res, wrn = check_dir(f)
        if res or wrn:
            errors_and_warnings(f, res, wrn)
            
    elif stat.S_ISREG(f_stats[stat.ST_MODE]):
        res, wrn = check_file(f)
        errors_and_warnings(f, res, wrn)
        
    else:
        error(f+' ... unrecognized type')
        return


def start_check(line):
    line = line.strip()
    
    import profile
    import pstats
    profile.run("check(line)", "/tmp/scanfiles_profile")
    p = pstats.Stats("/tmp/scanfiles_profile")
    p.sort_stats('cumulative').print_stats(100)
    
    #check(line)

if __name__ == '__main__':

    if len(sys.argv) >= 2 and sys.argv[1] == '--help':
        usage()
        sys.exit(0)

    if len(sys.argv) == 3 and sys.argv[1] == '--infile':
        file_object = open(sys.argv[2])
        file_list = None
        #f = open(sys.argv[2])
        #f_list = map(string.strip, f.readlines())
        #f.close()
    elif len(sys.argv) == 1:
        file_object = sys.stdin
        file_list = None
        #f_list = map(string.strip, sys.stdin.readlines())
    else:
        file_object = None
        file_list = sys.argv[1:]
        #f_list = sys.argv[1:]

    intf = option.Interface()
    infc = info_client.infoClient((intf.config_host, intf.config_port))

    try:

        #When the entire list of files/directories is listed on the command
        # line we need to loop over them.
        if file_list:
            for line in file_list:
                if line[:2] != '--':
                    start_check(line)
                    
        #When the list of files/directories is of an unknown size from a file
        # object; read the filenames in one at a time for resource efficiency.
        elif file_object:
            line = file_object.readline()
            while line:
                start_check(line)
                line = file_object.readline()

    except (KeyboardInterrupt, SystemExit):
        #If the user does Control-C don't traceback.
        pass
