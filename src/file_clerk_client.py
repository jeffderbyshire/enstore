###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import time
import string
import errno
import sys

# enstore imports
import generic_client
import backup_client
import udp_client
import callback
import Trace
import e_errors

MY_NAME = "FILE_C_CLIENT"
MY_SERVER = "file_clerk"

class FileClient(generic_client.GenericClient, 
                      backup_client.BackupClient):

    def __init__( self, csc, bfid=0, server_addr=None ):
        generic_client.GenericClient.__init__(self, csc, MY_NAME)
        self.u = udp_client.UDPClient()
	self.bfid = bfid
        ticket = self.csc.get( MY_SERVER )
	if server_addr != None: self.server_addr = server_addr
	else:                  self.server_addr = (ticket['hostip'],ticket['port'])

    def send (self, ticket, rcv_timeout=0, tries=0):
        Trace.trace( 12, 'send to volume clerk %s'%(self.server_addr,))
        x = self.u.send( ticket, self.server_addr, rcv_timeout, tries )
        return x

    def new_bit_file(self, ticket):
        r = self.send(ticket)
        return r

    def set_pnfsid(self, ticket):
        r = self.send(ticket)
        return r

    def set_delete(self, ticket):
        r = self.send(ticket)
        return r

    def get_bfids(self):
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"         : "get_bfids",
                  "callback_addr": (host, port),
                  "unique_id"    : time.time() }
        # send the work ticket to the library manager
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            raise errno.errorcode[errno.EPROTO],"fcc.get_bfids: sending ticket %s"%(ticket,)

        # We have placed our request in the system and now we have to wait.
        # All we  need to do is wait for the system to call us back,
        # and make sure that is it calling _us_ back, and not some sort of old
        # call-back to this very same port. 
        while 1:
            control_socket, address = listen_socket.accept()
            new_ticket = callback.read_tcp_obj(control_socket)
            if ticket["unique_id"] == new_ticket["unique_id"]:
                listen_socket.close()
                break
            else:
                Trace.log(e_errors.INFO,
                          "get_bfids - imposter called us back, trying again")
                control_socket.close()
        ticket = new_ticket
        if ticket["status"][0] != e_errors.OK:
            msg = "get_bfids: failed to setup transfer: status=%s"%(ticket['status'],)
            Trace.trace(7,msg)
            raise errno.errorcode[errno.EPROTO],msg
        # If the system has called us back with our own  unique id, call back
        # the library manager on the library manager's port and read the
        # work queues on that port.


        
        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['file_clerk_callback_addr'])
        
        data_path_socket = callback.file_server_callback_socket(ticket)
        ticket= callback.read_tcp_obj(data_path_socket)
        bfids=''
        while 1:
            msg=callback.read_tcp_raw(data_path_socket)
            if not msg: break
            if bfids: bfids=bfids+','+msg
            else: bfids=msg
        ticket['bfids'] = bfids
        data_path_socket.close()

        # Work has been read - wait for final dialog with file clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            msg = "get_bfids: failed to transfer: status=%s"%(ticket['status'],)
            Trace.trace(7,msg)
            raise errno.errorcode[errno.EPROTO],msg

        return ticket

    def tape_list(self,external_label):
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "tape_list",
                  "callback_addr" : (host, port),
                  "external_label": external_label,
                  "unique_id"     : time.time() }
        # send the work ticket to the file clerk
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            raise errno.errorcode[errno.EPROTO],"fcc.tape_list: sending ticket %s"%(ticket,)

        # We have placed our request in the system and now we have to wait.
        # All we  need to do is wait for the system to call us back,
        # and make sure that is it calling _us_ back, and not some sort of old
        # call-back to this very same port.
        while 1:
            control_socket, address = listen_socket.accept()
            new_ticket = callback.read_tcp_obj(control_socket)
            if ticket["unique_id"] == new_ticket["unique_id"]:
                listen_socket.close()
                break
            else:
	        Trace.log(e_errors.INFO,
                          "tape_list - imposter called us back, trying again")
                control_socket.close()
        ticket = new_ticket
        if ticket["status"][0] != e_errors.OK:
            msg = "tape_list:  failed to setup transfer: status=%s"%(ticket['status'],)
            Trace.trace(7,msg)
            raise errno.errorcode[errno.EPROTO],msg
        # If the system has called us back with our own  unique id, call back
        # the library manager on the library manager's port and read the
        # work queues on that port.
        
        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['file_clerk_callback_addr'])
  
        ticket= callback.read_tcp_obj(data_path_socket)
        tape_list=''
        while 1:
            msg=callback.read_tcp_raw(data_path_socket)
            if not msg: break
            if tape_list: tape_list=tape_list+msg
            else: tape_list=msg
        ticket['tape_list'] = tape_list
        data_path_socket.close()

        # Work has been read - wait for final dialog with file clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            msg = "tape_list: failed to transfer: status=%s"%(ticket['status'],)
            Trace.trace(7,msg)
            raise errno.errorcode[errno.EPROTO],msg

        return ticket


    def bfid_info(self):
        r = self.send({"work" : "bfid_info",
                       "bfid" : self.bfid } )
        return r

    def set_deleted(self, deleted, restore_dir="no"):
        r = self.send({"work"        : "set_deleted",
                       "bfid"        : self.bfid,
                       "deleted"     : deleted,
		       "restore_dir" : restore_dir } )
        return r


    def get_crcs(self, bfid):
        r = self.send({"work"        : "get_crcs",
                       "bfid"        : bfid})
        return r

    def set_crcs(self, bfid, sanity_cookie, complete_crc):
        r = self.send({"work"        : "set_crcs",
                       "bfid"        : bfid,
                       "sanity_cookie": sanity_cookie,
                       "complete_crc": complete_crc})
        return r
        
    # rename volume and volume map
    def rename_volume(self, bfid, external_label, 
		      set_deleted, restore_vm, restore_dir):
        r = self.send({"work"           : "rename_volume",
                       "bfid"           : bfid,
		       "external_label" : external_label,
		       "set_deleted"    : set_deleted,
		       "restore"        : restore_vm,
		       "restore_dir"    : restore_dir } )
	return r

    # rename volume and volume map
    def restore(self, file_name, restore_dir="no"):
        r = self.send({"work"           : "restore_file",
                       "file_name"      : file_name,
		       "restore_dir"    : restore_dir } )
	return r

    # get volume map name for given bfid
    def get_volmap_name(self):
        r = self.send({"work"           : "get_volmap_name",
                       "bfid"           : self.bfid} )
	return r

    # delete bitfile
    def del_bfid(self):
        r = self.send({"work"           : "del_bfid",
                       "bfid"           : self.bfid} )
	return r

class FileClerkClientInterface(generic_client.GenericClientInterface):

    def __init__(self, flag=1, opts=[]):
        # fill in the defaults for the possible options
        self.do_parse = flag
        self.restricted_opts = opts
        self.bfids = 0
        self.list = 0
        self.bfid = 0
        self.backup = 0
        self.deleted = 0
	self.restore = ""
        self.alive_rcv_timeout = 0
        self.alive_retries = 0
        self.get_crcs=None
        self.set_crcs=None
        generic_client.GenericClientInterface.__init__(self)

        
    # define the command line options that are valid
    def options(self):
        if self.restricted_opts:
            return self.restricted_opts
        else:
            return self.client_options()+[
                "bfids","bfid=","deleted=","list=","backup",
                "get_crcs=","set_crcs=",
                "restore=", "recursive"]
            

def do_work(intf):
    # now get a file clerk client
    fcc = FileClient((intf.config_host, intf.config_port), intf.bfid)
    Trace.init(fcc.get_name(MY_NAME))

    ticket = fcc.handle_generic_commands(MY_SERVER, intf)
    if ticket:
        pass

    elif intf.backup:
        ticket = fcc.start_backup()
        ticket = fcc.backup()
        ticket = fcc.stop_backup()

    elif intf.deleted and intf.bfid:
	try:
	    if intf.restore_dir: dir ="yes"
	except AttributeError:
	    dir = "no"
        ticket = fcc.set_deleted(intf.deleted, dir)
        Trace.trace(13, str(ticket))

    elif intf.bfids:
        ticket = fcc.get_bfids()
        print ticket['bfids']

    elif intf.list:
        ticket = fcc.tape_list(intf.list)
        print ticket['tape_list']
        aticket = fcc.alive(MY_SERVER, intf.alive_rcv_timeout,
                            intf.alive_retries) #clear out any zombies from the forked file clerk

    elif intf.bfid:
        ticket = fcc.bfid_info()
	if ticket['status'][0] ==  e_errors.OK:
	    print ticket['fc']
	    print ticket['vc']
    elif intf.restore:
	try:
	    if intf.restore_dir: dir="yes"
	except AttributeError:
	    dir = "no"
	print "file",intf.restore
        ticket = fcc.restore(intf.restore, dir)
    elif intf.get_crcs:
        bfid=intf.get_crcs
        ticket = fcc.get_crcs(bfid)
        print "bfid %s: sanity_cookie %s, complete_crc %s"%(`bfid`,ticket["sanity_cookie"],
                                                 `ticket["complete_crc"]`) #keep L suffix
    elif intf.set_crcs:
        bfid,sanity_size,sanity_crc,complete_crc=string.split(intf.set_crcs,',')
        sanity_crc=eval(sanity_crc)
        sanity_size=eval(sanity_size)
        complete_crc=eval(complete_crc)
        sanity_cookie=(sanity_size,sanity_crc)
        ticket=fcc.set_crcs(bfid,sanity_cookie,complete_crc)
        sanity_cookie = ticket['sanity_cookie']
        complete_crc = ticket['complete_crc']
        print "bfid %s: sanity_cookie %s, complete_crc %s"%(`bfid`,ticket["sanity_cookie"],
                                                            `ticket["complete_crc"]`) #keep L suffix
        
    else:
	intf.print_help()
        sys.exit(0)

    fcc.check_ticket(ticket)

if __name__ == "__main__" :
    Trace.init(MY_NAME)
    Trace.trace(6,"fcc called with args %s"%(sys.argv,))

    # fill in interface
    intf = FileClerkClientInterface()

    do_work(intf)
