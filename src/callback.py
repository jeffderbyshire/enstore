###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import time
import sys, os
import string
import random
import select
import errno
import socket

# enstore imports
import lockfile
import Trace
import e_errors
import checksum
import hostaddr
import socket_ext




HUNT_PORT_LOCK_DIR = "/tmp/enstore"
HUNT_PORT_LOCK_FILE="hunt_port_lock"
HUNT_PORT_LOCK=os.path.join(HUNT_PORT_LOCK_DIR, HUNT_PORT_LOCK_FILE)

# see if we can bind to the selected tcp host/port
def try_a_port(host, port, reuseaddr=1) :
    Trace.trace(16, "try_a_port: trying TCP port %s %s" % (host, port))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if reuseaddr:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if 0: #XXX CGW
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_DONTROUTE,1)
        sock.bind((host, port))
        sock.listen(4)  ## Got to listen right away, to prevent another bind
                        ## with REUSEADDR from succeeding
        interface=hostaddr.interface_name(host)
        if interface:
            Trace.trace(16,"bindtodev:  %s %s %s"%(host,port,interface))
            if 0: ##XXX CGW
                status=socket_ext.bindtodev(sock.fileno(),interface)
            else:
                status =0
            if status and status != errno.ENOSYS:
                Trace.log(e_errors.ERROR, "bindtodev(%s): %s"%(interface,os.strerror(status)))
    except socket.error, detail:
	try:
            sock.close()
        except:
            pass
        Trace.trace(16,'try_a_port FAILURE %s'%(detail,))
        return (0 , 0)
    return 1 , sock

# get an unused tcp port for communication
def get_callback_port(start,end,use_multiple=0,fixed_ip=None,verbose=0):

    if use_multiple and fixed_ip:
        raise "Error: get_callback_port: cannot set both use_multiple and fixed_ip"

    host_name,junk,ips = hostaddr.gethostinfo(verbose)
    ca = ips[0]
    reuseaddr=1
    if use_multiple:
        interface_tab = hostaddr.get_multiple_interfaces(verbose)
    elif fixed_ip:
	interface_tab = [(fixed_ip, 1)]
    else:
        interface_tab = [(ips[0], 1)]
    # First acquire the hunt lock.  Once we have it, we have the exclusive right
    # to hunt for a port.  Hunt lock will (I hope) properly serlialze the
    # waiters so that they will be services in the order of arrival.
    # Because we use file locks instead of semaphores, the system will
    # properly clean up, even on kill -9s.
    #lockf = open ("/var/lock/hsm/lockfile", "w")
    if not os.access(HUNT_PORT_LOCK_DIR, os.W_OK):
        os.mkdir(HUNT_PORT_LOCK_DIR)
    lockf = open (HUNT_PORT_LOCK, "w")
    Trace.trace(20,"get_callback_port - trying to get lock on node %s %s"%(host_name,ca))
    lockfile.writelock(lockf)  #holding write lock = right to hunt for a port.
    Trace.trace(20,"get_callback_port - got the lock - hunting for port")

    tot_bw = 0
    for (ip, bw) in interface_tab:
        tot_bw = tot_bw+bw
    n_tries = (end - start)*tot_bw
    n_interfaces = len(interface_tab)
    # now check for a port we can use
    while  1:
        #remember, only person with lock is pounding  hard on this
        next_port_to_try={}
        for which_interface in range(len(interface_tab)):
            next_port_to_try[which_interface]=start
        count = 0
        which_interface=0
        host = None
        while count < n_tries:
            count = count + 1
            if not host:
                host, bw = interface_tab[which_interface]
            if bw<=0:
                which_interface = (which_interface+1)%n_interfaces
                host, bw = interface_tab[which_interface]
            bw = bw-1
            port = next_port_to_try[which_interface]
            if use_multiple:
                Trace.trace(16,"multiple interface: trying %s %s" % (host,port))
            if verbose>2:
                print "trying port", host, port
            success, mysocket = try_a_port (host, port, reuseaddr)
            # if we got a lock, give up the hunt lock and return port
            if success :
                if verbose>2: print "success"
                lockfile.unlock(lockf)
                lockf.close()
                return host, port, mysocket
            else:
                if verbose>2: print "failure"
                port = port+1
                if port >= end:
                    port = start
                next_port_to_try[which_interface] = port
                
        #  otherwise, we tried all ports, try later.
        sleeptime = 1
        msg = "get_callback_port: all ports from %s to %s used, waiting %s seconds"%(start,end,sleeptime)
        if verbose>2: print msg
        Trace.log(e_errors.INFO, repr(msg))
        time.sleep (sleeptime)

def hex8(x):
    s=hex(x)[2:]  #kill the 0x
    if type(x)==type(1L): s=s[:-1]  # kill the L
    l = len(s)
    if l>8:
        raise OverflowError, x
    return '0'*(8-l)+s
    

# get an unused tcp port for control communication
def get_callback(use_multiple=0,fixed_ip=None,verbose=0):
    return get_callback_port( 7600, 7800, use_multiple, fixed_ip, verbose )

# get an unused tcp port for data communication - called by mover
def get_data_callback(use_multiple=0, fixed_ip=None,verbose=0):
    return get_callback_port( 7800, 8000, use_multiple, fixed_ip, verbose )

#send a message, with bytecount and rudimentary security
def write_tcp_raw(sock,msg):
    max_pkt_size=16384
    try:
        l = len(msg)
        ptr=0
        sock.send("%08d"%(len(msg),))
        salt=random.randint(11,99)
        sock.send("ENSTOR%s"%(salt,))
        while ptr<l:
            nwritten=sock.send(msg[ptr:ptr+max_pkt_size])
            if nwritten<=0:
                break
            ptr = ptr+nwritten
        sock.send(hex8(checksum.adler32(salt,msg,l)))
    except socket.error, detail:
        Trace.trace(6,"write_tcp_raw: socket.error %s"%(detail,))
        ##XXX Further sends will fail, our peer will notice incomplete message


# send a message which is a Python object
def write_tcp_obj(sock,obj):
    return write_tcp_raw(sock,repr(obj))

#recv with a timeout
def timeout_recv(sock,nbytes,timeout=15*60):
    fds,junk,junk = select.select([sock],[],[],timeout)
    if sock not in fds:
        return ""
    return sock.recv(nbytes)
    

# read a complete message
def read_tcp_raw(sock):
    tmp = timeout_recv(sock,8) 
    try:
        bytecount = string.atoi(tmp)
    except:
        bytecount = None
    if len(tmp)!=8 or bytecount is None:
        Trace.trace(6,"read_tcp_raw: bad bytecount %s"%(tmp,))
        return ""
    tmp = timeout_recv(sock,8) # the 'signature'
    if len(tmp)!=8 or tmp[:6] != "ENSTOR":
        Trace.trace(6,"read_tcp_raw: invalid signature %s"%(tmp,))
        return ""
    salt=string.atoi(tmp[6:])
    msg = ""
    while len(msg) < bytecount:
        tmp = timeout_recv(sock,bytecount - len(msg))
        if not tmp:
            break
        msg = msg+tmp
    if len(msg)!=bytecount:
        Trace.trace(6,"read_tcp_raw: bytecount mismatch %s != %s"%(len(msg),bytecount))
        return ""
    tmp = timeout_recv(sock,8)
    crc = string.atol(tmp, 16)  #XXX 
    mycrc = checksum.adler32(salt,msg,len(msg))
    if crc != mycrc:
        Trace.trace(6,"read_tcp_raw: checksum mismatch %s != %s"%(mycrc, crc))
        return ""
    return msg



def read_tcp_obj(sock) :
    s=read_tcp_raw(sock)
    if not s:
        raise "TCP connection closed"  #XXX This is not caught anywhere!!! cgw
    return eval(s)

    
# return a mover tcp socket
def mover_callback_socket(ticket, use_multiple=1, verbose=0) :
    host, port = ticket['mover']['callback_addr']    
    Trace.trace(16,'mover_callback_socket host='+\
                repr(host)+" port="+\
                repr(port))



    ##XXX this hack is to work around  a problem on Linux 2.0 (?) where socket/bind/connect
    ##fails with an errno 99.  If the multiple interface configuration file is not found,
    ##don't bind the socket before doing the connect
    if not hostaddr.get_interface_file_name():
        localhost, localport, sock = ("<Not bound>", "<Not bound>",
                                      socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    else:
        localhost, localport, sock = get_callback_port(7001, 8000, use_multiple=use_multiple,
                                                       verbose=verbose)
        
    Trace.trace(16, "mover_callback_socket: using %s %s" % (localhost, localport))
    sock.connect((host, port))
    Trace.trace(16, "mover_callback_socket: connected,  local=%s peer=%s" % (sock.getsockname(),
                                                                             sock.getpeername()))
    return sock

# return a library manager tcp socket
def library_manager_callback_socket(ticket) :
    Trace.trace(16,'library_manager_server_callback_socket host='+\
                repr(ticket['library_manager_callback_host'])+" port="+\
                repr(ticket['library_manager_callback_port']))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['library_manager_callback_host'], \
                 ticket['library_manager_callback_port'])
    return sock

# return a library manager tcp socket
def volume_server_callback_socket(ticket) :
    Trace.trace(16,'volume_server_callback_socket host='+\
                repr(ticket['volume_clerk_callback_host'])+" port="+\
                repr(ticket['volume_clerk_callback_port']))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['volume_clerk_callback_host'], \
                 ticket['volume_clerk_callback_port'])
    return sock

# return a file clerk tcp socket
def file_server_callback_socket(ticket) :
    Trace.trace(16,'file_server_callback_socket host='+\
                repr(ticket['file_clerk_callback_host'])+" port="+\
                repr(ticket['file_clerk_callback_port']))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['file_clerk_callback_host'], \
                 ticket['file_clerk_callback_port'])
    return sock

# return and admin clerk tcp socket
def admin_server_callback_socket(ticket) :
    Trace.trace(16,'admin_server_callback_socket host='+\
                repr(ticket['admin_clerk_callback_host'])+" port="+\
                repr(ticket['admin_clerk_callback_port']))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['admin_clerk_callback_host'], \
                 ticket['admin_clerk_callback_port'])
    return sock

# send ticket/message on user tcp socket and return user tcp socket
def user_callback_socket(ticket) :
    host, port = ticket['callback_addr']
    Trace.trace(16,'user_callback_socket host='+\
                repr(host)+" port="+\
                repr(port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    write_tcp_obj(sock,ticket)
    return sock

# send ticket/message on tcp socket
def send_to_user_callback(ticket) :
    host, port = ticket['callback_addr']
    Trace.trace(16,'send_to_user_callback host='+\
                repr(host)+" port="+\
                repr(port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    write_tcp_obj(sock,ticket)
    sock.close()

if __name__ == "__main__" :
    import sys
    Trace.init("CALLBACK")
    Trace.trace(6,"callback called with args "+repr(sys.argv))

    c = get_callback()
    Trace.log(e_errors.INFO,"callback exit ok callback="+repr(c))





