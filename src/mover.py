#!/usr/bin/python

import sys
from os import *
from time import *
from configuration_client import *
from volume_clerk_client import VolumeClerkClient
from file_clerk_client import FileClerkClient
from udp_client import UDPClient
from callback import *
from dict_to_a import *
from driver import RawDiskDriver

csc = configuration_client()
u = UDPClient()

class Mover :
	def move_forever(self, name) :
		self.name = name
		self.nowork({})
		while 1:
			ticket = self.send_vol_manager()
			try: 
				function = ticket["work"]
			except KeyError:
				raise "assert error Bogus stuff from vol mgr"
			exec ("self." + function + "(ticket)")


	def send_vol_manager(self) :
		ticket = u.send(self.next_volmgr_request, 
				(self.library_manager_host, 
			     	 self.library_manager_port)
                                )
		return ticket

	def send_user_last(self, ticket):
		self.control_socket.send(dict_to_a(ticket))
		self.control_socket.close()
		#when I have debugged this, blow away any socket exceptions

	def nowork(self, ticket) :
		sleep(1)
		# An adminsitrator can change out configuration on the fly.
		# this is useful when a "library" is really one robot 
		# with multiple uses, or when we need to manually load balance
		# movers attacke to virtual library.... 
		csc = configuration_client()
		mconfig = csc.get(self.name)
		if not mconfig["status"] == "ok" :
			raise "could not start mover up:" + mconfig["status"]
		self.library_device = mconfig["library_device"]
		self.driver_name = mconfig["driver"]
		self.device = mconfig["device"]
		self.library = mconfig["library"]
	
		# now get info asssociated with our volume manager
		csc = configuration_client()
		lconfig = csc.get_uncached(self.library + ".library_manager")
		self.library_manager_host = lconfig["host"]
		self.library_manager_port = lconfig["port"]

		# announce ourselves
		self.idle_mover_next()


	def bind_volume(self, ticket) :
		self.external_label = ticket["external_label"]
		ss = VolumeClerkClient(csc)
		vticket = ss.inquire_vol(self.external_label)
		if not vticket["status"] == "ok" :
			self.unilateral_unbind_next()
			return
		self.vticket = vticket
		self.driver = eval(self.driver_name + "('" + 
				  self.device + "','" + 
				  vticket["eod_cookie"] + "'," + 
				  `vticket["remaining_bytes"]` +
					")")

		ml = MediaLoaderClient(self.library + ".media_loader")
		lmticket = ml.load(self.external_label, self.library_device)
		if not lmticket["status"] == "ok" :
			if lmticket["status"] == "media_in_another_device" :
			# it is possible under normal functioning of the
			#  system to be in the following race condition
			#    "the volume mgr told another mover to unbind.
			#    the mover responds promptly, but more work for the
			#    volume mgr arrives and is given to a new mover 
			#    before the old volume was given back to the 
			#    library 
				sleep (10)
			self.unilateral_unbind_next()
			return

		self.driver.load()

		self.have_bound_volume_next()

	def unbind_volume(self, ticket) :

		ml = MediaLoaderClient(self.library + ".media_loader")
		#
		# do any rewind unload or eject operations on the device
		#
		self.driver.unload()
		ticket = ml.unload(self.external_label, 
						self.library_device)
		if not ticket["status"] == "ok" :
			raise "media loader cannot unload my volume"

		# need to call the driver destructor....
		self.idle_mover_next()
		

	def get_user_sockets(self, ticket) :

		# get a port for the data transfer
		# tell the user I'm your mover and here's your ticket

        	mover_host, mover_port, listen_socket = get_callback()
		listen_socket.listen(4)
		ticket["mover_callback_host"] = mover_host
		ticket["mover_callback_port"] = mover_port
		self.control_socket = user_callback_socket(ticket)
 	
		# we expect a prompt call-back here, and should protect
		# against users not getting back to us. The best protection
		# would be to kick off if the user dropped the control_socket, 
		# but I am at home and am not able to find documentation 
		# on select...

		data_socket, address = listen_socket.accept()
		self.data_socket = data_socket
		listen_socket.close()

	def write_to_hsm(self, ticket) :
	
		if not ticket["external_label"] == self.external_label :
			raise "volume manager and I disagree on volume"
		ss = VolumeClerkClient(csc)
		vticket = ss.set_writing(self.external_label)
		if not ticket["status"] == "ok" :
			raise "volume clerk forgot about this volume"

		# space to where the file will begin and save location 
		# information for where futrure reads will have to 
		# space the drive to.

		self.get_user_sockets(ticket)

		
		nb = ticket["size_bytes"]
		bytes_recvd = 0
		media_error = 0
		media_full  = 0
		drive_error = 0
		user_send_error = 0
		anything_written = 0
		bof_space_cookie = 0
		self.driver.open_file_write()
		while 1:
			buff = self.data_socket.recv(self.driver.get_iomax())
			l = len(buff)
			bytes_recvd = bytes_recvd + l
			if l == 0 : break
			self.driver.write_block(buff)
			anything_written = 1

		self.data_socket.close()
		file_cookie = self.driver.close_file_write()
		eod_cookie = self.driver.get_eod_cookie()
		remaining_bytes = self.driver.get_eod_remaining_bytes()

		ss = VolumeClerkClient(csc)

		if not bytes_recvd == ticket["size_bytes"] :
			user_send_error = 1

		if user_send_error:
			self.vticket = ss.set_remaining_bytes(
				ticket["external_label"], 
				remaining_bytes, 
				eod_cookie)
			self.have_bound_volume_next()
			self.send_user_last({"status" : "user_protocol_error"})
			return

		elif media_full :
			ss.set_system_readonly(ticket["external_label"])
			self.unilateral_unbind_next()
			self.send_user_last({"status" : "retry"})
			return

		elif media_error :
			ss.set_system_readonly(ticket["external_label"])
			self.send_user_last({"status" : "retry"})
			self.unilateral_unbind_next()
			return

		elif drive_error :
			ss.set_hung(ticket["external_label"])
			self.send_user_last({"status" : "retry"})
			self.unilateral_unbind_next()
		        #since we will kill ourselves, tell the volume mgr
			#now....
			ticket = send_vol_manager()
			raise "device panic -- I want to do no harm to media"
			return
		
		# All is well.
		# Tell volume server
		self.vticket = ss.set_remaining_bytes(
				ticket["external_label"], 
				remaining_bytes, 
				eod_cookie)

		# tell file clerk server

		fc = FileClerkClient(csc)
		fticket = fc.new_bit_file(
			file_cookie, 
			ticket["external_label"], 0, 0)

		# really only bfid is needed, but save other useful information for user too
		ticket["bfid"] = fticket["bfid"]
		ticket["bof_space_cookie"] = fticket["bof_space_cookie"]
		ticket["complete_crc"] = fticket["complete_crc"]
		ticket["sanity_cookie"] = fticket["sanity_cookie"]
		ticket["device"] = self.device
		ticket["driver_name"] = self.driver_name
		ticket["device_name"] = self.name
		ticket["library_device"] = self.library_device
		ticket["capacity_bytes"] = self.vticket["capacity_bytes"]
		ticket["remaining_bytes"] = self.vticket["remaining_bytes"]
		ticket["media_type"] = self.vticket["media_type"]
		
		# tell user
		self.send_user_last(ticket)
		# go around for more
		self.have_bound_volume_next()

	def read_from_hsm(self, ticket) :
		if not ticket["external_label"] == self.external_label :
			raise "volume manager and I disagree on volume"
		ss = VolumeClerkClient(csc)
		vticket = ss.inquire_vol(self.external_label)
		if not ticket["status"] == "ok" :
			raise "volume clerk forgot about this volume"

		# space to where the file will begin and save location 
		# information for where futrure reads will have to 
		# space the drive to.

		self.get_user_sockets(ticket)		
		media_error = 0
		media_full  = 0
		drive_error = 0
		user_recieve_error = 0
		bytes_sent = 0
		self.driver.open_file_read(ticket["bof_space_cookie"])
		while 1:
			buff = self.driver.read_block()
			l = len(buff)
			if l == 0 : break
			self.data_socket.send(buff)
			bytes_sent = bytes_sent + l
			anything_sent = 1
		self.data_socket.close()

		if media_error :
			ss.set_system_readonly(ticket["external_label"])
			self.send_user_last({"status" : "retry"})
			self.unilateral_unbind_next()
			return

		elif drive_error :
			ss.set_hung(ticket["external_label"])
			self.send_user_last({"status" : "retry"})
			self.unilateral_unbind_next()
		        #since we will kill ourselves, tell the volume mgr
			#now....
			ticket = send_vol_manager()
			raise "device panic -- I want to do no harm to media"
			return
		
		# read has finished correctly
		# tell user
		self.send_user_last(ticket)
		# go around for more
		self.have_bound_volume_next()


	def idle_mover_next(self):
		self.next_volmgr_request = {"work" : "idle_mover",
			"mover" : self.name
			}

	def have_bound_volume_next(self):
		self.next_volmgr_request = {}
		for k in self.vticket.keys() :
			self.next_volmgr_request[k] = self.vticket[k]
		self.next_volmgr_request["work"] = "have_bound_volume"
		self.next_volmgr_request["mover"] = self.name

	def unilateral_unbind_next(self):
		self.next_volmgr_request = {"work" : "unilateral_unbind",
			"external_label" : self.external_label,
			"mover" : self.name
			}

class MediaLoaderClient :

		def __init__(self, library) :
			self.nload = 0
			pass
						
		def load(self, external_label, drive) :
			self.nload = self.nload + 1
			if self.nload % 10 == 0 :
				return {"status" : "media_in_another_device"}
			return {"status" : "ok"}

		def unload(self, external_label, drive) :
			return {"status" : "ok"}

if __name__ == "__main__" :
	while (1) :
		mv = Mover()
		mv.move_forever (sys.argv[1])
