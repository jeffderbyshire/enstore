import string
import types

# event relay message types, add new ones to the list at the 
# bottom too
ALL = "all"
NOTIFY = "notify"
ALIVE = "alive"
NEWCONFIGFILE = "newconfigfile"
CLIENT = "client"
STATE = "state"
TRANSFER = "transfer"
DISCONNECT = "disconnect"
CONNECT = "connect"
UNLOAD = "unload"
LOADED = "loaded"
MSG_FIELD_SEPARATOR = " "

def decode_type(msg):
    return string.split(msg, MSG_FIELD_SEPARATOR, 1)


class EventRelayMsg:

    def __init__(self, host="", port=-1):
	self.type = ""
	self.extra_info = ""
	self.host = host
	if type(port) == types.StringType:
	    self.port = string.atoi(port)
	else:
	    self.port = port

    def message(self):
	return("%s%s%s"%(self.type, MSG_FIELD_SEPARATOR, self.extra_info))

    def send(self, sock, event_relay_addr):
	sock.sendto(self.message(), (event_relay_addr))

    def encode_addr(self):
	return "%s %s"%(self.host, self.port)

# Message format :  notify host port msg_type1 msg_type1 ...
class EventRelayNotifyMsg(EventRelayMsg):

    def encode(self, msg_type_l):
	self.type = NOTIFY
	self.extra_info = self.encode_addr()
	for msg_type in msg_type_l:
	    self.extra_info = "%s%s%s"%(self.extra_info, MSG_FIELD_SEPARATOR, msg_type)

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.host, self.port, self.msg_types = string.split(self.extra_info, 
							    MSG_FIELD_SEPARATOR, 2)
	
# Message format:   alive host port server_name 
class EventRelayAliveMsg(EventRelayMsg):

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.host, self.port, self.server = string.split(self.extra_info, 
							 MSG_FIELD_SEPARATOR, 2)

    def encode(self, name):
	self.type = ALIVE
	self.extra_info = self.encode_addr()
	self.extra_info = "%s%s%s"%(self.extra_info, MSG_FIELD_SEPARATOR, name)

# Message format:  newconfigfile host port
class EventRelayNewConfigFileMsg(EventRelayMsg):

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.host, self.port = string.split(self.extra_info, 
					    MSG_FIELD_SEPARATOR, 1)

    def encode(self):
	self.type = NEWCONFIGFILE
	self.extra_info = self.encode_addr()

# Message format:  client host work file_family more_info
class EventRelayClientMsg(EventRelayMsg):

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.host, self.work, self.file_family, \
		   self.more = string.split(self.extra_info, 
					    MSG_FIELD_SEPARATOR, 3)

    def encode(self, host, work, file_family, more_info):
	self.type = CLIENT
	self.extra_info = "%s %s %s %s"%(host, work, file_family, 
					 more_info)

# Message format:  state short_name state_name
class EventRelayStateMsg(EventRelayMsg):

    def __init__(self, short_name):
	EventRelayMsg.__init__(self)
	self.short_name = short_name

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.short_name, self.state_name = string.split(self.extra_info, 
							MSG_FIELD_SEPARATOR, 1)

    def encode(self, state_name):
	self.type = STATE
	self.extra_info = "%s %s"%(self.short_name, state_name)

# Message format:  transfer short_name bytes_read bytes_to_read
class EventRelayTransferMsg(EventRelayMsg):

    def __init__(self, short_name):
	EventRelayMsg.__init__(self)
	self.short_name = short_name

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.short_name, self.bytes_read, \
			 self.bytes_to_read = string.split(self.extra_info, 
							   MSG_FIELD_SEPARATOR, 2)

    def encode(self, bytes_read, bytes_to_read):
	self.type = TRANSFER
	self.extra_info = "%s %s %s"%(self.short_name, bytes_read, bytes_to_read)

# Message format:  disconnect short_name client_hostname
class EventRelayDisconnectMsg(EventRelayMsg):

    def __init__(self, short_name):
	EventRelayMsg.__init__(self)
	self.short_name = short_name

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.short_name, self.client_hostname = string.split(self.extra_info, 
							     MSG_FIELD_SEPARATOR, 1)

    def encode(self, client_hostname):
	self.type = DISCONNECT
	self.extra_info = "%s %s"%(self.short_name, client_hostname)

# Message format:  connect short_name client_hostname
class EventRelayConnectMsg(EventRelayMsg):

    def __init__(self, short_name):
	EventRelayMsg.__init__(self)
	self.short_name = short_name

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.short_name, self.client_hostname = string.split(self.extra_info, 
							     MSG_FIELD_SEPARATOR, 1)

    def encode(self, client_hostname):
	self.type = CONNECT
	self.extra_info = "%s %s"%(self.short_name, client_hostname)

# Message format:  unload short_name volume
class EventRelayUnloadMsg(EventRelayMsg):

    def __init__(self, short_name):
	EventRelayMsg.__init__(self)
	self.short_name = short_name

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.short_name, self.volume = string.split(self.extra_info, 
						    MSG_FIELD_SEPARATOR, 1)

    def encode(self, volume):
	self.type = UNLOAD
	self.extra_info = "%s %s"%(self.short_name, state_name)

# Message format:  loaded short_name volume
class EventRelayLoadedMsg(EventRelayMsg):

    def __init__(self, short_name):
	EventRelayMsg.__init__(self)
	self.short_name = short_name

    def decode(self, msg):
	self.type, self.extra_info = decode_type(msg)
	self.short_name, self.volume = string.split(self.extra_info, 
						    MSG_FIELD_SEPARATOR, 1)

    def encode(self, volume):
	self.type = VOLUME
	self.extra_info = "%s %s"%(self.short_name, volume)

# list of supported messages
SUPPORTED_MESSAGES = {NOTIFY : EventRelayNotifyMsg,
		      ALIVE :  EventRelayAliveMsg,
		      NEWCONFIGFILE : EventRelayNewConfigFileMsg,
		      CLIENT : EventRelayClientMsg,
		      STATE : EventRelayStateMsg,
		      TRANSFER : EventRelayTransferMsg,
		      DISCONNECT : EventRelayDisconnectMsg,
		      CONNECT : EventRelayConnectMsg,
		      UNLOAD : EventRelayUnloadMsg,
		      LOADED : EventRelayLoadedMsg
		      }


def decode(msg):
    type, extra_info = decode_type(msg)
    msg_class = SUPPORTED_MESSAGES.get(type, None)
    if msg_class:
	decoded_msg = msg_class()
	decoded_msg.decode(msg)
    else:
	decoded_msg = None
    return decoded_msg


