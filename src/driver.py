##############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import sys
import errno
import posix
import string
import time
import os				# temporary - .system to execute mt commands

# enstore imports
try:
    import ETape
except  ImportError:
    print "ETape unavailable!"


class GenericDriver:

    def __init__(self, device, eod_cookie,remaining_bytes):
        self.device = device
        self.remaining_bytes = remaining_bytes
        self.wr_err = 0			# counts
        self.rd_err = 0			# counts
        self.wr_access = 0		# counts
        self.rd_access = 0		# counts
	self.blocksize = 0		# to be initialized later
	self.position = 0		# to be initialized later
	self.bod = 0			# to be initialized later
	self.eod = 0			# to be initialized later
	self.ETdesc = 0			# will be pointer to ETape ETdesc
	self.df = 0

	# When a volume is ceated, the system sets EOD cookie to "none"
	self.set_eod( eod_cookie )
	pass

    def load( self, eod_cookie ):
	# this
	return
    def unload(self): return

    # blocksize is volume dependent
    def set_blocksize(self,blocksize):
        self.blocksize = blocksize

    def get_blocksize(self) :
        return self.blocksize

    def get_eod_remaining_bytes(self):
        return self.remaining_bytes-5000

    def get_eod(self):
        return repr(self.eod)

    def set_eod(self, eod_cookie) :
        # When a volume is ceated, the system sets EOD cookie to "none"
        if eod_cookie == "none" :
            self.eod = 0
        else:
	    # use eval as eod may be a string (could use atoi
	    # but eod could be larger than 2 or 4 Gig
            self.eod = eval(eod_cookie)

    def get_errors(self) :
         # return error count and # of files accesses
        return (self.wr_err, self.rd_err, self.wr_access, self.rd_access)


class  FTTDriver(GenericDriver) :
    """
     A Fermi Tape Tools driver
    """
#    Error handling - the ET routines return a NULL pointer to an  object
#    and throw an ETape.error exception which is passed to our caller.
#
    def __init__(self, device, eod_cookie, remaining_bytes):
        GenericDriver.__init__(self, device, eod_cookie, remaining_bytes)
        self.blocksize = 65536
        #ETape.ET_Rewind("", self.device)
        self.set_position()

    def load( self, eod_cookie ):
	os.system("mt -t " + self.device + " rewind")
	return

    def unload(self):
	os.system("mt -t " + self.device + " offline")
	return

    # This may be a mixin where the position is determined from the drive
    def set_position(self):
        self.position = 0;

    def open_file_read(self, file_location_cookie) :
        loc, size  = eval(file_location_cookie)
        move = loc - self.position
        if move < 0 :
           move = move-1
        self.ETdesc = ETape.ET_OpenRead(self.device, move, loc, self.blocksize)
        self.position = loc

    def close_file_read(self) :
        self.position = self.position + 1
        stats = ETape.ET_CloseRead(self.ETdesc)

        if stats[1] != "Invalid":
          self.rd_access = string.atoi(stats[1])
        if stats[2] != "Invalid":
          self.rd_err = string.atoi(stats[2])

    def read_block(self):
        return ETape.ET_ReadBlock (self.ETdesc)

    def open_file_write(self):
        self.bod = self.eod
        self.ETdesc = ETape.ET_OpenWrite(self.device, self.eod-self.position, self.blocksize)
        self.position = self.eod

    def close_file_write(self):
        stats = ETape.ET_CloseWrite(self.ETdesc)
        self.eod = self.eod + 1
        self.position = self.eod
        if stats[0] != "Invalid" :
           self.remaining_bytes = 1024L*(string.atoi(stats[0])-1024)
        else :
          self.remaining_bytes = self.remaining_bytes - stats[3] - 1048576L
        self.wr_access = string.atoi(stats[1])
        if stats[2] != "Invalid" :
          self.wr_err = string.atoi(stats[2])
        else :
          self.wr_err = 0;
        return `(self.bod, stats[3])`

#      This does not realy write a "block" but puts data into a buffer
#      which is writtenb when the buffer is a full tape block.
    def write_block(self, data):
       ETape.ET_WriteBlock(self.ETdesc, data)

    # ftt updates remaining_byte count, so this routine not needed for FTT driver
    def xferred_bytes(self,size) :
        pass

class  RawDiskDriver(GenericDriver) :
    """
    A driver for testing with disk files
    """	
	
    firstbyte = 0 
	
    def __init__(self, device, eod_cookie, remaining_bytes):
        GenericDriver.__init__(self, device, eod_cookie, remaining_bytes)
        self.blocksize = 4096
        #self.df = open(self.device, "a+")	# need to open so we can "tell"
        #self.set_eod( repr(self.df.tell()) )
	
    def __del__( self ):
	#self.df.close()
	pass
	
    def load( self, eod_cookie ):
	#self.df = open(self.device, "a+")
	self.set_eod( eod_cookie )
        return
	
    def unload( self ):
	#self.df.close()
	return
	
    # read file -- use the "cookie" to not walk off the end, since we have
    # no "file marks" on a disk
    def open_file_read(self, file_location_cookie) :
        #print "   open_file_read"
        self.df = open(self.device, "a+")
        self.rd_access = self.rd_access+1
        self.firstbyte, self.pastbyte = eval(file_location_cookie)
        self.df.seek(self.firstbyte, 0)
        self.left_to_read = self.pastbyte - self.firstbyte

    def close_file_read(self) :
        #print "   close_file_read"
	self.df.close()
        pass

    def read_block(self):
        # no file marks on a disk, so use the information
        # in the cookie to bound the file.
        n_to_read = min(self.blocksize, self.left_to_read)
        if n_to_read == 0 : return ""
        buf = self.df.read(n_to_read)
        self.left_to_read = self.left_to_read - len(buf)
        if self.left_to_read < 0:
            raise "assert error"
        return buf

    # we cannot auto sense a floppy, so we must trust the user
    def open_file_write(self):
        #print "   open_file_write"
        self.df = open(self.device, "a+")
        self.wr_access = self.wr_access+1
        self.df.seek(self.eod, 0)
        self.first_write_block = 1

    def close_file_write(self):
        #print "   close_file_write"
        first_byte = self.eod
        last_byte = self.df.tell()

        # we don't fill each byte - the next starting place is at the
        # beginning of the next block
        if last_byte%self.blocksize != 0:
            self.eod = last_byte+(self.blocksize-(last_byte%self.blocksize))

            # If the data is being written to a file on a hard drive, the
            # file has to be blanked filled to the next blocksize.
            # Otherwise, the next open_write doesn't seek to end
            empty = self.eod-last_byte    # number of empty bytes to next block
            self.first_write_block = 0    # just filling it it
            self.write_block("J"*empty)   # fill it out
        else:
            self.eod = last_byte

        self.df.close()			# belongs in unload???
        return `(first_byte, last_byte)`  # cookie describing the file

    # write a block of data to already open file: user has to handle exceptions
    def write_block(self, data):
        if len(data) > self.remaining_bytes :
            format="NoSpace Len "+repr(len(data))+ \
                     "Remain "+repr(self.remaining_bytes)
            raise errno.errorcode[errno.ENOSPC], format
        self.remaining_bytes = (self.remaining_bytes-len(data))
        self.df.write(data)
        self.df.flush()
#        if self.first_write_block :
#            self.first_write_block = 0
#            self.eod = self.df.tell() - len(data)

    # xferred_bytes not counted - so subtract them from remaining byte count
    def xferred_bytes(self,size) :
        self.remaining_bytes = self.remaining_bytes - size

class  DelayDriver(RawDiskDriver) :
    """
    A specialized RawDisk Driver for testing with disk files, but with 
    crude delays modeled on no particular tape drive.

    """
    def load( self, eod_cookie ):
        time.sleep( 10 )                   # load time 10 seconds
	RawDiskDriver.load( self, eod_cookie )

    def unload(self):
	time.sleep(self.firstbyte/20E6)   # rewind time @ 20MB/sec
	time.sleep(10)			  # unload time -- 10 seconds
        RawDiskDriver.unload(self)

    def open_file_read(self, file_location_cookie) :
        whereb4 = self.firstbyte
        RawDiskDriver.open_file_read(self, file_location_cookie)
	bytesskipped = abs(whereb4 - self.firstbyte);
	time.sleep(bytesskipped/20E6)    # skip at 20MB/sec

    def open_file_write(self):
        #print "   open_file_write"
	bytesskipped = abs(self.eod - self.firstbyte);
	time.sleep(bytesskipped/20E6)    # skip at 20MB/sec
	RawDiskDriver.open_file_write(self)


if __name__ == "__main__" :
    import getopt
    import string
    # Import SOCKS module if it exists, else standard socket module socket
    # This is a python module that works just like the socket module, but uses
    # the SOCKS protocol to make connections through a firewall machine.
    # See http://www.w3.org/People/Connolly/support/socksForPython.html or
    # goto www.python.org and search for "import SOCKS"
    try:
        import SOCKS; socket = SOCKS
    except ImportError:
        import socket

    status = 0

    # defaults
    size = 760000
    device = "./rdd-testfile.fake"
    eod_cookie = "0"
    list = 0

    # see what the user has specified. bomb out if wrong options specified
    options = ["size=","device=","eod_cookie=","list","verbose","help"]
    optlist,args=getopt.getopt(sys.argv[1:],'',options)
    for (opt,value) in optlist :
        if opt == "--size" :
            size = string.atoi(value)
        elif opt == "--device" :
            device = value
        elif opt == "--eod_cookie":
            eod_cookie = value
        elif opt == "--list" or opt == "--verbose":
            list = 1
        elif opt == "--help" :
            print "python ",sys.argv[0], options
            print "   do not forget the '--' in front of each option"
            sys.exit(0)


    if list:
        print "Creating RawDiskDriver device",device, "with",size,"bytes"
    rdd = RawDiskDriver (device,eod_cookie,size)
    #rdd = DelayDriver (device,eod_cookie,size)
    rdd.load( eod_cookie )

    cookie = {}

    try:
        if list:
            print "writing 1 0's"
        rdd.open_file_write()
        rdd.write_block("0"*1)
        cookie[0] = rdd.close_file_write()
        if list:
            print "   ok",cookie[0]

        if list:
            print "writing 10 1's"
        rdd.open_file_write()
        rdd.write_block("1"*10)
        cookie[1] = rdd.close_file_write()
        if list:
            print "   ok",cookie[1]

        if list:
            print "writing 100 2's"
        rdd.open_file_write()
        rdd.write_block("2"*100)
        cookie[2] = rdd.close_file_write()
        if list:
            print "   ok",cookie[2]

        if list:
            print "writing 1,000 3's"
        rdd.open_file_write()
        rdd.write_block("3"*1000)
        cookie[3] = rdd.close_file_write()
        if list:
            print "   ok",cookie[3]

        if list:
            print "writing 10,000 4's"
        rdd.open_file_write()
        rdd.write_block("4"*10000)
        cookie[4] = rdd.close_file_write()
        if list:
            print "   ok",cookie[4]

        if list:
            print "writing 100,000 5's"
        rdd.open_file_write()
        rdd.write_block("5"*100000)
        cookie[5] = rdd.close_file_write()
        if list:
            print "   ok",cookie[5]

        if list:
            print "writing 1,000,000 6's"
        rdd.open_file_write()
        rdd.write_block("6"*1000000)
        cookie[6] = rdd.close_file_write()
        if list:
            print "   ok",cookie[6]

        if list:
            print "writing 1,000,000 7's"
        rdd.open_file_write()
        rdd.write_block("7"*1000000)
        cookie[7] = rdd.close_file_write()
        print "   ok",cookie[7]

    except:
        if list:
            print "ok, processed exception:"\
                  #,sys.exc_info()[0],sys.exc_info()[1]

    if list:
        print "EOD cookie:",rdd.get_eod()
        print "lower bound on bytes available:", rdd.get_eod_remaining_bytes()

    for k in cookie.keys() :
        rdd.open_file_read(cookie[k])
        readback = rdd.read_block()
        rlen = len(readback)
        if rlen != 10**k and rlen != rdd.blocksize :
            print "Read error on cookie",k, cookie[k],"- not enough bytes. "\
                  +"Read=",rlen ," should have read= ",10**k
            status = status|1
        if list:
            print "cookie=",k," readback[0]=",readback[0]\
                  ,"readback[end]=",readback[rlen-1]
        if readback[0] != repr(k) or readback[rlen-1] != repr(k) :
            print "Read error. ",  cookie[k], "Should have read",k, " but "\
                  ,"First=",readback[0],"  Last=",readback[rlen-1]
            status = status|2
        rdd.close_file_read()

    rdd.unload()

    sys.exit(status)
















