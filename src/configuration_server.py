#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import sys
import string
import types
import os
import traceback
import pprint

# enstore imports
import setpath

import dispatching_worker
import generic_server
import interface
import Trace
import e_errors
import hostaddr
import callback

MY_NAME = "CONFIG_SERVER"

class ConfigurationDict(dispatching_worker.DispatchingWorker):

    def __init__(self):
	self.print_id="CONFIG_DICT"
        self.serverlist = {}
    def read_config(self, configfile):
        try:
            f = open(configfile,'r')
        except:
            msg = (e_errors.DOESNOTEXIST,"Configuration Server: read_config %s: does not exist"%
                   (configfile,))
            Trace.log( e_errors.ERROR, msg[1] )
            return msg
        code = string.join(f.readlines(),'')
        Trace.trace(9, "Configuration Server read_config: loading enstore configuration from %s"%
                    (configfile,))
        configdict={};
        del configdict # Lint hack, otherwise lint can't see where configdict is defined.
        try:
            exec(code)
            ##I would like to do this in a restricted namespace, but
            ##the dict uses modules like e_errors, which it does not import
        except:
            exc,msg,tb = sys.exc_info()
            fmt =  traceback.format_exception(exc,msg,tb)[2:]
            ##report the name of the config file in the traceback instead of "<string>"
            fmt[0] = string.replace(fmt[0], "<string>", configfile)
            msg = "Configuration Server: "+string.join(fmt, "")
            Trace.log(e_errors.ERROR,msg)
            print msg
            os._exit(-1)
        # ok, we read entire file - now set it to real dictionary
        self.configdict=configdict
        return (e_errors.OK, None)

    # load the configuration dictionary - the default is a wormhole in pnfs
    def load_config(self, configfile):
        try:
            msg = self.read_config(configfile)
            if msg != (e_errors.OK, None):
                return msg
            self.serverlist={}
            conflict = 0
            for key in self.configdict.keys():
                if not self.configdict[key].has_key('status'):
                    self.configdict[key]['status'] = (e_errors.OK, None)
                for insidekey in self.configdict[key].keys():
                    if insidekey == 'host':
                        self.configdict[key]['hostip'] = hostaddr.name_to_address(
                            self.configdict[key]['host'])
                        if not self.configdict[key].has_key('port'):
                            self.configdict[key]['port'] = -1
                        # check if server is already configured
                        for configured_key in self.serverlist.keys():
                            if (self.serverlist[configured_key][1] == 
                                self.configdict[key]['hostip'] and 
                                self.serverlist[configured_key][2] == 
                                self.configdict[key]['port']):
                                msg = "Configuration Conflict detected for "\
                                      "hostip "+\
                                      repr(self.configdict[key]['hostip'])+ \
                                      "and port "+ \
                                      repr(self.configdict[key]['port'])
                                Trace.log(10, msg)
                                conflict = 1
                                break
                        if not conflict:
                            self.serverlist[key]= (self.configdict[key]['host'],self.configdict[key]['hostip'],self.configdict[key]['port'])
                        break

            if conflict:
                return(e_errors.CONFLICT, "Configuration conflict detected. "
                       "Check configuration file")
            return (e_errors.OK, None)

        # even if there is an error - respond to caller so he can process it
        except:
            exc,msg,tb=sys.exc_info()
            return str(exc), str(msg)


    # just return the current value for the item the user wants to know about
    def lookup(self, ticket):
        try:
            # everything is based on lookup - make sure we have this
            try:
                key="lookup"
                lookup = ticket[key]
            except KeyError:
                Trace.trace(6,"lookup "+repr(key)+" key is missing")
                ticket["status"] = (e_errors.KEYERROR, "Configuration Server: "+key+" key is missing")
                self.reply_to_caller(ticket)
                return

            # look up in our dictionary the lookup key
            try:
                out_ticket = self.configdict[lookup]
            except KeyError:
                Trace.trace(8,"lookup no such name"+repr(lookup))
                out_ticket = {"status": (e_errors.KEYERROR,
                                         "Configuration Server: no such name: "
                                         +repr(lookup))}
            self.reply_to_caller(out_ticket)
            Trace.trace(6,"lookup "+repr(lookup)+"="+repr(out_ticket))
            return

        # even if there is an error - respond to caller so he can process it
        except:
            exc, msg, tb = sys.exc_info()
            ticket["status"] = (str(exc), str(msg))
            self.reply_to_caller(ticket)
            Trace.trace(6,"lookup %s %s"%(exc,msg))
            return

    # return a list of the dictionary keys back to the user
    def get_keys(self, ticket):
        try:
            skeys = self.configdict.keys()
            skeys.sort()
            out_ticket = {"status" : (e_errors.OK, None), "get_keys" : (skeys)}
            self.reply_to_caller(out_ticket)
            return

        # even if there is an error - respond to caller so he can process it
        except:
            exc, msg, tb = sys.exc_info()
            ticket["status"] = str(exc), str(msg)
            self.reply_to_caller(ticket)
            Trace.trace(6,"get_keys %s %"%(exc,msg))
            return


    # return a dump of the dictionary back to the user
    def dump(self, ticket):
        try:
            ticket['status']=(e_errors.OK, None)
            reply=ticket.copy()
	    reply["dump"] = self.configdict
            self.reply_to_caller(ticket)
            addr = ticket['callback_addr']
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(addr)
            callback.write_tcp_obj(sock,reply)
            sock.close()

        # even if there is an error - respond to caller so he can process it
        except:
            exc,msg,tb=sys.exc_info()
            ticket["status"] = str(exc),str(msg)
            try:
                self.reply_to_caller(ticket)
            except:
                pass
            Trace.trace(6,"dump %s %s"%(exc,msg))


    # reload the configuration dictionary, possibly from a new file
    def load(self, ticket):
	try:
	    try:
		configfile = ticket["configfile"]
		out_ticket = {"status" : self.load_config(configfile)}
	    except KeyError:
		out_ticket = {"status" : (e_errors.KEYERROR, "Configuration Server: no such name")}
	    self.reply_to_caller(out_ticket)
	    Trace.trace(6,"load"+repr(out_ticket))
	    return

	# even if there is an error - respond to caller so he can process it
	except:
            exc,msg,tb=sys.exc_info()
	    ticket["status"] = str(exc),str(msg)
	    self.reply_to_caller(ticket)
	    Trace.trace(6,"load %s %s"%(exc,msg))
	    return

    # get list of the Library manager movers
    def get_movers(self, ticket):
	ret = self.get_movers_internal(ticket)
	self.reply_to_caller(ret)

    def get_movers_internal(self, ticket):
        ret = []
	if ticket.has_key('library'):
	    # search for the appearance of this library manager
	    # in all configured movers
	    for srv in self.configdict.keys():
		if string.find (srv, ".mover") != -1:
		    item = self.configdict[srv]
                    for key in ('library', 'libraries'):
                        if item.has_key(key):
                            if type(item[key]) == types.ListType:
                                for i in item[key]:
                                    if i == ticket['library']:
                                        mv = {'mover' : srv,
                                              'address' : (item['hostip'], 
                                                          item['port'])
                                              }
                                        ret.append(mv)
                            else:
                                if item[key] == ticket['library']:
                                    mv = {'mover' : srv,
                                          'address' : (item['hostip'], 
                                                       item['port'])
                                          }
                                    ret.append(mv)
        return ret

    def get_media_changer(self, ticket):
        movers = self.get_movers_internal(ticket)
        ##print "get_movers_internal %s returns %s" % (ticket, movers)
        ret = ''
        for m in movers:
            mv_name = m['mover']
            ret =  self.configdict[mv_name].get('media_changer','')
            if ret:
                break
        self.reply_to_caller(ret)
        
    #get list of library managers
    def get_library_managers(self, ticket):
        ret = {}
        for key in self.configdict.keys():
            index = string.find (key, ".library_manager")
            if index != -1:
                library_name = key[:index]
                item = self.configdict[key]
                ret[library_name] = {'address':(item['host'],item['port']),
				     'name': key}
        self.reply_to_caller(ret)
        Trace.trace(6,"get_library_managers"+repr(ret))

    def reply_serverlist( self, ticket ):
        out_ticket = {"status" : (e_errors.OK, None), 
                      "server_list" : self.serverlist }
        self.reply_to_caller(out_ticket)
 
        
    def get_dict_entry(self, skeyValue):
        slist = []
        for key in self.configdict.keys():
            if skeyValue in self.configdict[key].items():
                slist.append(key)
        return slist

    def get_dict_element(self, ticket):
        ret = {"status" : (e_errors.OK, None)}
        ret['servers'] = self.get_dict_entry(ticket['keyValue'])
        self.reply_to_caller(ret)
        Trace.trace(6,"get_dict_element"+repr(ret))


class ConfigurationServer(ConfigurationDict, generic_server.GenericServer):

    def __init__(self, csc, configfile=interface.default_file()):
	self.running = 0
	self.print_id = MY_NAME
        Trace.trace(10,
            "Instantiating Configuration Server at %s %s using config file %s"
            %(csc[0], csc[1], configfile))

        # make a configuration dictionary
        cd =  ConfigurationDict()

        # default socket initialization - ConfigurationDict handles requests
        dispatching_worker.DispatchingWorker.__init__(self, csc)

        # now (and not before,please) load the config file user requested
        self.load_config(configfile)

	self.running = 1

        # always nice to let the user see what she has
        Trace.trace(10, repr(self.__dict__))

class ConfigurationServerInterface(generic_server.GenericServerInterface):

    def __init__(self):
        # fill in the defaults for possible options
	self.config_file = ""
        generic_server.GenericServerInterface.__init__(self)

        # bomb out if we can't find the file
        statinfo = os.stat(self.config_file)
        Trace.trace(10,'stat for '+repr(self.config_file)+' '+repr(statinfo))

    # define the command line options that are valid
    def options(self):
        return generic_server.GenericServerInterface.options(self)+\
	       ["config_file=",]


if __name__ == "__main__":
    Trace.init(MY_NAME)
    Trace.trace( 6, "called args="+repr(sys.argv) )
    import sys

    # get the interface
    intf = ConfigurationServerInterface()

    # get a configuration server
    cs = ConfigurationServer((intf.config_host, intf.config_port),
	                     intf.config_file)

    while 1:
        try:
            Trace.trace(6,"Configuration Server (re)starting")
            cs.serve_forever()
	except SystemExit, exit_code:
	    sys.exit(exit_code)
        except:
	    cs.serve_forever_error(MY_NAME)
            continue

    Trace.trace(6,"Configuration Server finished (impossible)")
