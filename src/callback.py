import lockfile
import dict_to_a
# Import SOCKS module if it exists, else standard socket module socket
try:
    import SOCKS; socket = SOCKS
except ImportError:
    import socket

# see if we can bind to the selected host/port
def try_a_port(host, port) :
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(host, port)
    except:
        sock.close()
        return (0 , sock)
    return 1 , sock

# get an unused port for communication
def get_callback() :
    #host = 'localhost'
    (host,ca,ci) = socket.gethostbyaddr(socket.gethostname())

    # First acquire the hunt lock.  Once we have it, we have the exlusive right
    # to hunt for a port.  Hunt lock will (I hope) properly serlialze the
    # waiters so that they will be services in the order of arrival.
    # Because we use file locks instead of semaphores, the system will
    # properly clean up, even on kill -9s.
    lockf = open ("/var/lock/hsm/lockfile", "w")
    lockfile.writelock(lockf)  #holding write lock = right to hunt for a port.

    # now check for a port we can use
    while  1:
        # remember, only person with lock is pounding  hard on this
        for port in range (7600, 7650) :
            success, mysocket = try_a_port (host, port)
            # if we got a lock, give up the hunt lock and return port
            if success :
                lockfile.unlock(lockf)
                lockf.close()
                return host, port, mysocket
        #  otherwise, we tried all ports, try later.
        sleep (1)


# return a mover socket
def mover_callback_socket(ticket) :
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['mover_callback_host'], ticket['mover_callback_port'])
    return sock

# return a library manager socket
def library_manager_callback_socket(ticket) :
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['library_manager_callback_host'], \
                 ticket['library_manager_callback_port'])
    return sock

# send ticket/message on user socket and return user socket
def user_callback_socket(ticket) :
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['user_callback_host'], ticket['user_callback_port'])
    badsock = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    if badsock != 0 :
        print "callback user_callback_socket, block pre-send error:", \
              errno.errorcode[badsock]
    sock.send(dict_to_a.dict_to_a(ticket))
    badsock = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    if badsock != 0 :
        print "callback user_callback_socket, block post-send error:", \
              errno.errorcode[badsock]
    return sock

# send ticket/message
def send_to_user_callback(ticket) :
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(ticket['user_callback_host'], ticket['user_callback_port'])
    badsock = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    if badsock != 0 :
        print "callback send_to_user_callback, block pre-send error:", \
              errno.errorcode[badsock]
    sock.send(dict_to_a.dict_to_a(ticket))
    badsock = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    if badsock != 0 :
        print "callback send_to_user_callback, block post-send error:", \
              errno.errorcode[badsock]
    sock.close()

if __name__ == "__main__" :
    print get_callback()
