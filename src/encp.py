#!/usr/bin/env python
#
# $Id$
#

# system imports
import sys
import os
import stat
import time
import errno
import pprint
import pwd
import grp
import socket
import pdb
import string
import traceback
import select
import signal
import random
import fcntl, FCNTL
import math
import exceptions
import re

# enstore modules
import setpath 
import Trace
import pnfs
import callback
import log_client
import configuration_client
import udp_client
import EXfer
import interface
import e_errors
import hostaddr
import host_config
import atomic
import multiple_interface
import library_manager_client
import delete_at_exit
import runon
import enroute
import charset
import volume_family
import volume_clerk_client
import file_clerk_client
import enstore_constants
import enstore_functions

#Constants for the max file size.  Currently this assumes the max for the
# cpio_odc wrapper format.  The -1s are necessary since that is the size
# that fits in signed integer variables.
ONE_G = 1024 * 1024 * 1024
TWO_G = long(ONE_G) - 1     #Used in int32()
MAX_FILE_SIZE = long(ONE_G) * 2 - 1    # don't get overflow

#############################################################################
# verbose: Roughly, five verbose levels are used.
# 0: Print nothing except fatal errors.
# 1: Print message for complete success.
# 2: Print non-fatal error messages.
# 4: Print (short) info about the read/write status.
# 6: Print (short) information on the number of files left to transfer.
# 8: Print info about system config.
# 10: Print (long) info about everthing.
#############################################################################
DONE_LEVEL     = 1
ERROR_LEVEL    = 2
TRANSFER_LEVEL = 4
TO_GO_LEVEL    = 6
CONFIG_LEVEL   = 8
TICKET_LEVEL   = 10

#This is the global used by print_data_access_layer_format().  It uses it to
# determine whether standard out or error is used.
data_access_layer_requested = 0

#Initial seed for generate_unique_id().
_counter = 0

# int32(v) -- if v > 2^31-1, make it long
#
# a quick fix for those 64 bit machine that consider int is 64 bit ...

def int32(v):
    if v > TWO_G:
        return long(v)
    else:
        return v
    
############################################################################

class EncpError(Exception):
    def __init__(self, e_errno, e_message, e_type, e_ticket=None):

        Exception.__init__(self)

        #Handle the errno (if a valid one passed in).
        if e_errno in errno.errorcode.keys():
            self.errno = e_errno
        else:
            self.errno = None

        #Handel the message if not given.
        if e_message == None:
            if e_errno: #By now this is None or a valid errno.
                self.message = os.strerror(self.errno)
            else:
                self.message = None
        elif type(e_message) == type(""):
            self.message = e_message #There was a string message passed.
        else:
            self.message = None

        #Type should be from e_errors.py.  If not specified, use errno code.
        if not e_type:
            try:
                self.type = errno.errorcode[self.errno]
            except KeyError:
                self.type = e_errors.UNKNOWN
        else:
            self.type = e_type

        self.ticket = e_ticket

        #Generate the string that stringifying this obeject will give.
        self._string()

        #Is this duplicated from calling Exception.__init__(self)?
        #self.args = [self.errno, self.message, self.type]

    def __str__(self):
        self._string()
        return self.strerror

    def __repr__(self):
        return "EncpError"

    def _string(self):
        if self.errno in errno.errorcode.keys():
            errno_name = errno.errorcode[self.errno]
            errno_description = os.strerror(self.errno)
            self.strerror = "%s: [ ERRNO %s ] %s: %s" % (errno_name,
                                                        self.errno,
                                                        errno_description,
                                                        self.message)
        else:
            self.strerror = self.message

        return self.strerror
    
############################################################################

def signal_handler(sig, frame):
    try:
        sys.stderr.write("Caught signal %s, exiting\n" % (sig,))
        sys.stderr.flush()
    except:
        pass

    if sig != signal.SIGTERM: #If they kill, don't do anything.
        quit(1)

def encp_client_version():
    ##this gets changed automatically in {enstore,encp}Cut
    ##You can edit it manually, but do not change the syntax
    version_string = "v2_15  CVS $Revision$ "
    file = globals().get('__file__', "")
    if file: version_string = version_string + file
    return version_string

def quit(exit_code=1):
    delete_at_exit.delete()
    os._exit(exit_code)

def print_error(errcode,errmsg):
    format = str(errcode)+" "+str(errmsg) + '\n'
    format = "ERROR: "+format
    sys.stderr.write(format)
    sys.stderr.flush()

def generate_unique_id():
    global _counter
    thishost = hostaddr.gethostinfo()[0]
    ret = "%s-%d-%d-%d" % (thishost, int(time.time()),_counter, os.getpid())
    _counter = _counter + 1
    return ret

def combine_dict(*dictionaries):
    new = {}
    for i in range(0, len(dictionaries)):
        if type(dictionaries[i]) != type({}):
            raise TypeError, "Dictionary required, not %s." % \
                  type(dictionaries[i])
        for key in dictionaries[i].keys():
            #If both items in the dictionary are themselves dictionaries, then
            # do this recursivly.
            if new.get(key, None) and \
               type(dictionaries[i][key]) == type({}) and \
               type(new[key]) == type({}):
                         new[key] = combine_dict(new[key],
                                                 dictionaries[i][key])
                         
            #Just set the value if not a dictionary.
            elif not new.has_key(key):
                new[key] = dictionaries[i][key]

    return new

# generate the full path name to the file
def fullpath(filename):
    if not filename:
        return None, None, None, None

    machine = hostaddr.gethostinfo()[0]

    #Expand the path to the complete absolute path.
    filename = os.path.expandvars(filename)
    filename = os.path.expanduser(filename)
    filename = os.path.abspath(filename)
    filename = os.path.normpath(filename)

    dirname, basename = os.path.split(filename)

    return machine, filename, dirname, basename

def close_descriptors(*fds):
    #For each file descriptor that is passed in, close it.  The fds can
    # contain itegers or class instances with a "close" function attribute.
    for fd in fds:
        if hasattr(fd, "close"):
            apply(getattr(fd, "close"))
        else:
            try:
                os.close(fd)
            except OSError:
                sys.stderr.write("Unable to close fd %s.\n" % fd)

def format_class_for_print(object, name):
    #formulate e values output
    formated_string = "%s=" % name
    pad = 0
    for var in dir(object):
        if pad:
            formated_string = formated_string + "\n"
        ret = getattr(object, var)
        if type(ret) == type(""): #if a string, make it look like one.
            ret = "'" + ret + "'"
        formated_string = formated_string + " " * pad + var \
                          + ": " + str(ret)
        pad = len(name) + 1 #length of string plus the = character
    return formated_string

def get_file_size(file):
    if file[:6] == "/pnfs/":
        #Get the remote pnfs filesize.
        try:
            pin = pnfs.Pnfs(file)
            pin.get_file_size()
            filesize = pin.file_size
        except (OSError, IOError), detail:
            filesize = 0
    else:
        try:
            statinfo = os.stat(file)
            filesize = statinfo[stat.ST_SIZE]
        except (OSError, IOError), detail:
            filesize = 0

    return filesize

#Return the number of requests in the list that have NOT had a non-retriable
# error or have already finished.
def get_queue_size(request_list):
    queue_size=0
    for req in request_list:
        if not req.get('finished_state', 0):
            queue_size = queue_size + 1

    print queue_size
    return queue_size

############################################################################

#The os.access() and the access(2) C library routine use the real id when
# testing for access.  This function does the same thing but for the
# effective ID.
def e_access(path, mode):
    
    #Translate the access() mode values to stat() mode values.
    if mode == os.F_OK:
        t_mode = 0
    elif mode == os.R_OK:
        t_mode = stat.S_IRUSR
    elif mode == os.W_OK:
        t_mode = stat.S_IWUSR
    elif mode == os.X_OK:
        t_mode == stat.S_IXUSR
    else:
        return 0

    #Test for existance.
    try:
        stat_mode = os.stat(path)[stat.ST_MODE]

        #If the existance of the file is all that matters, then handle it.
        if t_mode == 0:
            return 1
    except OSError, detail:
        return 0

    #Need to break down the mode returned from os.stat().  This loop determines
    # the number of bytes to shift the mode.
    for i in range(32):
        if (t_mode >> 1) % 2: #Stop when the right most bit is 1.
            break
        else:
            t_mode = (t_mode >> 1) #Shift until the right most bit is 1.
    else:
        return 0

    return (stat_mode >> i) % 2

############################################################################

#Return the correct configuration server client based on the 'brand' (if
# present) of the bfid.
def get_csc(ticket_or_bfid=None):
    # get a configuration server
    config_host = enstore_functions.default_host()
    config_port = enstore_functions.default_port()
    csc = configuration_client.ConfigurationClient((config_host,config_port))
    fcc = file_clerk_client.FileClient(csc)
    
    #Due to branding we need to figure out which system is the correct one.
    # Should only matter for reads.  On a success, the variable 'brand' should
    # contain the brand of the bfid to be used in the rest of the function.
    # On error return the default configuration server client (csc).
    if not ticket_or_bfid:
        return csc
    elif type(ticket_or_bfid) == type({}):  #If passed a ticket with bfid.
        bfid = ticket_or_bfid['fc'].get("bfid", "")
        if len(bfid) >= 4 and  bfid[:4].isupper():
            brand = bfid[:4]
        else:
            return csc
    elif type(ticket_or_bfid) == type(''):  #If passed a bfid.
        if len(ticket_or_bfid) >= 4 and  ticket_or_bfid[:4].isupper():
                brand = ticket_or_bfid[:4]
        else:
            return csc
    else:  #Nothing valid, just return the default csc.
        return csc

    #Before checking other systems, check the current system.
    if brand == fcc.get_brand():
        return csc

    #Get the list of all config servers and remove the 'status' element.
    config_servers = csc.get('known_config_servers', {})
    if config_servers['status'][0] == e_errors.OK:
        del config_servers['status']
    else:
        return csc

    #Loop through systems for the brand that matches the one we're looking for.
    for server in config_servers.keys():
        try:
            #Get the next configuration client.
            csc_test = configuration_client.ConfigurationClient(
                config_servers[server])

            #Get the next file clerk client and its brand.
            fcc_test = file_clerk_client.FileClient(csc_test,
                                                    timeout=10, tries=1)
            system_brand = fcc_test.get_brand()

            #If things match then use this system.
            if brand == system_brand:
                if fcc.get_brand() != system_brand:
                    msg = "Using %s based on brand %s." % (system_brand, brand)
                    Trace.log(e_errors.INFO, msg)
                csc = csc_test
                break
        except KeyboardInterrupt:
            exc, msg, tb = sys.exc_info()
            raise exc, msg, tb
        except:
            exc, msg, tb = sys.exc_info()
            Trace.log(e_errors.WARNING, str((str(exc), str(msg))))

    return csc
            
def max_attempts(library, encp_intf):
    #Determine how many times a transfer can be retried from failures.
    #Also, determine how many times encp resends the request to the lm
    # and the mover fails to call back.
    if library[-17:] == ".library_manager":
        lib = library
    else:
        lib = library + ".library_manager"

    # get a configuration server
    csc = get_csc()
    lm = csc.get(lib)

    if encp_intf.max_retry == None:
        encp_intf.max_retry = lm.get('max_encp_retries',
                                     enstore_constants.DEFAULT_ENCP_RETRIES)
    if encp_intf.max_resubmit == None:
        encp_intf.max_resubmit = lm.get('max_encp_resubmits',
                                enstore_constants.DEFAULT_ENCP_RESUBMITIONS)

############################################################################

def print_data_access_layer_format(inputfile, outputfile, filesize, ticket):
    # check if all fields in ticket present
    fc_ticket = ticket.get('fc', {})
    external_label = fc_ticket.get('external_label', '')
    location_cookie = fc_ticket.get('location_cookie','')
    mover_ticket = ticket.get('mover', {})
    device = mover_ticket.get('device', '')
    device_sn = mover_ticket.get('serial_num','')
    time_ticket = ticket.get('times', {})
    transfer_time = time_ticket.get('transfer_time', 0)
    seek_time = time_ticket.get('seek_time', 0)
    mount_time = time_ticket.get('mount_time', 0)
    in_queue = time_ticket.get('in_queue', 0)
    now = time.time()
    total = now - time_ticket.get('encp_start_time', now)
    sts =  ticket.get('status', ('Unknown', None))
    status = sts[0]
    msg = sts[1:]
    if len(msg)==1:
        msg=msg[0]
        
    if type(outputfile) == type([]) and len(outputfile) == 1:
        outputfile = outputfile[0]
    if type(inputfile) == type([]) and len(inputfile) == 1:
        inputfile = inputfile[0]
        
    if not data_access_layer_requested and status != e_errors.OK:
        out=sys.stderr
    else:
        out=sys.stdout

    ###String used to print data access layer.
    data_access_layer_format = """INFILE=%s
OUTFILE=%s
FILESIZE=%s
LABEL=%s
LOCATION=%s
DRIVE=%s
DRIVE_SN=%s
TRANSFER_TIME=%.02f
SEEK_TIME=%.02f
MOUNT_TIME=%.02f
QWAIT_TIME=%.02f
TIME2NOW=%.02f
STATUS=%s\n"""  #TIME2NOW is TOTAL_TIME, QWAIT_TIME is QUEUE_WAIT_TIME.

    out.write(data_access_layer_format % (inputfile, outputfile, filesize,
                                          external_label,location_cookie,
                                          device, device_sn,
                                          transfer_time, seek_time,
                                          mount_time, in_queue,
                                          total, status))

    out.write('\n')
    out.flush()
    if msg:
        msg=str(msg)
        sys.stderr.write(msg+'\n')
        sys.stderr.flush()

    try:
        format = "INFILE=%s OUTFILE=%s FILESIZE=%d LABEL=%s LOCATION=%s " +\
                 "DRIVE=%s DRIVE_SN=%s TRANSFER_TIME=%.02f "+ \
                 "SEEK_TIME=%.02f MOUNT_TIME=%.02f QWAIT_TIME=%.02f " + \
                 "TIME2NOW=%.02f STATUS=%s"
        msg_type=e_errors.ERROR
        if status == e_errors.OK:
            msg_type = e_errors.INFO
        errmsg=format%(inputfile, outputfile, filesize, 
                       external_label, location_cookie,
                       device,device_sn,
                       transfer_time, seek_time, mount_time,
                       in_queue, total,
                       status)

        if msg:
            #Attach the data access layer info to the msg, but first remove
            # the newline and tab used for readability on the terminal.
            errmsg = errmsg + " " + string.replace(msg, "\n\t", "  ")
        Trace.log(msg_type, errmsg)
    except OSError:
        exc,msg,tb=sys.exc_info()
        sys.stderr.write("cannot log error message %s\n"%(errmsg,))
        sys.stderr.write("internal error %s %s\n"%(exc,msg))

#######################################################################

# get the configuration client and udp client and logger client
# return some information about who we are so it can be used in the ticket

def clients(config_host,config_port):
    # get a configuration serverg432
    #csc = configuration_client.ConfigurationClient((config_host,config_port))
    csc = get_csc()

    # send out an alive request - if config not working, give up
    rcv_timeout = 20
    alive_retries = 10
    try:
        stati = csc.alive(configuration_client.MY_SERVER,
                          rcv_timeout, alive_retries)
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except:
        stati={}
        stati["status"] = (e_errors.CONFIGDEAD,"Config at %s port=%s"%
                           (config_host, config_port))
    if stati['status'][0] != e_errors.OK:
        print_data_access_layer_format("","",0, stati)
        quit()
    
    # get a logger client
    logc = log_client.LoggerClient(csc, 'ENCP', 'log_server')
   
    #global client #should not do this
    client = {}
    client['csc']=csc
    client['logc']=logc
    
    return client

##############################################################################

def get_callback_addr(e):
    # get a port to talk on and listen for connections
    (host, port, listen_socket) = callback.get_callback(verbose=e.verbose)
    callback_addr = (host, port)
    listen_socket.listen(4)

    Trace.message(CONFIG_LEVEL,
                  "Waiting for mover(s) to call back on (%s, %s)." %
                  callback_addr)

    return callback_addr, listen_socket

##############################################################################

# for automounted pnfs

pnfs_is_automounted = 0

# access_check(path, mode) -- a wrapper for os.access() that retries for
#                             automatically mounted file system

def access_check(path, mode):

    # if pnfs is not auto mounted, simply call os.access
    if not pnfs_is_automounted:
        #use the effective ids and not the reals used by os.access().
        return e_access(path, mode)

    # automaticall retry 6 times, one second delay each
    for i in range(5):
        if e_access(path, mode):
            return 1
        time.sleep(1)
    return e_access(path, mode)

#Make sure that the filename is valid.
def filename_check(filename):
    #pnfs (v3.1.7) only supports filepaths segments that are
    # less than 200 characters.
    for directory in filename.split("/"):
        if len(directory) > 199:
            raise EncpError(errno.ENAMETOOLONG,
                            "%s: %s" % (os.strerror(errno.ENAMETOOLONG),
                                        directory),
                            e_errors.USERERROR)

    #limit the usable characters for a filename.
    if not charset.is_in_filenamecharset(filename):
        st = ""
        for ch in filename: #grab all illegal characters.
            if ch not in charset.filenamecharset:
                st = st + ch
        raise EncpError(errno.EILSEQ,
                        'Filepath uses non-printable characters: %s' % (st,),
                        e_errors.USERERROR)

#Make sure that the filesystem can handle the filesize.
def filesystem_check(target_filesystem, inputfile):

    #Get filesize
    try:
        size = get_file_size(inputfile)
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except (OSError, IOError):
        exc, msg, tb = sys.exc_info()
        raise EncpError(msg.errno, str(msg), e_errors.OSERROR)
        
    #os.pathconf likes its targets to exist.  If the target is not a directory,
    # use the parent directory.
    if not os.path.isdir(target_filesystem):
        target_filesystem = os.path.split(target_filesystem)[0]

    #Not all operating systems support this POSIX limit yet (ie OSF1).
    try:
        #get the maximum filesize the local filesystem allows.
        bits = os.pathconf(target_filesystem,
                           os.pathconf_names['PC_FILESIZEBITS'])
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except KeyError, detail:
        return
    except (OSError, IOError):
        exc, msg, tb = sys.exc_info()
        msg = "System error getting filesystem file size limit: %s: %s" \
              % (str(exc), str(msg))
        Trace.log(e_errors.ERROR, msg)
        #raise exc, msg, tb
        raise EncpError(msg.errno, str(msg), e_errors.OSERROR)
        
    filesystem_max = 2L**(bits - 1) - 1
    
    #Compare the max sizes.
    if size > filesystem_max:
        raise EncpError(errno.EFBIG,
                        "Filesize (%s) larger than filesystem allows (%s)." \
                        % (size, filesystem_max),
                        e_errors.USERERROR)

#Make sure that the wrapper can handle the filesize.
def wrappersize_check(target_filepath, inputfile):

    #Get filesize
    try:
        size = get_file_size(inputfile)

        #Get the remote pnfs wrapper.  If the maximum size of the
        # wrapper isn't in the configuration file, assume 2GB-1.
        pout = pnfs.Tag((os.path.dirname(target_filepath)))
        pout.get_file_family_wrapper()
        # get a configuration server and the max filesize the wrappers allow.
        csc = get_csc()
        wrappersizes = csc.get('wrappersizes', {})
        wrapper_max = wrappersizes.get(pout.file_family_wrapper,
                                       MAX_FILE_SIZE)
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except (OSError, IOError):
        exc, msg, tb = sys.exc_info()
        raise EncpError(msg.errno, str(msg), e_errors.OSERROR)

    if size > wrapper_max:
        raise EncpError(errno.EFBIG,
                        "Filesize (%s) larger than wrapper (%s) allows (%s)." \
                        % (size, pout.file_family_wrapper, wrapper_max),
                        e_errors.USERERROR)
    
#Make sure that the library can handle the filesize.
def librarysize_check(target_filepath, inputfile):

    #Get filesize
    try:
        size = get_file_size(inputfile)

        #Determine the max allowable size for the given library.
        pout = pnfs.Tag(os.path.dirname(target_filepath))
        pout.get_library()
        csc = get_csc()
        library = csc.get(pout.library + ".library_manager", {})
        library_max = library.get('max_file_size', MAX_FILE_SIZE)
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except (OSError, IOError):
        exc, msg, tb = sys.exc_info()
        raise EncpError(msg.errno, str(msg), e_errors.OSERROR)

    #Compare the max sizes allowed for these various conditions.
    if size > library_max:
        raise EncpError(errno.EFBIG,
                        "Filesize (%s) larger than library (%s) allows (%s)." \
                        % (size, pout.library, library_max),
                        e_errors.USERERROR)

# check the input file list for consistency
def inputfile_check(input_files):
    # create internal list of input unix files even if just 1 file passed in
    if type(input_files)==type([]):
        inputlist=input_files
    else:
        inputlist = [input_files]

    # we need to know how big each input file is
    file_size = []
    
    # check the input unix file. if files don't exits, we bomb out to the user
    for i in range(0, len(inputlist)):

        # get fully qualified name
        machine, fullname, dirname, basename = fullpath(inputlist[i])
        inputlist[i] = fullname

        try:
            #check to make sure that the filename string doesn't have any
            # wackiness to it.
            filename_check(inputlist[i])
            
            # input files must exist - also handle automounting.
            if not access_check(inputlist[i], os.F_OK):
                raise EncpError(errno.ENOENT, inputlist[i], e_errors.USERERROR)

            # input files must have read permissions.
            if not access_check(inputlist[i], os.R_OK):
                raise EncpError(errno.EACCES, inputlist[i], e_errors.USERERROR)

            #Since, the file exists, we can get its stats.
            statinfo = os.stat(inputlist[i])

            # input files can't be directories
            if not stat.S_ISREG(statinfo[stat.ST_MODE]):
                raise EncpError(errno.EISDIR, inputlist[i], e_errors.USERERROR)

            # get the file size
            if "/pnfs/" == inputlist[i][:6]:
                p = pnfs.Pnfs(inputlist[i])
                p.get_file_size()
                file_size.append(p.file_size)
                                                   
	    #This would work if pnfs supported NFS version 3.  Untill it does
            # this can not be used in conjuction with large file support.
            else:
                file_size.append(long(statinfo[stat.ST_SIZE]))

            # we cannot allow 2 input files to be the same
            # this will cause the 2nd to just overwrite the 1st
            try:
                match_index = inputlist[:i].index(inputlist[i])
                
                raise EncpError(None,
                                'Duplicate entry %s'%(inputlist[match_index],),
                                e_errors.USERERROR)
            except ValueError:
                pass  #There is no error.

        except KeyboardInterrupt:
            exc, msg, tb = sys.exc_info()
            raise exc, msg, tb
        except EncpError, detail:
            exc, msg, tb = sys.exc_info()
            size = get_file_size(inputlist[i])
            print_data_access_layer_format(inputlist[i], "", size,
                                           {'status':(msg.type, msg.strerror)})
            quit()
        except (OSError, IOError), detail:
            exc, msg, tb = sys.exc_info()
            size = get_file_size(inputlist[i])
            print_data_access_layer_format(
                inputlist[i], "", size,
                {'status':(errno.errorcode[msg.errno], str(msg))})
            quit()

    return (inputlist, file_size)

# check the output file list for consistency
# generate names based on input list if required
#"inputlist" is the list of input files.  "output" is a list with one element.

def outputfile_check(inputlist, output, dcache):
    # can only handle 1 input file copied to 1 output file
    # or multiple input files copied to 1 output directory or /dev/null
    if len(output)>1:
        raise EncpError(None,
                        'Cannot have multiple output files',
                        e_errors.USERERROR)
        #print_data_access_layer_format('',output[0],0,{'status':(
        #    'USERERROR','Cannot have multiple output files')})
        #quit()

    nfiles = len(inputlist)
    outputlist = []

    # Make sure we can open the files. If we can't, we bomb out to user
    # loop over all input files and generate full output file names
    for i in range(nfiles):

        #If output location is /dev/null, skip the checks.
        if output[0] == '/dev/null':
            outputlist.append(output[0])
            continue

        try:
            imachine, ifullname, idir, ibasename = fullpath(inputlist[i])
            omachine, ofullname, odir, obasename = fullpath(output[0])

            #If the output location is a directory, put the name on the end.
            #If it already is the full file name, check to see if the parent
            # directory exits.
            if access_check(ofullname, os.F_OK):
                if os.path.isdir(ofullname):
                    #Reset the ofullname and related variables with the
                    # basname included.
                    ofullname=os.path.join(ofullname, ibasename)
                    omachine, ofullname, odir, obasename = fullpath(ofullname)
            elif not access_check(odir, os.F_OK):
                #If the directory does not exist, raise error.
                raise EncpError(errno.ENOENT, odir, e_errors.USERERROR)

            #check to make sure that the filename string doesn't have any
            # wackiness to it.
            filename_check(ofullname)

            #There are four (4) possible senerios for the following test(s).
            #The two conditions are:
            # 1) If dache involked encp.
            # 2) If the file does not exist or not.

            #Test case when used by a user and the file does not exist (as is
            # should be).
            if not access_check(ofullname, os.F_OK) and not dcache:
                #Check if the filesystem is corrupted.
                if ofullname in os.listdir(odir):
                    raise EncpError(getattr(errno, 'EFSCORRUPTED', 'EIO'),
                                    "Filesystem is corrupt.", e_errors.OSERROR)
                #Check for permissions.
                elif access_check(odir, os.W_OK):
                    outputlist.append(ofullname)
                else:
                    raise EncpError(errno.EACCES,ofullname,e_errors.USERERROR)
                
            #File exists when run by a normal user.
            elif access_check(ofullname, os.F_OK) and not dcache:
                raise EncpError(errno.EEXIST, ofullname, e_errors.USERERROR)

            #The file does not already exits and it is a dcache transfer.
            elif not access_check(ofullname, os.F_OK) and dcache:
                #Check if the filesystem is corrupted.
                if ofullname in os.listdir(odir):
                    raise EncpError(getattr(errno, 'EFSCORRUPTED', 'EIO'),
                                    "Filesystem is corrupt.", e_errors.OSERROR)
                else:
                    raise EncpError(errno.ENOENT,ofullname,e_errors.USERERROR)

            #The file exits, as it should, for a dache transfer.
            elif access_check(ofullname, os.F_OK) and dcache:
                #Check for permissions.
                if access_check(ofullname, os.W_OK):
                    outputlist.append(ofullname)
                else:
                    raise EncpError(errno.EACCES,ofullname,e_errors.USERERROR)
            else:
                raise EncpError(None,
                                "Failed outputfile check for: %s" % ofullname,
                                e_errors.UNKNOWN)

            #Make sure the output file system can handle a file as big as
            # the input file.  Also, make sure that the maximum size that
            # the wrapper and library use are greater than the filesize.
            # These function will raise an EncpError on an error.
            if "/pnfs/" == inputlist[i][:6]: #READS
                filesystem_check(outputlist[i], inputlist[i])
            else: #WRITES
                librarysize_check(outputlist[i], inputlist[i])
                wrappersize_check(outputlist[i], inputlist[i])
                #filesystem_check(outputlist[i], inputlist[i])

            # we cannot allow 2 output files to be the same
            # this will cause the 2nd to just overwrite the 1st
            # In principle, this is already taken care of in the
            # inputfile_check, but do it again just to make sure in case
            # someone changes protocol
            try:
                match_index = inputlist[:i].index(inputlist[i])
                raise EncpError(None,
                                'Duplicate entry %s'%(inputlist[match_index],),
                                e_errors.USERERROR)
            except ValueError:
                pass  #There is no error.

        except EncpError:
            exc, msg, tb = sys.exc_info()
            size = get_file_size(ifullname)
            print_data_access_layer_format('', ofullname, size,
                                           {'status':(msg.type, msg.strerror)})
            quit()

    if outputlist[0] == "/dev/null":
        return outputlist
    elif dcache:
        return outputlist
    else:
        #now try to atomically create each file
        for f in outputlist:
            try:
                fd = atomic.open(f, mode=0666) #raises OSError on error.
                if fd<0:
                    #The return code is the negitive return value.
                    error = int(math.fabs(fd))
                    raise OSError(error,os.strerror(error))

                os.close(fd)

            except OSError:
                exc, msg, tb = sys.exc_info()
                error = errno.errorcode.get(msg.errno,
                                            errno.errorcode[errno.ENODATA])
                print_data_access_layer_format('', f, 0,
                                               {'status': (error, str(msg))})
                
                quit()

    return outputlist

#######################################################################

def file_check(e):
    # check the output pnfs files(s) names
    # bomb out if they exist already
    inputlist, file_size = inputfile_check(e.input)
    n_input = len(inputlist)

    Trace.message(TICKET_LEVEL, "file count=" + str(n_input))
    Trace.message(TICKET_LEVEL, "inputlist=" + str(inputlist))
    Trace.message(TICKET_LEVEL, "file_size=" + str(file_size))

    # check (and generate) the output pnfs files(s) names
    # bomb out if they exist already
    outputlist = outputfile_check(e.input, e.output, e.put_cache)

    Trace.message(TICKET_LEVEL, "outputlist=" + str(outputlist))

    return n_input, file_size, inputlist, outputlist

#######################################################################

def get_clerks(bfid=None):

    #Snag the configuration server client for the system that contains the
    # file clerk where the file was stored.  This is determined based on
    # the bfid's brand.
    csc = get_csc(bfid)

    #Get the file clerk information.
    fcc = file_clerk_client.FileClient(csc, bfid)
    if not fcc:
        raise EncpError(errno.ENOPROTOOPT,
                        "File clerk not available",
                        e_errors.NET_ERROR)
        
    #Get the volume clerk information.
    vcc = volume_clerk_client.VolumeClerkClient(csc)
    if not vcc:
        raise EncpError(errno.ENOPROTOOPT,
                        "File clerk not available",
                        e_errors.NET_ERROR)

    return vcc, fcc

############################################################################

def get_pinfo(p):
    p.pstatinfo()
            
    # get some debugging info for the ticket
    pinf = {}
    for k in [ 'pnfsFilename','gid', 'gname','uid', 'uname',
               'major','minor','rmajor','rminor',
               'mode','pstat' ] :
        try:
            pinf[k]=getattr(p,k)
        except AttributeError:
            pinf[k]="None"
    pinf['inode'] = 0                  # cpio wrapper needs this also

    return pinf

############################################################################

def open_control_socket(listen_socket, mover_timeout):

    read_fds,write_fds,exc_fds=select.select([listen_socket], [],
                                             [listen_socket], mover_timeout)

    #If there are no successful connected sockets, then select timedout.
    if not read_fds:
        raise EncpError(errno.ETIMEDOUT,
                        "Mover did not call back.", e_errors.TIMEDOUT)
        #msg = os.strerror(errno.ETIMEDOUT)
        #Trace.message(ERROR_LEVEL, msg)
        #raise socket.error, (errno.ETIMEDOUT, msg)
    
    control_socket, address = listen_socket.accept()

    if not hostaddr.allow(address):
        control_socket.close()
        raise EncpError(errno.EPERM, "host %s not allowed" % address[0],
                        e_errors.NOT_ALWD_EXCEPTION)
        #msg = "host %s not allowed" % address[0]
        #Trace.message(ERROR_LEVEL, msg)
        #raise socket.error, (errno.EACCES, msg)

    try:
        ticket = callback.read_tcp_obj(control_socket)
    except e_errors.TCP_EXCEPTION:
        raise EncpError(errno.EPROTO, "Unable to obtain mover responce",
                        e_errors.TCP_EXCEPTION)
        #msg = e_errors.TCP_EXCEPTION
        #Trace.message(ERROR_LEVEL, msg)
        #raise socket.error, (e_errors.NET_ERROR, msg)

    #try:
    #    a = ticket['mover']['callback_addr']
    #except KeyError:
    #    msg = "mover did not return mover info.  " + \
    #          str(ticket.get("status", None))
    #    Trace.message(ERROR_LEVEL, msg)
    #    raise socket.error, (errno.EPROTO, msg )

    return control_socket, address, ticket
    
##############################################################################

def open_data_socket(mover_addr, mode):
    data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    flags = fcntl.fcntl(data_path_socket.fileno(), FCNTL.F_GETFL)
    fcntl.fcntl(data_path_socket.fileno(), FCNTL.F_SETFL,
                flags | FCNTL.O_NONBLOCK)

    #set up any special network load-balancing voodoo
    interface=host_config.check_load_balance(mode=mode, dest=mover_addr[0])
    #load balencing...
    if interface:
        ip = interface.get('ip')
        if ip:
            try:
                #This is were the interface selection magic occurs.
                host_config.setup_interface(mover_addr[0], ip)
            except socket.error, msg:
                Trace.log(e_errors.ERROR, "setup interface: %s %s" % (ip, msg))
            try:
                data_path_socket.bind((ip, 0))
                Trace.log(e_errors.INFO, "bind %s" % (ip,))
            except socket.error, msg:
                Trace.log(e_errors.ERROR, "bind: %s %s" % (ip, msg))

    try:
        data_path_socket.connect(mover_addr)
        error = 0
    except socket.error, msg:
        #We have seen that on IRIX, when the connection succeds, we
        # get an ISCONN error.
        if hasattr(errno, 'EISCONN') and msg[0] == errno.EISCONN:
            pass
        #The TCP handshake is in progress.
        elif msg[0] == errno.EINPROGRESS:
            pass
        #A real or fatal error has occured.  Handle accordingly.
        else:
            raise socket.error, msg

    #Check if the socket is open for reading and/or writing.
    r, w, ex = select.select([data_path_socket], [data_path_socket], [], 30)

    if r or w:
        #Get the socket error condition...
        rtn = data_path_socket.getsockopt(socket.SOL_SOCKET,
                                          socket.SO_ERROR)
        error = 0
    #If the select didn't return sockets ready for read or write, then the
    # connection timed out.
    else:
        raise socket.error, (errno.ETIMEDOUT, os.strerror(errno.ETIMEDOUT))

    #If the return value is zero then success, otherwise it failed.
    if rtn != 0:
        raise socket.error, (rtn, os.strerror(rtn))

    #Restore flag values to blocking mode.
    fcntl.fcntl(data_path_socket.fileno(), FCNTL.F_SETFL, flags)

    return data_path_socket

############################################################################

#Initiats the handshake with the mover.
#Args:
# listen_socket - The listen socket returned from a callback.get_callback().
# work_tickets - List of dictionaries, where each dictionary represents
#                a transfer.
# mover_timeout - number of seconds to wait for mover to make connection.
# max_retry - the allowable number of times to retry a specific request
#             before giving up.
# verbose - the verbose level of output.
#Returns:
# (control_socket, 

def mover_handshake(listen_socket, work_tickets, mover_timeout):
    ##19990723:  resubmit request after 15minute timeout.  Since the
    # unique_id is unchanged the library manager should not get
    # confused by duplicate requests.
    #timedout=0
    while 1:  ###not (timedout or reply_read):
        #Attempt to get the control socket connected with the mover.
        try:
            control_socket, mover_address, ticket = open_control_socket(
                listen_socket, mover_timeout)

        except (socket.error, EncpError), detail:
            exc, msg, tb = sys.exc_info()
            if msg.errno == errno.ETIMEDOUT:
                ticket = {'status':(e_errors.RESUBMITTING, None)}
            elif hasattr(msg, "type"):
                ticket = {'status':(msg.type, msg.strerror)}                
            else:
                ticket = {'status':(e_errors.NET_ERROR, msg.strerror)}
                
            #Since an error occured, just return it.
            return None, None, ticket

        Trace.message(TICKET_LEVEL, "MOVER HANDSHAKE")
        Trace.message(TICKET_LEVEL, pprint.pformat(ticket))

        #verify that the id is one that we are excpeting and not one that got
        # lost in the ether.
        for i in range(0, len(work_tickets)):
            if work_tickets[i]['unique_id'] == ticket['unique_id']:
                break #Success, control socket opened!
            
        else: #Didn't find matching id.
            close_descriptors(control_socket)

            list_of_ids = []
            for j in range(0, len(work_tickets)):
                list_of_ids.append(work_tickets[j]['unique_id'])

            Trace.log(e_errors.INFO,
                      "mover handshake: mover impostor called back\n"
                      "   mover address: %s   got id: %s   expected: %s\n"
                      "   ticket=%s" %
                      (mover_address,ticket['unique_id'], list_of_ids, ticket))
            
            continue

        # ok, we've been called back with a matched id - how's the status?
        if ticket['status'] != (e_errors.OK, None):
            return None, None, ticket

        try:
            mover_addr = ticket['mover']['callback_addr']
        except KeyError:
            exc, msg, tb = sys.exc_info()
            sys.stderr.write("Sub ticket 'mover' not found.\n")
            sys.stderr.write("%s: %s\n" % (str(exc), str(msg)))
            sys.stderr.write(pprint.pformat(ticket)+"\n")
            if ticket.get('status', (None, None))[0] == e_errors.OK:
                ticket['status'] = (str(exc), str(msg))
            return None, None, ticket

        #Determine if reading or writing.  This only has importance on
        # mulithomed machines were an interface needs to be choosen based
        # on reading and writing usages/rates of the interfaces.
        if ticket['outfile'][:5] == "/pnfs":
            mode = 1
        else:
            mode = 0

        #Attempt to get the data socket connected with the mover.
        try:
            data_path_socket = open_data_socket(mover_addr, mode)

            if not data_path_socket:
                raise socket.error,(errno.ENOTCONN,os.strerror(errno.ENOTCONN))

        except (socket.error,), detail:
            exc, msg, tb = sys.exc_info()
            ticket = {'status':(e_errors.NET_ERROR, str(msg))}
            #Trace.log(e_errors.INFO, str(msg))
            
            #Since an error occured, just return it.
            return None, None, ticket

        #If we got here then the status is OK.
        ticket['status'] = (e_errors.OK, None)
        #Include new info from mover.
        work_tickets[i] = ticket

        #The following three lines are usefull for testing error handling.
        #control_socket.close()
        #data_path_socket.close()
        #ticket['status'] = (e_errors.NET_ERROR, "because I closed them")

        return control_socket, data_path_socket, ticket

############################################################################

def submit_one_request(ticket):
    ##start of resubmit block
    #Trace.trace(17,"write_to_hsm q'ing: %s"%(ticket,))

    if ticket['retry']:
        Trace.message(TO_GO_LEVEL, "RETRY COUNT:" + str(ticket['retry']))

    csc = get_csc(ticket)
    Trace.message(CONFIG_LEVEL, format_class_for_print(csc, "csc"))

    #Send work ticket to LM
    #Get the library manager info information.
    lmc = library_manager_client.LibraryManagerClient(
        csc, ticket['vc']['library'] + ".library_manager")
    if ticket['infile'][:5] == "/pnfs":
        responce_ticket = lmc.read_from_hsm(ticket)
    else:
        responce_ticket = lmc.write_to_hsm(ticket)

    if responce_ticket['status'][0] != e_errors.OK :
        Trace.message(ERROR_LEVEL, "Submition to LM failed: " + \
                      str(responce_ticket['status']))
        Trace.log(e_errors.NET_ERROR,
                  "submit_one_request: Ticket submit failed for %s"
                  " - retrying" % ticket['infile'])

    return responce_ticket

############################################################################

#mode should only contain two values, "read", "write".
def open_local_file(filename, mode):
    #Determine the os.open() flags to use.
    if mode == "write":
            flags = os.O_RDONLY
    elif mode == "read":
        if filename == "/dev/null":
            flags = os.O_WRONLY
        else:
            flags = os.O_WRONLY | os.O_CREAT
    else:
        done_ticket = {'status':(e_errors.UNKNOWN,
                                 "Unable to open local file.")}
        return done_ticket

    #Try to open the local file for read/write.
    try:
        #if filename == "/dev/null":
        #    local_fd = os.open("/dev/null", flags)
        #else:
        local_fd = os.open(filename, flags, 0)
    except OSError, detail:
        #USERERROR is on the list of non-retriable errors.  Because of
        # this the return from handle_retries will remove this request
        # from the list.  Thus avoiding issues with the continue and
        # range(submitted).
        done_ticket = {'status':(e_errors.USERERROR, detail)}
        return done_ticket

    done_ticket = {'status':(e_errors.OK, None), 'fd':local_fd}
    return done_ticket

############################################################################

def receive_final_dialog(control_socket):
    # File has been sent - wait for final dialog with mover. 
    # We know the file has hit some sort of media.... 
    # when this occurs. Create a file in pnfs namespace with
    #information about transfer.
    
    try:
        done_ticket = callback.read_tcp_obj(control_socket)
    except e_errors.TCP_EXCEPTION, msg:
        done_ticket = {'status':(e_errors.TCP_EXCEPTION,
                                 msg)}
        
    return done_ticket
        
############################################################################

#Returns two-tuple.  First is dictionary with 'status' element.  The next
# is an integer of the crc value.  On error returns 0.
def transfer_file(input_fd, output_fd, control_socket, request, tinfo, e):

    encp_crc = 0

    #Read/Write in/out the data to/from the mover and write/read it out to
    # file.  Also, total up the crc value for comparison with what was
    # sent from the mover.
    try:
        if e.chk_crc != 0:
            crc_flag = 1
        else:
            crc_flag = 0

        encp_crc = EXfer.fd_xfer(input_fd, output_fd, request['file_size'],
                                 e.bufsize, crc_flag, 0)
        EXfer_ticket = {'status':(e_errors.OK, None)}
    except EXfer.error, msg:
        if msg.args[1] == errno.ENOSPC: #This should be non-retriable.
            EXfer_ticket = {'status':(e_errors.NOSPACE, str(msg))}
        else:
            EXfer_ticket = {'status':(e_errors.IOERROR, str(msg))}
        Trace.log(e_errors.WARNING, "transfer file EXfer error: %s" % (msg,))

    # File has been read - wait for final dialog with mover.
    Trace.message(TRANSFER_LEVEL,"Waiting for final mover dialog.  elapsed=%s"
                  % (time.time() - tinfo['encp_start_time'],))
    #Even though the functionality is there for this to be done in
    # handle requests, this should be recieved outside since there must
    # be one... not only receiving one on error.
    if EXfer_ticket['status'][0] == e_errors.NOSPACE:
        done_ticket = {'status':(e_errors.OK, None)}
    else:
        done_ticket = receive_final_dialog(control_socket)

    if not e_errors.is_retriable(done_ticket['status'][0]):
        return done_ticket, 0
    elif not e_errors.is_retriable(EXfer_ticket['status'][0]):
        return EXfer_ticket, 0
    elif done_ticket['status'][0] != (e_errors.OK):
        return done_ticket, 0
    elif EXfer_ticket['status'][0] != (e_errors.OK):
        return EXfer_ticket, 0
    else:
        return done_ticket, encp_crc #Success.

############################################################################

def check_crc(done_ticket, chk_crc, my_crc):

    # Check the CRC
    if chk_crc:
        mover_crc = done_ticket['fc'].get('complete_crc', None)
        if mover_crc == None:
            msg =   "warning: mover did not return CRC; skipping CRC check\n"
            sys.stderr.write(msg)
            #done_ticket['status'] = (e_errors.NO_CRC_RETURNED, msg)

        elif mover_crc != my_crc :
            msg = "CRC mismatch: %d != %d" % (mover_crc, my_crc)
            done_ticket['status'] = (e_errors.CRC_ERROR, msg)

############################################################################

def set_outfile_permissions(ticket):
    #Attempt to get the input files permissions and set the output file to
    # match them.
    if ticket['outfile'] != "/dev/null":
        try:
            perms = os.stat(ticket['infile'])[stat.ST_MODE]
            os.chmod(ticket['outfile'], perms)
            ticket['status'] = (e_errors.OK, None)
        except OSError, msg:
            Trace.log(e_errors.INFO, "chmod %s failed: %s" % \
                      (ticket['outfile'], msg))
            ticket['status'] = (e_errors.USERERROR,
                                "Unable to set permissions.")

############################################################################

#This function prototype looking thing is here so that there is a defined
# handle_retries() before internal_handle_retries() is defined.  While
# python handles this without the pre-definition, mylint.py does not.
def handle_retries(*args):
    pass

#This internal version of handle retries should only be called from inside
# of handle_retries().
def internal_handle_retries(request_list, request_dictionary, error_dictionary,
                            control_socket, encp_intf):
    #Set the encp_intf to internal test values to two.  This means
    # there is only one check made on internal problems.
    remember_retries = encp_intf.max_retry
    remember_resubmits = encp_intf.max_resubmit
    encp_intf.max_retry = 2
    encp_intf.max_resubmit = 2
    
    internal_result_dict = handle_retries(request_list, request_dictionary,
                                          error_dictionary, control_socket,
                                          encp_intf)

    #Set the max resend parameters to original values.
    encp_intf.max_retry = remember_retries
    encp_intf.max_resubmit = remember_resubmits

    return internal_result_dict

def handle_retries(request_list, request_dictionary, error_dictionary,
                   control_socket, encp_intf):
    #Extract for readability.
    max_retries = encp_intf.max_retry
    max_submits = encp_intf.max_resubmit
    verbose = encp_intf.verbose

    #request_dictionary must have 'retry' as an element.
    #error_dictionary must have 'status':(e_errors.XXX, "explanation").

    #These fields need to be retrieved in this fashion.  If the transfer
    # failed before encp could determine which transfer failed (aka failed
    # opening/reading the/from contol socket) then only the 'status' field
    # of both the request_dictionary and error_dictionary are guarenteed to
    # exist (although some situations will add others).
    infile = request_dictionary.get('infile', '')
    outfile = request_dictionary.get('outfile', '')
    file_size = request_dictionary.get('file_size', 0)
    retry = request_dictionary.get('retry', 0)
    
    resubmits = request_list[0].get('resubmits', 0)
    
    dict_status = error_dictionary.get('status', (e_errors.OK, None))

    #Get volume info from the volume clerk.
    #Need to check if the volume has been marked NOACCESS since it
    # was checked last.  This should only apply to reads.
    if request_dictionary.get('fc', {}).has_key('external_label'):
        # get a configuration server
        csc = get_csc(request_dictionary)

        # get the volume clerk responce.
        vcc = volume_clerk_client.VolumeClerkClient(csc)
        vc_reply = vcc.inquire_vol(request_dictionary['fc']['external_label'])
        vc_status = vc_reply['status']
    else:
        vc_status = (e_errors.OK, None)

    #If there is a control socket open and there is data to read, then read it.
    socket_status = (e_errors.OK, None)
    socket_dict = {'status':socket_status}
    if control_socket:
        #Determine if the control socket has some errror to report.
        read_fd, write_fd, exc_fd = select.select([control_socket],
                                                  [], [], 15)
        #check control socket for error.
        if read_fd:
            socket_dict = receive_final_dialog(control_socket)
            socket_status = socket_dict.get('status', (e_errors.OK , None))
            request_dictionary = combine_dict(socket_dict, request_dictionary)

    #The volume clerk set the volume NOACCESS.
    if vc_status[0] != e_errors.OK:
        status = vc_status
    #Set status if there was an error recieved from control socket.
    elif socket_status[0] != e_errors.OK:
        status = socket_status
    #Use the ticket status.
    else:
        status = dict_status

        
    #If there is no error, then don't do anything
    if status == (e_errors.OK, None):
        result_dict = {'status':(e_errors.OK, None), 'retry':retry,
                       'resubmits':resubmits,
                       'queue_size':len(request_list)}
        result_dict = combine_dict(result_dict, socket_dict)
        return result_dict

    #If the mover doesn't call back after max_submits number of times, give up.
    if max_submits != None and resubmits >= max_submits:
        Trace.message(ERROR_LEVEL,
                      "To many resubmitions for %s -> %s."%(infile,outfile))
        status = (e_errors.TOO_MANY_RESUBMITS, status)

    #If the transfer has failed to many times, remove it from the queue.
    # Since TOO_MANY_RETRIES is non-retriable, set this here.
    if max_retries != None and retry >= max_retries:
        Trace.message(ERROR_LEVEL,
                      "To many retries for %s -> %s."%(infile,outfile))
        status = (e_errors.TOO_MANY_RETRIES, status)

    #If the error is not retriable, remove it from the request queue.  There
    # are two types of non retriable errors.  Those that cause the transfer
    # to be aborted, and those that in addition to abborting the transfer
    # tell the operator that someone needs to investigate what happend.
    if not e_errors.is_retriable(status[0]):
        #Print error to stdout in data_access_layer format. However, only
        # do so if the dictionary is full (aka. the error occured after
        # the control socket was successfully opened).  Control socket
        # errors are printed elsewere (for reads only).
        error_dictionary['status'] = status
        #By checking those that aren't of significant length, we only
        # print these out on writes.
        if len(request_dictionary) > 3:
            print_data_access_layer_format(infile, outfile, file_size,
                                           error_dictionary)

        if status[0] in e_errors.raise_alarm_errors:
            Trace.alarm(e_errors.WARNING, status[0], {
                'infile':infile, 'outfile':outfile, 'status':status[1]})

        try:
            #Try to delete the request.  In the event that the connection
            # didn't let us determine which request failed, don't worry.
            del request_list[request_list.index(request_dictionary)]
            queue_size = len(request_list)
        except KeyboardInterrupt:
            exc, msg, tb = sys.exc_info()
            raise exc, msg, tb
        except (KeyError, ValueError):
            queue_size = len(request_list) - 1

        #This is needed on reads to send back to the calling function
        # that ths error means that there should be none left in the queue.
        # On writes, if it gets this far it should already be 0 and doesn't
        # effect anything.
        if status[0] == e_errors.TOO_MANY_RESUBMITS:
            queue_size = 0
        
        result_dict = {'status':status, 'retry':retry,
                       'resubmits':resubmits,
                       'queue_size':queue_size}

    #When nothing was recieved from the mover and the 15min has passed,
    # resubmit all entries in the queue.  Leave the unique id the same.
    # Even though for writes there is only one entry in the active request
    # list at a time, submitting like this will still work.
    elif status[0] == e_errors.RESUBMITTING:
        ###Is the work done here duplicated in the next commented code line???
        request_dictionary['resubmits'] = resubmits + 1

        for req in request_list:
            try:
                #Increase the resubmit count.
                req['resubmits'] = req.get('resubmits', 0) + 1

                #Before resubmitting, there are some fields that the library
                # manager and mover don't expect to receive from encp,
                # these should be removed.
                for item in ("mover", ):
                    try:
                        del req[item]
                    except KeyError:
                        pass

                #Since a retriable error occured, resubmit the ticket.
                lm_responce = submit_one_request(req)

            except KeyboardInterrupt:
                exc, msg, tb = sys.exc_info()
                raise exc, msg, tb
            except:
                exc, msg, tb = sys.exc_info()
                sys.stderr.write("%s: %s\n" % (str(exc), str(msg)))

            #Now it get checked.  But watch out for the recursion!!!
            internal_result_dict = internal_handle_retries([req], req,
                                                           lm_responce,
                                                           None, encp_intf)
            if internal_result_dict['status'][0] != e_errors.OK:
                status = internal_result_dict['status']
            else:
                status = (e_errors.RESUBMITTING, None)
                
            Trace.log(e_errors.WARNING, (e_errors.RETRY, req.get('unique_id',
                                                                 None)))

            result_dict = {'status':status,
                           'retry':request_dictionary.get('retry', 0),
                           'resubmits':request_dictionary.get('resubmits', 0),
                           'queue_size':len(request_list)}

    #Change the unique id so the library manager won't remove the retry
    # request when it removes the old one.  Do this only when there was an
    # actuall error, not just a timeout.  Also, increase the retry count by 1.
    else:
        #Log the intermidiate error as a warning instead as a full error.
        Trace.log(e_errors.WARNING, status)

        #Get a new unique id for the transfer request since the last attempt
        # ended in error.
        request_dictionary['unique_id'] = generate_unique_id()

        #Keep retrying this file.
        try:
            #Increase the retry count.
            request_dictionary['retry'] = retry + 1
            
            #Before resending, there are some fields that the library
            # manager and mover don't expect to receive from encp,
            # these should be removed.
            for item in ("mover", ):
                try:
                    del request_dictionary[item]
                except KeyError:
                    pass
                
            #Since a retriable error occured, resubmit the ticket.
            lm_responce = submit_one_request(request_dictionary)

        except KeyError:
            lm_responce = {'status':(e_errors.NET_ERROR,
                            "Unable to obtain responce from library manager.")}
            sys.stderr.write("Error processing resubmition of %s.\n" %
                             (request_dictionary['unique_id']))
            sys.stderr.write(pprint.pformat(request_dictionary)+"\n")
            
        #Now it get checked.  But watch out for the recursion!!!
        internal_result_dict = internal_handle_retries([request_dictionary],
                                                       request_dictionary,
                                                       lm_responce,
                                                       None, encp_intf)

        if internal_result_dict['status'][0] != e_errors.OK:
            status = internal_result_dict['status']
        else:
            status = (e_errors.RETRY, request_dictionary['unique_id'])
            
        Trace.log(e_errors.WARNING, (e_errors.RETRY, status))

        result_dict = {'status':status,
                       'retry':request_dictionary.get('retry', 0),
                       'resubmits':request_dictionary.get('resubmits', 0),
                       'queue_size':len(request_list)}

    #If we get here, then some type of error occured.  This means one of
    # three things happend.
    #1) The transfer was abborted.
    #    a) A non-retriable error occured once.
    #    b) A retriable error occured too many times.
    #2) The request(s) was/were resubmited.
    #    a) No mover called back before the listen socket timed out.
    #3) The request(s) was/were retried.
    #    a) A retriable error occured.
    return result_dict

############################################################################

def calculate_rate(done_ticket, tinfo):
    # calculate some kind of rate - time from beginning to wait for
    # mover to respond until now. This doesn't include the overheads
    # before this, so it isn't a correct rate. I'm assuming that the
    # overheads I've neglected are small so the quoted rate is close
    # to the right one.  In any event, I calculate an overall rate at
    # the end of all transfers

    #calculate MB relatated stats
    bytes_per_MB = 1024 * 1024
    MB_transfered = float(done_ticket['file_size']) / float(bytes_per_MB)

    #For readablilty...
    id = done_ticket['unique_id']

    #Make these variables easier to use.
    network_time = tinfo.get('%s_elapsed_time' % (id,), 0)
    complete_time = tinfo.get('%s_elapsed_finished' % (id,), 0)
    drive_time = done_ticket['times'].get('transfer_time', 0)

    if done_ticket['work'] == "read_from_hsm":
        preposition = "from"
    else: #write "to"
        preposition = "to"
    
    if done_ticket['status'][0] == e_errors.OK:

        if complete_time != 0:
            tinfo['overall_rate_%s'%(id,)] = MB_transfered / complete_time
        else:
            tinfo['overall_rate_%s'%(id,)] = 0.0
        if network_time != 0:
            tinfo['network_rate_%s'%(id,)] = MB_transfered / network_time
        else:
            tinfo['network_rate_%s'%(id,)] = 0.0            
        if drive_time != 0:
            tinfo['drive_rate_%s'%(id,)] = MB_transfered / drive_time
        else:
            tinfo['drive_rate_%s'%(id,)] = 0.0
            
        print_format = "Transfer %s -> %s:\n" \
                 "\t%d bytes copied %s %s at %.3g MB/S\n " \
                 "\t(%.3g MB/S network) (%.3g MB/S drive)\n " \
                 "\tdrive_id=%s drive_sn=%s drive_vendor=%s\n" \
                 "\tmover=%s media_changer=%s   elapsed=%.02f"
        
        log_format = "  %s %s -> %s: "\
                     "%d bytes copied %s %s at %.3g MB/S " \
                     "(%.3g MB/S network) (%.3g MB/S drive) " \
                     "mover=%s " \
                     "drive_id=%s drive_sn=%s drive_venor=%s elapsed=%.05g "\
                     "{'media_changer' : '%s', 'mover_interface' : '%s', " \
                     "'driver' : '%s'}"

        print_values = (done_ticket['infile'],
                        done_ticket['outfile'],
                        done_ticket['file_size'],
                        preposition,
                        done_ticket["fc"]["external_label"],
                        tinfo["overall_rate_%s"%(id,)],
                        tinfo['network_rate_%s'%(id,)],
                        tinfo["drive_rate_%s"%(id,)],
                        done_ticket["mover"]["product_id"],
                        done_ticket["mover"]["serial_num"],
                        done_ticket["mover"]["vendor_id"],
                        done_ticket["mover"]["name"],
                        done_ticket["mover"].get("media_changer",
                                                 e_errors.UNKNOWN),
                        time.time() - tinfo["encp_start_time"])

        log_values = (done_ticket['work'],
                      done_ticket['infile'],
                      done_ticket['outfile'],
                      done_ticket['file_size'],
                      preposition,
                      done_ticket["fc"]["external_label"],
                      tinfo["overall_rate_%s"%(id,)],
                      tinfo["network_rate_%s"%(id,)],
                      tinfo['drive_rate_%s'%(id,)],
                      done_ticket["mover"]["name"],
                      done_ticket["mover"]["product_id"],
                      done_ticket["mover"]["serial_num"],
                      done_ticket["mover"]["vendor_id"],
                      time.time() - tinfo["encp_start_time"],
                      done_ticket["mover"].get("media_changer",
                                               e_errors.UNKNOWN),
                      #socket.gethostbyaddr(done_ticket["mover"]["hostip"])[0],
		      done_ticket["mover"].get('data_ip',
					       done_ticket["mover"]['host']),
                      done_ticket["mover"]["driver"])
        
        Trace.message(DONE_LEVEL, print_format % print_values)

        Trace.log(e_errors.INFO, log_format % log_values, Trace.MSG_ENCP_XFER )

############################################################################

def calculate_final_statistics(bytes, number_of_files, exit_status, tinfo):
    # Calculate an overall rate: all bytes, all time

    #Calculate total running time from the begining.
    now = time.time()
    tinfo['total'] = now - tinfo['encp_start_time']

    #calculate MB relatated stats
    bytes_per_MB = 1024 * 1024
    MB_transfered = float(bytes) / float(bytes_per_MB)

    if tinfo['total']: #protect against division by zero.
        tinfo['MB_per_S_total'] = MB_transfered / tinfo['total']
    else:
        tinfo['MB_per_S_total'] = 0.0

    #get all the drive rates from the dictionary.
    drive_rate  = 0L
    count = 0
    for value in tinfo.keys():
        if string.find(value, "drive_rate") != -1:
            count = count + 1
            drive_rate  = drive_rate  + tinfo[value]
    if count:
        tinfo['MB_per_S_drive'] = drive_rate / count
    else:
        tinfo['MB_per_S_drive'] = 0.0

    #get all the drive rates from the dictionary.
    network_rate  = 0L
    count = 0
    for value in tinfo.keys():
        if string.find(value, "network_rate") != -1:
            count = count + 1
            network_rate  = network_rate  + tinfo[value]
    if count:
        tinfo['MB_per_S_network'] = network_rate / count
    else:
        tinfo['MB_per_S_network'] = 0.0
    
    msg = "%s transferring %s bytes in %s files in %s sec.\n" \
          "\tOverall rate = %.3g MB/sec.  Drive rate = %.3g MB/sec.\n" \
          "\tNetwork rate = %.3g MB/sec.  Exit status = %s."
    
    if exit_status:
        msg = msg % ("Error after", bytes, number_of_files,
                     tinfo['total'], tinfo["MB_per_S_total"],
                     tinfo['MB_per_S_drive'], tinfo['MB_per_S_network'],
                     exit_status)
    else:
        msg = msg % ("Completed", bytes, number_of_files,
                     tinfo['total'], tinfo["MB_per_S_total"],
                     tinfo['MB_per_S_drive'], tinfo['MB_per_S_network'],
                     exit_status)

    done_ticket = {}
    done_ticket['times'] = tinfo
    #set the final status values
    done_ticket['exit_status'] = exit_status
    done_ticket['status'] = (e_errors.OK, msg)
    return done_ticket

############################################################################
#Support functions for writes.
############################################################################

#Args:
# Takes a list of request tickets.
#Returns:
#None
#Verifies that various information in the tickets are correct, valid, spelled
# correctly, etc.
def verify_write_request_consistancy(request_list):

    for request in request_list:

        #Consistancy check for valid pnfs tag values.  These values are
        # placed inside the 'vc' sub-ticket.
        tags = ["file_family", "wrapper", "file_family_width",
                "storage_group", "library"]
        for key in tags:
            #check for values that contain letters, digits and _.
            if not charset.is_in_charset(str(request['vc'][key])):
                msg="Pnfs tag, %s, contains invalid characters." % (key,)
                request['status'] = (e_errors.USERERROR, msg)

                print_data_access_layer_format(request['infile'],
                                               request['outfile'],
                                               request['file_size'],
                                               request)
                quit() #Harsh, but necessary.

        #Verify that the file family width is in fact a non-
        # negitive integer.
        try:
            expression = int(request['vc']['file_family_width']) < 0
            if expression:
                raise ValueError,(e_errors.USERERROR,
                                  request['vc']['file_family_width'])
        except ValueError:
            msg="Pnfs tag, %s, requires a non-negitive integer value."\
                 % ("file_family_width",)
            request['status'] = (e_errors.USERERROR, msg)

            print_data_access_layer_format(request['infile'],
                                           request['outfile'],
                                           request['file_size'],
                                           request)
            quit() #Harsh, but necessary.

############################################################################

def set_pnfs_settings(ticket):

    # create a new pnfs object pointing to current output file
    Trace.trace(20,"write_to_hsm adding to pnfs "+ ticket['outfile'])

    try:
        p=pnfs.Pnfs(ticket['outfile'])
        t=pnfs.Tag(os.path.dirname(ticket['outfile']))
        # save the bfid and set the file size
        p.set_bit_file_id(ticket["fc"]["bfid"])
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except:
        exc, msg, tb = sys.exc_info()
        Trace.log(e_errors.INFO, "Trouble with pnfs: %s %s."
                  % (str(exc), str(msg)))
        ticket['status'] = (str(exc), str(msg))
        return
        
    # store cross reference data
    mover_ticket = ticket.get('mover', {})
    drive = "%s:%s" % (mover_ticket.get('device', 'Unknown'),
                       mover_ticket.get('serial_num','Unknown'))
    try:
        #t.get_file_family()
        p.get_bit_file_id()
        p.get_id()

        p.set_xreference(ticket["fc"]["external_label"],
                         ticket["fc"]["location_cookie"],
                         ticket["fc"]["size"],
                         ticket["vc"]["file_family"],
                         p.pnfsFilename,
                         "", #p.volume_filepath,
                         p.id,
                         "", #p.volume_fileP.id,
                         p.bit_file_id,
                         drive)
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except:
        exc,msg,tb=sys.exc_info()
        Trace.log(e_errors.INFO, "Trouble with pnfs.set_xreference %s %s."
                  % (str(exc), str(msg)))
        ticket['status'] = (str(exc), str(msg))
        return

    try:
        # add the pnfs ids and filenames to the file clerk ticket and store it
        fc_ticket = {}
        fc_ticket["fc"] = ticket['fc'].copy()
        fc_ticket["fc"]["pnfsid"] = p.id
        fc_ticket["fc"]["pnfsvid"] = "" #p.volume_fileP.id
        fc_ticket["fc"]["pnfs_name0"] = p.pnfsFilename
        fc_ticket["fc"]["pnfs_mapname"] = "" #p.mapfile
        fc_ticket["fc"]["drive"] = drive

        csc = get_csc()
        fcc = file_clerk_client.FileClient(csc, ticket["fc"]["bfid"])
        fc_reply = fcc.set_pnfsid(fc_ticket)

        if fc_reply['status'][0] != e_errors.OK:
            Trace.alarm(e_errors.ERROR, fc_reply['status'][0], fc_reply)

        Trace.message(TICKET_LEVEL, "PNFS SET")
        Trace.message(TICKET_LEVEL, pprint.pformat(fc_reply))

        ticket['status'] = fc_reply['status']
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except:
        exc,msg,tb=sys.exc_info()
        Trace.log(e_errors.INFO, "Unable to send info. to file clerk. %s %s."
                  % (str(exc), str(msg)))
        ticket['status'] = (str(exc), str(msg))

    # file size needs to be the LAST metadata to be recorded
    try:
        # set the file size
        p.set_file_size(ticket['file_size'])
    except KeyboardInterrupt:
        exc, msg, tb = sys.exc_info()
        raise exc, msg, tb
    except:
        exc, msg, tb = sys.exc_info()
	ticket['status'] = (str(exc), str(msg))

############################################################################
#Functions for writes.
############################################################################

def create_write_requests(callback_addr, e, tinfo):

    request_list = []

    ninput, file_size, inputlist, outputlist = file_check(e)

    #Obtain the pnfs tag information.
    try:
        t=pnfs.Tag(os.path.dirname(outputlist[0]))

        Trace.message(TICKET_LEVEL, "library=" + str(t.get_library()))
        Trace.message(TICKET_LEVEL, "file family=" + str(t.get_file_family()))
        Trace.message(TICKET_LEVEL,
                      "wrapper =" + str(t.get_file_family_wrapper()))
        Trace.message(TICKET_LEVEL, "width=" + str(t.get_file_family_width()))
        Trace.message(TICKET_LEVEL,
                      "storage group=" + str(t.get_storage_group()))
    except (OSError, IOError), detail:
        print_data_access_layer_format('', '', 0,
                                       {'status':(errno.errorcode[detail.errno]
                                                  ,str(detail))})
        quit()


    #Create the list of file requests that will be sent to the library manager.
    for i in range(0, len(inputlist)):

        #The pnfs file family may be overridden with the options --ephemeral
        # or --file-family.  
        if e.output_file_family:
            file_fam = e.output_file_family
        else:
            file_fam = t.get_file_family()
        
        # make the part of the ticket that encp knows about (there's 
        # more later)
        encp = {}
        encp["basepri"] = e.priority
        encp["adminpri"] = e.admpri
        encp["delpri"] = e.delpri
        encp["agetime"] = e.age_time
        encp["delayed_dismount"] = e.delayed_dismount

        times = {'t0':tinfo['encp_start_time']}

        #If the environmental variable exists, send it to the lm.
        try:
            encp_daq = os.environ['ENCP_DAQ']
        except KeyError:
            encp_daq = None

        uinfo = {}
        uinfo['uid'] = os.getuid()
        uinfo['gid'] = os.getgid()
        try:
            uinfo['gname'] = grp.getgrgid(uinfo['gid'])[0]
        except (ValueError, AttributeError, TypeError, IndexError):
            uinfo['gname'] = 'unknown'
            try:
                uinfo['uname'] = pwd.getpwuid(uinfo['uid'])[0]
            except (ValueError, AttributeError, TypeError, IndexError):
                uinfo['uname'] = 'unknown'
        uinfo['machine'] = os.uname()

        try:
            p = pnfs.Pnfs(outputlist[i])
            pinfo = get_pinfo(p)
        except (OSError, IOError), detail:
            print_data_access_layer_format(
                inputlist[i], outputlist[i], file_size[i],
                {'status':(errno.errorcode[detail.errno], str(detail))})
            quit()
        except (IndexError,), detail:
            print_data_access_layer_format(
                inputlist[i], outputlist[i], file_size[i],
                {'status':(e_errors.OSERROR, "Unable to obtain bfid.")})
            quit()

        # create the wrapper subticket - copy all the user info 
        # into for starters
        wrapper = {}

        # store the pnfs information info into the wrapper
        for key in pinfo.keys():
            wrapper[key] = pinfo[key]

        # the user key takes precedence over the pnfs key
        for key in uinfo.keys():
            wrapper[key] = uinfo[key]

        wrapper["fullname"] = inputlist[i]
        wrapper["type"] = t.get_file_family_wrapper() #ff_wrapper
        #file permissions from PNFS are junk, replace them
        #with the real mode
        wrapper['mode']=os.stat(inputlist[i])[stat.ST_MODE]
        wrapper["sanity_size"] = 65536
        wrapper["size_bytes"] = file_size[i]
        wrapper["mtime"] = int(time.time())

        #Get the information needed to contact the file clerk, volume clerk and
        # the library manager.
        vcc, fcc = get_clerks()
        volume_clerk = {"address"            : vcc.server_address,
                        "library"            : t.get_library(),
                        "file_family"        : file_fam,  #might be overridden
                        # technically width does not belong here,
                        # but it associated with the volume
                        "file_family_width"  : t.get_file_family_width(),
                        "wrapper"            : t.get_file_family_wrapper(),
                        "storage_group"      : t.get_storage_group(),}
        file_clerk = {"address" : fcc.server_address}

        work_ticket = {}
        work_ticket['callback_addr'] = callback_addr
        work_ticket['client_crc'] = e.chk_crc
        work_ticket['encp'] = encp
        work_ticket['encp_daq'] = encp_daq
        work_ticket['fc'] = file_clerk
        work_ticket['file_size'] = file_size[i]
        work_ticket['infile'] = inputlist[i]
        work_ticket['outfile'] = outputlist[i]
        work_ticket['retry'] = 0 #retry,
        work_ticket['times'] = times
        work_ticket['unique_id'] = generate_unique_id()
        work_ticket['vc'] = volume_clerk
        work_ticket['version'] = encp_client_version()
        work_ticket['work'] = "write_to_hsm"
        work_ticket['wrapper'] = wrapper

        request_list.append(work_ticket)
    
    return request_list

############################################################################

def submit_write_request(work_ticket, tinfo, encp_intf):

    Trace.message(TRANSFER_LEVEL, 
                  "Submitting %s write request.  elapsed=%s" % \
                  (work_ticket['outfile'],
                   time.time() - tinfo['encp_start_time']))

    # send the work ticket to the library manager
    while work_ticket['retry'] <= encp_intf.max_retry:

        ##start of resubmit block
        Trace.trace(17,"write_to_hsm q'ing: %s"%(work_ticket,))

        ticket = submit_one_request(work_ticket)
        
        Trace.message(TICKET_LEVEL, "LIBRARY MANAGER")
        Trace.message(TICKET_LEVEL, pprint.pformat(ticket))

        result_dict = handle_retries([work_ticket], work_ticket, ticket,
                                     None, encp_intf)
	if result_dict['status'][0] == e_errors.OK:
	    ticket['status'] = result_dict['status']
            return ticket
        elif result_dict['status'][0] == e_errors.RETRY or \
           e_errors.is_retriable(result_dict['status'][0]):
            continue
        else:
            ticket['status'] = result_dict['status']
            return ticket
	
    ticket['status'] = (e_errors.TOO_MANY_RETRIES, ticket['status'])
    return ticket

############################################################################


def write_hsm_file(listen_socket, work_ticket, tinfo, e):

    #Loop around in case the file transfer needs to be retried.
    while work_ticket.get('retry', 0) <= e.max_retry:
        
        encp_crc = 0 #In case there is a problem, make sure this exists.

        Trace.message(TRANSFER_LEVEL,
                      "Waiting for mover to call back.   elapsed=%s" % \
                      (time.time() - tinfo['encp_start_time'],))

        #Open the control and mover sockets.
        control_socket, data_path_socket, ticket = mover_handshake(
            listen_socket, [work_ticket], e.mover_timeout)

        #Handle any possible errors occured so far.
        result_dict = handle_retries([work_ticket], work_ticket, ticket,
                                     None, e)

        if result_dict['status'][0] == e_errors.RETRY or \
           result_dict['status'][0] == e_errors.RESUBMITTING:
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            ticket = combine_dict(result_dict, ticket)
            return ticket

        #This should be redundant error check.
        if not control_socket or not data_path_socket:
            ticket['status'] = (e_errors.NET_ERROR, "No socket")
            return ticket #This file failed.

        Trace.message(TRANSFER_LEVEL, "Mover called back.  elapsed=%s" %
                      (time.time() - tinfo['encp_start_time'],))
        
        Trace.message(TICKET_LEVEL, "WORK TICKET:")
        Trace.message(TICKET_LEVEL, pprint.pformat(ticket))

        #maybe this isn't a good idea...
        work_ticket = combine_dict(ticket, work_ticket)

        done_ticket = open_local_file(work_ticket['infile'], "write")

        result_dict = handle_retries([work_ticket], work_ticket,
                                     done_ticket, None, e)
        
        if result_dict['status'][0] == e_errors.RETRY:
            close_descriptors(control_socket, data_path_socket)
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            close_descriptors(control_socket, data_path_socket)
            return combine_dict(result_dict, work_ticket)
        else:
            in_fd = done_ticket['fd']

        Trace.message(TRANSFER_LEVEL, "Input file %s opened.   elapsed=%s" % 
                      (work_ticket['infile'],
                       time.time()-tinfo['encp_start_time']))


        #Stall starting the count until the first byte is ready for reading.
        read_fd, write_fd, exc_fd = select.select([], [data_path_socket],
                                                  [data_path_socket], 15 * 60)

        if not write_fd:
            status_ticket = {'status':(e_errors.UNKNOWN,
                                       "No data written to mover.")}
            result_dict = handle_retries([work_ticket], work_ticket,
                                         status_ticket, control_socket, e)
            
            close_descriptors(control_socket, data_path_socket, in_fd)
            
            if result_dict['status'][0] == e_errors.RETRY:
                continue
            elif not e_errors.is_retriable(result_dict['status'][0]):
                return combine_dict(result_dict, work_ticket)

        Trace.message(TRANSFER_LEVEL, "Starting transfer.  elapsed=%s" %
                  (time.time() - tinfo['encp_start_time'],))
            
        lap_time = time.time() #------------------------------------------Start

        done_ticket, encp_crc = transfer_file(in_fd, data_path_socket.fileno(),
                                              control_socket, work_ticket,
                                              tinfo, e)

        tstring = '%s_elapsed_time' % work_ticket['unique_id']
        tinfo[tstring] = time.time() - lap_time #--------------------------End

        try:
            delete_at_exit.register_bfid(done_ticket['fc']['bfid'])
        except (IndexError, KeyError):
            Trace.log(e_errors.INFO, "unable to register bfid")
        
        Trace.message(TRANSFER_LEVEL, "Verifying %s transfer.  elapsed=%s" %
                      (work_ticket['outfile'],
                       time.time()-tinfo['encp_start_time']))

        #Don't need these anymore.
        close_descriptors(control_socket, data_path_socket, in_fd)

        #Verify that everything is ok on the mover side of the transfer.
        result_dict = handle_retries([work_ticket], work_ticket,
                                     done_ticket, None, e)

        if result_dict['status'][0] == e_errors.RETRY:
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            return done_ticket

        Trace.message(TRANSFER_LEVEL, "File %s transfered.  elapsed=%s" %
                      (done_ticket['outfile'],
                       time.time()-tinfo['encp_start_time']))

        Trace.message(TICKET_LEVEL, "FINAL DIALOG")
        Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

        #This function writes errors/warnings to the log file and puts an
        # error status in the ticket.
        check_crc(done_ticket, e.chk_crc, encp_crc) #Check the CRC.

        #Verify that the file transfered in tacted.
        result_dict = handle_retries([work_ticket], work_ticket,
                                     done_ticket, None, e)
        if result_dict['status'][0] == e_errors.RETRY:
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            return combine_dict(result_dict, work_ticket)

        #Set the UNIX file permissions.
        #Writes errors to log file.
        set_outfile_permissions(done_ticket)

        ###What kind of check should be done here?
        #This error should result in the file being left where it is, but it
        # is still considered a failed transfer (aka. exit code = 1 and
        # data access layer is still printed).
        if done_ticket.get('status', (e_errors.OK,None)) != (e_errors.OK,None):
            print_data_access_layer_format(done_ticket['infile'],
                                           done_ticket['outfile'],
                                           done_ticket['file_size'],
                                           done_ticket)
            
        #We know the file has hit some sort of media. When this occurs
        # create a file in pnfs namespace with information about transfer.
        set_pnfs_settings(done_ticket)

        #Verify that the pnfs info was set correctly.
        result_dict = handle_retries([work_ticket], work_ticket,
                                     done_ticket, None, e)
        if result_dict['status'][0] == e_errors.RETRY:
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            return combine_dict(result_dict, work_ticket)

        #Remove the new file from the list of those to be deleted should
        # encp stop suddenly.  (ie. crash or control-C).
        try:
            delete_at_exit.unregister_bfid(done_ticket['fc']['bfid'])
        except (IndexError, KeyError):
            Trace.log(e_errors.INFO, "unable to unregister bfid")
        try:
            delete_at_exit.unregister(done_ticket['outfile']) #localname
        except (IndexError, KeyError):
             Trace.log(e_errors.INFO, "unable to unregister file")
             
        Trace.message(TRANSFER_LEVEL,
                      "File status after verification: %s   elapsed=%s" %
                      (done_ticket['status'],
                       time.time()-tinfo['encp_start_time']))

        return done_ticket

    #If we get out of the while loop, then return error.
    msg = "Failed to write file %s." % work_ticket['outfile']
    done_ticket = {'status':(e_errors.TOO_MANY_RETRIES, msg)}
    return done_ticket

############################################################################

def write_to_hsm(e, tinfo):

    Trace.trace(16,"write_to_hsm input_files=%s  output=%s  verbose=%s  "
                "chk_crc=%s t0=%s" %
                (e.input, e.output, e.verbose, e.chk_crc,
                 tinfo['encp_start_time']))

    # initialize
    bytes = 0L #Sum of bytes all transfered (when transfering multiple files).
    exit_status = 0 #Used to determine the final message text.

    # get a port to talk on and listen for connections
    callback_addr, listen_socket = get_callback_addr(e)

    #Build the dictionary, work_ticket, that will be sent to the
    # library manager.
    request_list = create_write_requests(callback_addr, e, tinfo)

    #If this is the case, don't worry about anything.
    if len(request_list) == 0:
        quit()

    #This will halt the program if everything isn't consistant.
    verify_write_request_consistancy(request_list)

    #Set the max attempts that can be made on a transfer.
    max_attempts(request_list[0]['vc']['library'], e)

    # loop on all input files sequentially
    for i in range(0,len(request_list)):
        lap_start = time.time() #------------------------------------Lap Start

        Trace.message(TO_GO_LEVEL, "FILES LEFT: %s" % str(len(request_list)-i))

        work_ticket = request_list[i]
        Trace.message(TICKET_LEVEL, "WORK_TICKET")
        Trace.message(TICKET_LEVEL, pprint.pformat(work_ticket))

        Trace.message(TRANSFER_LEVEL,
                      "Sending ticket to library manager,  elapsed=%s" %
                      (time.time() - tinfo['encp_start_time'],))

        #Send the request to write the file to the library manager.
        done_ticket = submit_write_request(work_ticket, tinfo, e)

        Trace.message(TICKET_LEVEL, "LM RESPONCE TICKET")
        Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

        Trace.message(TRANSFER_LEVEL,
              "File queued: %s library: %s family: %s bytes: %d elapsed=%s" %
                      (work_ticket['infile'], work_ticket['vc']['library'],
                       work_ticket['vc']['file_family'],
                       long(work_ticket['file_size']),
                       time.time() - tinfo['encp_start_time']))

        #handle_retries() is not required here since submit_write_request()
        # handles its own retrying when an error occurs.
        if done_ticket['status'][0] != e_errors.OK:
            exit_status = 1
            continue

        #Send (write) the file to the mover.
        done_ticket = write_hsm_file(listen_socket, work_ticket, tinfo, e)

        Trace.message(TICKET_LEVEL, "DONE WRITTING TICKET")
        Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

        #handle_retries() is not required here since write_hsm_file()
        # handles its own retrying when an error occurs.
        if done_ticket['status'][0] != e_errors.OK:
            exit_status = 1
            continue

        bytes = bytes + done_ticket['file_size']

        tstring = '%s_elapsed_finished' % done_ticket['unique_id']
        tinfo[tstring] = time.time() - lap_start #-------------------------End

        # calculate some kind of rate - time from beginning 
        # to wait for mover to respond until now. This doesn't 
        # include the overheads before this, so it isn't a 
        # correct rate. I'm assuming that the overheads I've 
        # neglected are small so the quoted rate is close
        # to the right one.  In any event, I calculate an 
        # overall rate at the end of all transfers
        calculate_rate(done_ticket, tinfo)

    # we are done transferring - close out the listen socket
    close_descriptors(listen_socket)

    #Finishing up with a few of these things.
    calc_ticket = calculate_final_statistics(bytes, len(request_list),
                                             exit_status, tinfo)

    #If applicable print new file family.
    if e.output_file_family:
        ff = string.split(done_ticket["vc"]["file_family"], ".")
        Trace.message(DONE_LEVEL, "New File Family Created: %s" % ff)

    Trace.message(TICKET_LEVEL, "DONE TICKET")
    Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

    done_ticket = combine_dict(calc_ticket, done_ticket)

    return done_ticket

#######################################################################
#Support function for reads.
#######################################################################

#######################################################################

# same_cookie(c1, c2) -- to see if c1 and c2 are the same

def same_cookie(c1, c2):
    lc_re = re.compile("[0-9]{4}_[0-9]{9,9}_[0-9]{7,7}")
    match1=lc_re.search(c1)
    match2=lc_re.search(c2)
    if match1 and match2:
        #The location cookie resembles that of null and tape cookies.
        #  Only the last section of the cookie is important.
        try: # just to be paranoid
            return string.split(c1, '_')[-1] == string.split(c2, '_')[-1]
        except (ValueError, AttributeError, TypeError, IndexError):
            return 0
    else:
        #The location cookie is a disk cookie.
        return c1 == c2


#Args:
# Takes in a dictionary of lists of transfer requests sorted by volume.
#Rerturns:
# None
#Verifies that various information in the tickets are correct, valid, spelled
# correctly, etc.
def verify_read_request_consistancy(requests_per_vol):

    bfid_brand = None
    
    vols = requests_per_vol.keys()
    vols.sort()
    for vol in vols:
        request_list = requests_per_vol[vol]

        #Only aquire the first loop.  This might be a performance hit for
        # a large number of requests otherwise.
        if not bfid_brand:
            bfid_brand = requests_per_vol[vol][0]['fc']['bfid']

        for request in request_list:

            #Verify that file clerk and volume clerk returned the same
            # external label.
            if request['vc']['external_label'] != \
               request['fc']['external_label']:
                msg = "Volume and file clerks returned conflicting volumes." \
                      " VC_V=%s  FC_V=%s"%\
                      (request['vc']['external_label'],
                       request['fc']['external_label'])
                request['status'] = (e_errors.USERERROR, msg)

                print_data_access_layer_format(request['infile'],
                                               request['outfile'],
                                               request['file_size'], request)
                quit() #Harsh, but necessary.

            #If no layer 4 is present, then report the error, raise an alarm,
            # but continue with the transfer.
            try:
                p = pnfs.Pnfs(request['wrapper']['pnfsFilename'])
                p.get_xreference()
            except (OSError, IOError), detail:
                request['stats'] = (errno.errorcode[detail.errno], str(detail))
                print_data_access_layer_format(request['infile'],
                                               request['outfile'],
                                               request['file_size'], request)
                quit() #Harsh, but necessary.

            
            if (p.volume == pnfs.UNKNOWN or
                p.location_cookie == pnfs.UNKNOWN or
                p.size == pnfs.UNKNOWN or
                p.origff == pnfs.UNKNOWN  or
                p.origname == pnfs.UNKNOWN or
                #Mapfile no longer used.
                p.pnfsid_file == pnfs.UNKNOWN or
                #Volume map file id no longer used.
                p.bfid == pnfs.UNKNOWN
                #Origdrive not always recored.
                ):
                rest = {'infile':request['infile'],
                        'bfid':request['bfid'],
                        'pnfs_volume':p.volume,
                        'pnfs_location_cookie':p.location_cookie,
                        'pnfs_size':p.size,
                        'pnfs_origff':p.origff,
                        'pnfs_origname':p.origname,
                        'pnfs_id':p.pnfsid_file,
                        'pnfs_bfid':p.bfid,
                        'pnfs_origdrive':p.origdrive,
                        'status':"Missing data in pnfs layer 4."}
                sys.stderr.write(rest['status'] + "  Continuing.\n")
                Trace.alarm(e_errors.ERROR, e_errors.PNFS_ERROR, rest)

            #If there is a layer 4, but the data does not match that in
            # the file and volume clerk databases, then raise alarm and exit.
            elif (request['fc']['external_label'] != p.volume or
                  not same_cookie(request['fc']['location_cookie'],
                                  p.location_cookie) or
                  long(request['fc']['size']) != long(p.size) or
                  volume_family.extract_file_family(
                                request['vc']['volume_family']) != p.origff or
                  request['fc']['pnfs_name0'] != p.origname or
                  #Mapfile no longer used.
                  request['fc']['pnfsid'] != p.pnfsid_file or
                  #Volume map file id no longer used.
                  request['fc']['bfid'] != p.bfid
                  #Origdrive not always recored.
                  ):
                rest = {'infile':request['infile'],
                        'outfile':request['outfile'],
                        'bfid':request['bfid'],
                        'db_volume':request['fc']['external_label'],
                        'pnfs_volume':p.volume,
                        'db_location_cookie':request['fc']['location_cookie'],
                        'pnfs_location_cookie':p.location_cookie,
                        'db_size':long(request['fc']['size']),
                        'pnfs_size':long(p.size),
                        'status':"Probable database conflict with pnfs."}
                Trace.alarm(e_errors.ERROR, e_errors.CONFLICT, rest)
                request['status'] = (e_errors.CONFLICT, rest['status'])
                print_data_access_layer_format(request['infile'],
                                               request['outfile'],
                                               request['file_size'], request)
                quit() #Harsh, but necessary.

            #Test to verify that all the brands are the same.  If not exit.
            # If so, then the system will function.  If this was not true,
            # then a lot of file clerk key errors could occur.
            if request['fc']['bfid'][:4] != bfid_brand[:4]:
                print request['fc']['bfid'], bfid_brand
                msg = "All bfids must have the same brand."
                request['status'] = (e_errors.USERERROR, msg)
                print_data_access_layer_format(request['infile'],
                                               request['outfile'],
                                               request['file_size'], request)
                quit() #Harsh, but necessary.

#######################################################################

def get_clerks_info(vcc, fcc, bfid):

    fc_ticket = fcc.bfid_info(bfid=bfid)

    if fc_ticket['status'][0] != e_errors.OK:
        raise EncpError(None,
                        "Failed to obtain information for bfid %s" % bfid,
                        e_errors.EPROTO, fc_ticket)
    if not fc_ticket.get('external_label', None):
        raise EncpError(None,
                        "Failed to obtain information for bfid %s" % bfid,
                        e_errors.EPROTO, fc_ticket)

    vc_ticket = vcc.inquire_vol(fc_ticket['external_label'])
    
    inhibit = vc_ticket['system_inhibit'][0]
    if inhibit in (e_errors.NOACCESS, e_errors.NOTALLOWED):
        raise EncpError(None,
                        "volume %s is marked %s"%(fc_ticket['external_label'],
                                                  inhibit),
                        inhibit, vc_ticket)

    inhibit = vc_ticket['user_inhibit'][0]
    if inhibit in (e_errors.NOACCESS, e_errors.NOTALLOWED):
        raise EncpError(None,
                        "volume %s is marked %s"%(fc_ticket['external_label'],
                                                  inhibit),
                        inhibit, vc_ticket)

    if fc_ticket["deleted"] == "yes":
        raise EncpError(None,
                        "volume %s is marked %s"%(fc_ticket['external_label'],
                                                  e_errors.DELETED),
                        e_errors.DELETED, vc_ticket)

    return vc_ticket, fc_ticket

############################################################################

def verify_file_size(ticket):
    #Don't worry about checking when outfile is /dev/null.
    if ticket['outfile'] == '/dev/null':
        try:
            p = pnfs.Pnfs(ticket['infile'])
            p.get_file_size()
            return p.file_size
        except (OSError, IOError), detail:
            return 0

    filename = ticket['outfile']
    file_size = 0 #quick hack
    
    try:
        #Get the stat info to 
        statinfo = os.stat(filename)
	
        file_size = statinfo[stat.ST_SIZE]
	
        #Until pnfs supports NFS version 3 (for large file support) make sure
	# we are using the correct file_size for the pnfs side.
        try:
            p = pnfs.Pnfs(ticket['infile'])
            p.get_file_size()
            real_size = p.file_size
        except (OSError, IOError), detail:
            real_size = 0

	if file_size != real_size: #ticket['file_size']:
            msg = "Expected file size (%s) not equal to actuall file size " \
                  "(%s) for file %s." % \
                  (ticket['file_size'], file_size, filename)

            ticket['file_size'] = file_size
            ticket['status'] = (e_errors.EPROTO, msg)

    except OSError, msg:
        Trace.log(e_errors.INFO, "Retrieving %s info. failed: %s" % \
                  (filename, msg))
        ticket['status'] = (e_errors.UNKNOWN, "Unable to verify file size.")

    return file_size #return used in read.

#######################################################################
#Functions for reads.
#######################################################################

def create_read_requests(callback_addr, tinfo, e):

    nfiles = 0
    requests_per_vol = {}

    vcc = fcc = None #Initialize these, so that they can be set only once.

    ninput, file_size, inputlist, outputlist = file_check(e)
    
    #Create the list of file requests that will be sent to the library manager.
    for i in range(0, len(inputlist)):

        try:
            p = pnfs.Pnfs(inputlist[i])
            bfid = p.get_bit_file_id()
            pinfo = get_pinfo(p)
        except (OSError, IOError), detail:
            print_data_access_layer_format(
                inputlist[i], outputlist[i], file_size[i],
                {'status':(errno.errorcode[detail.errno], str(detail))})
            quit()
        except (IndexError,), detail:
            print_data_access_layer_format(
                inputlist[i], outputlist[i], file_size[i],
                {'status':(e_errors.OSERROR, "Unable to obtain bfid.")})
            quit()
        

        #only do this the first time.
        if not vcc or not fcc:
            vcc, fcc = get_clerks(bfid)

        try:
            vc_reply, fc_reply = get_clerks_info(vcc, fcc, bfid)
            fc_reply['address'] = fcc.server_address
            vc_reply['address'] = vcc.server_address
        except EncpError, detail:
            print_data_access_layer_format(
                inputlist[i], outputlist[i], file_size[i],
                {'status':(detail.type, detail.strerror)})
            quit()

        Trace.message(TICKET_LEVEL, "FILE CLERK:")
        Trace.message(TICKET_LEVEL, pprint.pformat(fc_reply))
        Trace.message(TICKET_LEVEL, "VOLUME CLERK:")
        Trace.message(TICKET_LEVEL, pprint.pformat(vc_reply))

        try:
            # comment this out not to confuse the users
            #if fc_reply.has_key("fc") or fc_reply.has_key("vc"):
            #    sys.stderr.write("Old file clerk format detected.\n")
            del fc_reply['fc'] #Speed up debugging by removing these.
            del fc_reply['vc']
        except:
            pass

        # make the part of the ticket that encp knows about.
        # (there's more later)
        encp_el = {}
        encp_el['basepri'] = e.priority
        encp_el['adminpri'] = e.admpri
        encp_el['delpri'] = e.delpri
        encp_el['agetime'] = e.age_time
        encp_el['delayed_dismount'] = e.delayed_dismount

        #check for this environmental variable.
        try:
            encp_daq = os.environ["ENCP_DAQ"]
        except KeyError:
            encp_daq = None

        # create the time subticket
        times = {}
        times['t0'] = tinfo['encp_start_time']

        label = fc_reply['external_label']
        vf = vc_reply['volume_family']
        #vc_reply['address'] = volume_clerk_address
        vc_reply['storage_group']=volume_family.extract_storage_group(vf)
        vc_reply['file_family'] = volume_family.extract_file_family(vf)
        vc_reply['wrapper'] = volume_family.extract_wrapper(vf)
        #fc_reply['address'] = file_clerk_address

        uinfo = {}
        uinfo['uid'] = os.getuid()
        uinfo['gid'] = os.getgid()
        try:
            uinfo['gname'] = grp.getgrgid(uinfo['gid'])[0]
        except (ValueError, AttributeError, TypeError, IndexError):
            uinfo['gname'] = 'unknown'
            try:
                uinfo['uname'] = pwd.getpwuid(uinfo['uid'])[0]
            except (ValueError, AttributeError, TypeError, IndexError):
                uinfo['uname'] = 'unknown'
        uinfo['machine'] = os.uname()
        #uinfo['fullname'] = "" # will be filled in later for each transfer

        wrapper = {}

        # store the pnfs information info into the wrapper
        for key in pinfo.keys():
            wrapper[key] = pinfo[key]

        # the user key takes precedence over the pnfs key
        for key in uinfo.keys():
            wrapper[key] = uinfo[key]

        wrapper['fullname'] = outputlist[i]
        wrapper['sanity_size'] = 65536
        wrapper['size_bytes'] = file_size[i]
        
        request = {}
        request['bfid'] = bfid
        request['callback_addr'] = callback_addr
        request['client_crc'] = e.chk_crc
        request['encp'] = encp_el
        request['encp_daq'] = encp_daq
        request['fc'] = fc_reply
        request['file_size'] = file_size[i]
        request['infile'] = inputlist[i]
        request['outfile'] = outputlist[i]
        request['retry'] = 0
        request['times'] = times
        request['unique_id'] = generate_unique_id()
        request['vc'] = vc_reply
        request['version'] = encp_client_version()
        request['volume'] = label
        request['work'] = 'read_from_hsm'
        request['wrapper'] = wrapper

        requests_per_vol[label] = requests_per_vol.get(label,[]) + [request]
        nfiles = nfiles+1

    return requests_per_vol

#######################################################################

# submit read_from_hsm requests
def submit_read_requests(requests, tinfo, encp_intf):

    submitted = 0
    requests_to_submit = requests[:]

    # submit requests
    while requests_to_submit:
        for req in requests_to_submit:

            Trace.message(TRANSFER_LEVEL, 
                  "Submitting %s read request.  elapsed=%s" % \
                  (req['outfile'], time.time() - tinfo['encp_start_time']))

            Trace.trace(18, "submit_read_requests queueing:%s"%(req,))

            ticket = submit_one_request(req)

            Trace.message(TICKET_LEVEL, "LIBRARY MANAGER")
            Trace.message(TICKET_LEVEL, pprint.pformat(ticket))
                         
            result_dict = handle_retries(requests_to_submit, req, ticket,
                                         None, encp_intf)
            if result_dict['status'][0] == e_errors.RETRY or \
               not e_errors.is_retriable(result_dict['status'][0]):
                continue
            
            del requests_to_submit[requests_to_submit.index(req)]
            submitted = submitted+1

    return submitted

#############################################################################

# read hsm files in the loop after read requests have been submitted
#Args:
# listen_socket - The socket to listen on returned from callback.get_callback()
# submittted - The number of elements of the list requests that were
#  successfully transfered.
# requests - A list of dictionaries.  Each dictionary represents on transfer.
# tinfo - Dictionary of timing info.
# e - class instance of the interface.
#Rerturns:
# (requests, bytes) - requests returned only contains those requests that
#   did not succed.  bytes is the total running sum of bytes transfered
#   for this encp.

def read_hsm_files(listen_socket, submitted, request_list, tinfo, e):

    for rq in request_list: 
        Trace.trace(17,"read_hsm_files: %s"%(rq['infile'],))

    files_left = submitted
    bytes = 0L
    encp_crc = 0
    failed_requests = []
    succeded_requests = []

    #for waiting in range(submitted):
    while files_left:
        Trace.message(TO_GO_LEVEL, "FILES LEFT: %s" % files_left)
        Trace.message(TRANSFER_LEVEL,
                      "Waiting for mover to call back.  elapsed=%s" %
                      (time.time() - tinfo['encp_start_time'],))
            
        # listen for a mover - see if id corresponds to one of the tickets
        #   we submitted for the volume
        control_socket, data_path_socket, request_ticket = mover_handshake(
            listen_socket,
            request_list,
            e.mover_timeout)

        done_ticket = request_ticket #Make sure this exists by this point.
        result_dict = handle_retries(request_list, request_ticket,
                                     request_ticket, None, e)

        if result_dict['status'][0]== e_errors.RETRY or \
           result_dict['status'][0]== e_errors.RESUBMITTING:
            continue
        elif result_dict['status'][0]== e_errors.TOO_MANY_RESUBMITS:
            for n in range(files_left):
                failed_requests.append(request_ticket)
            files_left = 0
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            files_left = result_dict['queue_size']
            failed_requests.append(request_ticket)
            continue

        Trace.message(TRANSFER_LEVEL, "Mover called back.  elapsed=%s" %
                      (time.time() - tinfo['encp_start_time'],))
        Trace.message(TICKET_LEVEL, "REQUEST:")
        Trace.message(TICKET_LEVEL, pprint.pformat(request_ticket))

        #Open the output file.
        done_ticket = open_local_file(request_ticket['outfile'], "read")

        result_dict = handle_retries(request_list, request_ticket,
                                     done_ticket, None, e)
        if not e_errors.is_retriable(result_dict['status'][0]):
            files_left = result_dict['queue_size']
            failed_requests.append(request_ticket)

            close_descriptors(control_socket, data_path_socket)
            continue
        else:
            out_fd = done_ticket['fd']

        Trace.message(TRANSFER_LEVEL, "Output file %s opened.  elapsed=%s" %
                  (request_ticket['outfile'],
                   time.time() - tinfo['encp_start_time']))

        #Stall starting the count until the first byte is ready for reading.
        read_fd, write_fd, exc_fd = select.select([data_path_socket], [],
                                                  [data_path_socket], 15 * 60)

        Trace.message(TRANSFER_LEVEL, "Starting transfer.  elapsed=%s" %
                  (time.time() - tinfo['encp_start_time'],))
        
        lap_start = time.time() #----------------------------------------Start

        done_ticket, encp_crc = transfer_file(data_path_socket.fileno(),out_fd,
                                              control_socket, request_ticket,
                                              tinfo, e)

        lap_end = time.time()  #-----------------------------------------End
        tstring = "%s_elapsed_time" % request_ticket['unique_id']
        tinfo[tstring] = lap_end - lap_start

        Trace.message(TRANSFER_LEVEL, "Verifying %s transfer.  elapsed=%s" %
                      (request_ticket['infile'],
                       time.time() - tinfo['encp_start_time']))

        close_descriptors(control_socket, data_path_socket, out_fd)

        #Verify that everything went ok with the transfer.
        result_dict = handle_retries(request_list, request_ticket,
                                     done_ticket, None, e)
        
        if result_dict['status'][0] == e_errors.RETRY:
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            files_left = result_dict['queue_size']
            failed_requests.append(request_ticket)
            continue

        #For simplicity combine everything together.
        #done_ticket = combine_dict(result_dict, done_ticket)
        
        Trace.message(TRANSFER_LEVEL, "File %s transfered.  elapsed=%s" %
                      (request_ticket['infile'],
                       time.time() - tinfo['encp_start_time']))
        Trace.message(TICKET_LEVEL, "FINAL DIALOG")
        Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

        #These functions write errors/warnings to the log file and put an
        # error status in the ticket.
        bytes = bytes + verify_file_size(done_ticket) #Verify size is the same.
        check_crc(done_ticket, e.chk_crc, encp_crc) #Check the CRC.

        #Verfy that the file transfered in tacted.
        result_dict = handle_retries(request_list, request_ticket,
                                     done_ticket, None, e)
        if result_dict['status'][0] == e_errors.RETRY:
            continue
        elif not e_errors.is_retriable(result_dict['status'][0]):
            files_left = result_dict['queue_size']
            failed_requests.append(request_ticket)
            continue

        #This function writes errors/warnings to the log file and puts an
        # error status in the ticket.
        set_outfile_permissions(done_ticket) #Writes errors to log file.
        ###What kind of check should be done here?
        #This error should result in the file being left where it is, but it
        # is still considered a failed transfer (aka. exit code = 1 and
        # data access layer is still printed).
        if done_ticket.get('status', (e_errors.OK,None)) != (e_errors.OK,None):
            print_data_access_layer_format(done_ticket['infile'],
                                           done_ticket['outfile'],
                                           done_ticket['file_size'],
                                           done_ticket)

        #Remove the new file from the list of those to be deleted should
        # encp stop suddenly.  (ie. crash or control-C).
        delete_at_exit.unregister(done_ticket['outfile']) #localname

        # remove file requests if transfer completed succesfuly.
        #del(request_ticket)
        del request_list[request_list.index(request_ticket)]
        if files_left > 0:
            files_left = files_left - 1

        tstring = "%s_elapsed_finished" % done_ticket['unique_id']
        tinfo[tstring] = time.time() - lap_start #-------------------------End

        Trace.message(TRANSFER_LEVEL,
                      "File status after verification: %s   elapsed=%s" %
                      (done_ticket["status"],
                       time.time() - tinfo['encp_start_time']))
        
        # calculate some kind of rate - time from beginning to wait for
        # mover to respond until now. This doesn't include the overheads
        # before this, so it isn't a correct rate. I'm assuming that the
        # overheads I've neglected are small so the quoted rate is close
        # to the right one.  In any event, I calculate an overall rate at
        # the end of all transfers
        calculate_rate(done_ticket, tinfo)

        #With the transfer a success, we can now add the ticket to the list
        # of succeses.
        succeded_requests.append(done_ticket)

    Trace.message(TICKET_LEVEL, "DONE TICKET")
    Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

    #Pull out the failed transfers that occured while trying to open the
    # control socket.
    unknown_failed_transfers = []
    for transfer in failed_requests:
        if len(transfer) < 3:
            unknown_failed_transfers.append(transfer)

    #Extract the unique ids for the two lists.
    succeded_ids = []
    failed_ids = []
    for req in succeded_requests:
        try:
            succeded_ids.append(req['unique_id'])
        except KeyError:
            sys.stderr.write("Error obtaining unique id list of successes.\n")
            sys.stderr.write(pprint.pformat(req) + "\n")
    for req in failed_requests:
        try:
            failed_ids.append(req['unique_id'])
        except KeyError:
            sys.stderr.write("Error obtaining unique id list of failures.\n")
            sys.stderr.write(pprint.pformat(req) + "\n")

    #For each transfer that failed without even succeding to open a control
    # socket, print out their data access layer.
    for transfer in request_list:
        if transfer['unique_id'] not in succeded_ids and \
           transfer['unique_id'] not in failed_ids:
            try:
                transfer = combine_dict(unknown_failed_transfers[0], transfer)
                del unknown_failed_transfers[0] #shorten this list.

                print_data_access_layer_format(transfer['infile'],
                                               transfer['outfile'],
                                               transfer['file_size'],
                                               transfer)
            except IndexError, msg:
                #msg = "Unable to print data access layer.\n"
                sys.stderr.write(str(msg)+"\n")

    return failed_requests, bytes, done_ticket

#######################################################################

def read_from_hsm(e, tinfo):

    Trace.trace(16,"read_from_hsm input_files=%s  output=%s  verbose=%s  "
                "chk_crc=%s t0=%s" % (e.input, e.output, e.verbose,
                                      e.chk_crc, tinfo['encp_start_time']))
    
    # initialize
    bytes = 0L #Sum of bytes all transfered (when transfering multiple files).
    exit_status = 0 #Used to determine the final message text.
    number_of_files = 0 #Total number of files where a transfer was attempted.

    # get a port to talk on and listen for connections
    callback_addr, listen_socket = get_callback_addr(e)

    #Create all of the request dictionaries.
    requests_per_vol = create_read_requests(callback_addr, tinfo, e)

    #If this is the case, don't worry about anything.
    if (len(requests_per_vol) == 0):
        quit()

    #This will halt the program if everything isn't consistant.
    verify_read_request_consistancy(requests_per_vol)
    
    #Set the max attempts that can be made on a transfer.
    check_lib = requests_per_vol.keys()    
    max_attempts(requests_per_vol[check_lib[0]][0]['vc']['library'], e)

    # loop over all volumes that are needed and submit all requests for
    # that volume. Read files from each volume before submitting requests
    # for different volumes.
    
    vols = requests_per_vol.keys()
    vols.sort()
    for vol in vols:
        request_list = requests_per_vol[vol]
        number_of_files = number_of_files + len(request_list)

        #The return value is the number of files successfully submitted.
        # This value may be different from len(request_list).  The value
        # of request_list is not changed by this function.
        submitted = submit_read_requests(request_list, tinfo, e)

        Trace.message(TO_GO_LEVEL, "SUBMITED: %s" % submitted)
        Trace.message(TICKET_LEVEL, pprint.pformat(request_list))

        Trace.message(TRANSFER_LEVEL, "Files queued.   elapsed=%s" %
                      (time.time() - tinfo['encp_start_time']))

        if submitted != 0:
            #Since request_list contains all of the entires, submitted must
            # also be passed so read_hsm_files knows how many elements of
            # request_list are valid.
            requests_failed, brcvd, data_access_layer_ticket = read_hsm_files(
                listen_socket, submitted, request_list, tinfo, e)

            Trace.message(TRANSFER_LEVEL,
                          "Files read for volume %s   elapsed=%s" %
                          (vol, time.time() - tinfo['encp_start_time']))

            if len(requests_failed) > 0 or \
               data_access_layer_ticket['status'][0] != e_errors.OK:
                exit_status = 1 #Error, when quit() called, this is passed in.
                Trace.message(ERROR_LEVEL,
                              "TRANSFERS FAILED: %s" % len(requests_failed))
                Trace.message(TICKET_LEVEL, pprint.pformat(requests_failed))

            #Sum up the total amount of bytes transfered.
            bytes = bytes + brcvd

        else:
            #If all submits fail (i.e using an old encp), this avoids crashing.
            data_access_layer_ticket = {}

    Trace.message(TRANSFER_LEVEL, "Files read for all volumes.   elapsed=%s" %
                  (time.time() - tinfo['encp_start_time'],))

    # we are done transferring - close out the listen socket
    close_descriptors(listen_socket)

    #Finishing up with a few of these things.
    calc_ticket = calculate_final_statistics(bytes, number_of_files,
                                             exit_status, tinfo)

    done_ticket = combine_dict(calc_ticket, data_access_layer_ticket)

    Trace.message(TICKET_LEVEL, "DONE TICKET")
    Trace.message(TICKET_LEVEL, pprint.pformat(done_ticket))

    return done_ticket

##############################################################################
##############################################################################

class encp(interface.Interface):

    deprecated_options = ['--crc']
    
    def __init__(self):
        global pnfs_is_automounted
        self.chk_crc = 1           # we will check the crc unless told not to
        self.priority = 1          # lowest priority
        self.delpri = 0            # priority doesn't change
        self.admpri = -1           # quick fix to check HiPri functionality
        self.age_time = 0          # priority doesn't age
        self.data_access_layer = 0 # no special listings
        self.verbose = 0
        self.bufsize = 65536*4     #XXX CGW Investigate this
        self.delayed_dismount = None
        self.max_retry = None      # number of times to try again
        self.max_resubmit = None   # number of times to try again
        self.mover_timeout = 15*60 # seconds to wait for mover to call back,
                                   # before resubmitting req. to lib. mgr.
                                   # 15 minutes
        self.output_file_family = '' # initial set for use with --ephemeral or
                                     # or --file-family
                                     
        self.bytes = None

        self.dcache = 0 #Special options for operation with a disk cache layer.
        self.put_cache = self.get_cache = 0
        self.pnfs_mount_point = ""

        self.storage_info = None # Ditto
        self.test_mode = 0
        self.pnfs_is_automounted = 0

        interface.Interface.__init__(self)

        # parse the options
        self.parse_options()
        pnfs_is_automounted = self.pnfs_is_automounted

    ##########################################################################
    # define the command line options that are valid
    def options(self):
        return self.config_options()+[
            "verbose=","no-crc","priority=","delpri=","age-time=",
            "delayed-dismount=", "file-family=", "ephemeral",
            "get-cache", "put-cache", "storage-info=", "pnfs-mount-point=",
            "data-access-layer", "max-retry=", "max-resubmit=",
            "pnfs-is-automounted"] + \
            self.help_options()

    
    ##########################################################################
    #  define our specific help
    def help_line(self):
        prefix = self.help_prefix()
        return "%s%s\n or\n %s%s%s" % (
            prefix, self.parameters1(),
            prefix, self.parameters2(),
            self.format_options(self.options(), "\n\t\t"))

    ##########################################################################
    #  define our specific parameters
    def parameters1(self):
        return "inputfilename outputfilename"

    def parameters2(self):
        return "inputfilename1 ... inputfilenameN outputdirectory"

    def parameters(self):
        return "[["+self.parameters1()+"] or ["+self.parameters2()+"]]"

    ##########################################################################
    # parse the options from the command line
    def parse_options(self):
        # normal parsing of options
        interface.Interface.parse_options(self)

        # bomb out if we don't have an input and an output
        self.arglen = len(self.args)
        if self.arglen < 2 :
            print_error(e_errors.USERERROR, "not enough arguments specified")
            self.print_help()
            sys.exit(1)

        if self.get_cache:
            pnfs_id = sys.argv[-2]
            local_file = sys.argv[-1]
            #remote_file=os.popen("enstore pnfs --path " + pnfs_id).readlines()
            #p = pnfs.Pnfs(pnfs_id=pnfs_id, mount_point=self.pnfs_mount_point)
            try:
                p = pnfs.Pnfs(pnfs_id, mount_point=self.pnfs_mount_point)
                p.get_path()
                remote_file = p.path
            except (OSError, IOError), detail:
                print_data_access_layer_format(
                    local_file, pnfs_id, 0,
                    {'status':(errno.errorcode[detail.errno],str(detail))})
                quit()
                
            #self.args[0:2] = [remote_file[0][:-1], local_file]
            self.args[0:2] = [remote_file, local_file]
        if self.put_cache:
            pnfs_id = sys.argv[-2]
            local_file = sys.argv[-1]
            #remote_file=os.popen("enstore pnfs --path " + pnfs_id).readlines()
            #p = pnfs.Pnfs(pnfs_id=pnfs_id, mount_point=self.pnfs_mount_point)
            try:
                p = pnfs.Pnfs(pnfs_id, mount_point=self.pnfs_mount_point)
                p.get_path()
                remote_file = p.path
            except (OSError, IOError), detail:
                print_data_access_layer_format(
                    local_file, pnfs_id, 0,
                    {'status':(errno.errorcode[detail.errno],str(detail))})
                quit()
            #self.args[0:2] = [local_file, remote_file[0][:-1]]
            self.args[0:2] = [local_file, remote_file]

        # get fullpaths to the files
        p = []
        for i in range(0,self.arglen):
            (machine, fullname, dir, basename) = fullpath(self.args[i])
            self.args[i] = os.path.join(dir,basename)
            p.append(string.find(dir,"/pnfs"))
        # all files on the hsm system have /pnfs/ as 1st part of their name
        # scan input files for /pnfs - all have to be the same
        p1 = p[0]
        p2 = p[self.arglen-1]
        self.input = [self.args[0]]
        self.output = [self.args[self.arglen-1]]
        for i in range(1,len(self.args)-1):
            if p[i]!=p1:
                msg = "Not all input_files are %s files"
                if p1:
                    print_error(e_errors.USERERROR, msg % "/pnfs/...")
                else:
                    print_error(e_errors.USERERROR, msg % "unix")
                quit()
            else:
                self.input.append(self.args[i])

        if p1 == 0:
            self.intype="hsmfile"
        else:
            self.intype="unixfile"
        if p2 == 0:
            self.outtype="hsmfile"
        else:
            self.outtype="unixfile"

##############################################################################

def main():
    encp_start_time = time.time()
    tinfo = {'encp_start_time':encp_start_time}
    
    Trace.init("ENCP")
    Trace.trace( 16, 'encp called at %s: %s'%(encp_start_time, sys.argv) )

    for opt in encp.deprecated_options:
        if opt in sys.argv:
            print "WARNING: option %s is deprecated, ignoring" % (opt,)
            sys.argv.remove(opt)
    
    # use class to get standard way of parsing options
    e = encp()
    if e.test_mode:
        print "WARNING: running in test mode"

    for x in xrange(6, e.verbose+1):
        Trace.do_print(x)
    for x in xrange(1, e.verbose+1):
        Trace.do_message(x)

    #Print out the information from the command line.
    Trace.message(CONFIG_LEVEL, format_class_for_print(e, "e"))
    Trace.message(CONFIG_LEVEL, os.getuid())
    Trace.message(CONFIG_LEVEL, os.getgid())
    Trace.message(CONFIG_LEVEL, os.geteuid())
    Trace.message(CONFIG_LEVEL, os.getegid())

    #Some globals are expected to exists for normal operation (i.e. a logger
    # client).  Create them.
    client_klsdhsklfh = clients(e.config_host, e.config_port)
    #Trace.message(CONFIG_LEVEL, format_class_for_print(client['csc'], 'csc'))
    #Trace.message(CONFIG_LEVEL, format_class_for_print(client['logc'], 'logc'))

    # convenient, but maybe not correct place, to hack in log message
    # that shows how encp was called
    Trace.log(e_errors.INFO,
                'encp version %s, command line: "%s"' %
                (encp_client_version(), string.join(sys.argv)))

    if e.data_access_layer:
        global data_access_layer_requested
        data_access_layer_requested = e.data_access_layer
        #data_access_layer_requested.set()

    #Special handling for use with dcache - not yet enabled
    if e.get_cache:
        #pnfs_id = sys.argv[-2]
        #local_file = sys.argv[-1]
        #print "pnfsid", pnfs_id
        #print "local file", local_file
        done_ticket = read_from_hsm(e, tinfo)

    #Special handling for use with dcache - not yet enabled
    elif e.put_cache:
        #pnfs_id = sys.argv[-2]
        #local_file = sys.argv[-1]
        done_ticket = write_to_hsm(e, tinfo)
        
    ## have we been called "encp unixfile hsmfile" ?
    elif e.intype=="unixfile" and e.outtype=="hsmfile" :
        done_ticket = write_to_hsm(e, tinfo)
        

    ## have we been called "encp hsmfile unixfile" ?
    elif e.intype=="hsmfile" and e.outtype=="unixfile" :
        done_ticket = read_from_hsm(e, tinfo)


    ## have we been called "encp unixfile unixfile" ?
    elif e.intype=="unixfile" and e.outtype=="unixfile" :
        emsg="encp copies to/from tape. It is not involved in copying %s to %s" % (e.intype, e.outtype)
        print_error('USERERROR', emsg)
        if e.data_access_layer:
            print_data_access_layer_format(e.input, e.output, 0, {'status':("USERERROR",emsg)})
        quit()

    ## have we been called "encp hsmfile hsmfile?
    elif e.intype=="hsmfile" and e.outtype=="hsmfile" :
        emsg=  "encp tape to tape is not implemented. Copy file to local disk and them back to tape"
        print_error('USERERROR', emsg)
        if e.data_access_layer:
            print_data_access_layer_format(e.input, e.output, 0, {'status':("USERERROR",emsg)})
        quit()

    else:
        emsg = "ERROR: Can not process arguments %s"%(e.args,)
        Trace.trace(16,emsg)
        print_data_access_layer_format("","",0,{'status':("USERERROR",emsg)})
        quit()

    exit_status = done_ticket.get('exit_status', 1)    
    try:
        if e.data_access_layer and not exit_status:
            print_data_access_layer_format(e.input, e.output,
                                           done_ticket.get('file_size', 0),
                                           done_ticket)
        else:
            status = done_ticket.get('status', (e_errors.UNKNOWN,
                                                e_errors.UNKNOWN)[1])
            Trace.log(e_errors.INFO, string.replace(status[1], "\n\t", "  "))
            Trace.message(DONE_LEVEL, str(status[1]))

    except ValueError:
        exc, msg, tb = sys.exc_info()
        sys.stderr.write("Error (main): %s: %s\n" % (str(exc), str(msg)))
        sys.stderr.write("Exit status: %s\n", exit_status)

    Trace.trace(20,"encp finished at %s"%(time.time(),))
    #Quit safely by Removing any zero length file for transfers that failed.
    quit(exit_status)

if __name__ == '__main__':

    for sig in range(1, signal.NSIG):
        if sig not in (signal.SIGTSTP, signal.SIGCONT,
                       signal.SIGCHLD, signal.SIGWINCH):
            try:
                signal.signal(sig, signal_handler)
            except:
                sys.stderr.write("Setting signal %s to %s failed.\n" %
                                 (sig, signal_handler))
    
    try:
        main()
        quit(0)
    except SystemExit, msg:
        quit(1)
    #except:
        #exc, msg, tb = sys.exc_info()
        #sys.stderr.write("%s\n" % (tb,))
        #sys.stderr.write("%s %s\n" % (exc, msg))
        #quit(1)
        
        
