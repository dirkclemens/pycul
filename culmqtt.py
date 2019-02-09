#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# based on: 
#   https://gist.github.com/pklaus/4039175
#   https://github.com/pklaus/serialman/blob/master/serialman.py
#   http://stackoverflow.com/questions/17553543/pyserial-non-blocking-read-loop
#   http://stackoverflow.com/questions/14487151/pyserial-full-duplex-communication
#   http://www.fhemwiki.de/wiki/FHT80b
#   http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
#   http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol
#
#   pip3 install pyserial threading2 --user
#   pip3 install paho-mqtt --user
#
import serial
import binascii
import threading
import time
import logging 
from multiprocessing import Process, Queue
from datetime import datetime
import paho.mqtt.client as paho
import ssl

global log
 
################################################################################
# mqtt settings      
################################################################################
try:
    from configparser import ConfigParser
except ImportError:
    from ConfigParser import ConfigParser  # ver. < 3.0

config = ConfigParser()
config.read('/home/smarthome/.credentials/.mqtt') 

MQTT_SERVER 		= config.get('smarthome','mqtt_server')
MQTT_PORT 			= config.get('smarthome','mqtt_port')
MQTT_TLS 			= config.get('smarthome','mqtt_tls')
MQTT_SERVERIP 		= config.get('smarthome','mqtt_serverip')
MQTT_CACERT 		= config.get('smarthome','mqtt_cacert')
MQTT_USER 			= config.get('smarthome','mqtt_user')
MQTT_PASSWD 		= config.get('smarthome','mqtt_passwd')

################################################################################
	# FS20_RAMP-ON-TIME     = 0x1C; #time to reach the desired dim value on dimmers
	# FS20_RAMP-OFF-TIME    = 0x1D; #time to reach the off state on dimmers
	# FS20_ON-OLD-FOR-TIMER-PREV = 0x1E; # old val for timer, then go to prev. state
	# FS20_ON-100-FOR-TIMER-PREV = 0x1F; # 100% for timer, then go to previous state

FS20cmd ={	'00':'FS20_Off',
			'01':'FS20_STEP_006',
			'02':'FS20_STEP_012',
			'03':'FS20_STEP_018',
			'04':'FS20_STEP_025',
			'05':'FS20_STEP_031',
			'06':'FS20_STEP_037',
			'07':'FS20_STEP_043',
			'08':'FS20_STEP_050',
			'09':'FS20_STEP_056',
			'0A':'FS20_STEP_062',
			'0B':'FS20_STEP_068',
			'0C':'FS20_STEP_075',
			'0D':'FS20_STEP_081',
			'0E':'FS20_STEP_087',
			'0F':'FS20_STEP_093',
			'10':'FS20_STEP_100',
			'11':'FS20_On',
			'12':'FS20_Toggle',	 		# between off and previous dim val
			'13':'FS20_DimmUp',
			'14':'FS20_DimmDown',
			'15':'FS20_DimmUpDown',
			'16':'FS20_TimeSet',
			'17':'FS20_SentStatus',
			'18':'FS20_TimerOff',		# off-for-timer
			'19':'FS20_TimerOn', 		# on-for-timer
			'1A':'FS20_TimerLastValue',	# on-old-for-timer
			'1B':'FS20_Reset',
			'1C':'FS20_RAMP-ON-TIME',
			'1D':'FS20_RAMP-OFF-TIME',
			'1E':'FS20_ON-OLD-FOR-TIMER-PREV',
			'1F':'FS20_ON-100-FOR-TIMER-PREV',
			'3A':'FS20_MOTION'}

S300THdatapoint = { '0':'TEMPERATURE', '1':'HUMIDITY', '2':'RAIN', '3':'WIND', '4':'IS_RAINING'}
FS20 			= {"DC6900":"LichtKueche", "DC6901":"LichtAussenwand", "DC6902":"LichtKellerflur", "DC6903":"LichtGartentor", "DC69B0":"LichtDachHinten", "DC69B1":"LichtDachMitte", "DC69B2":"LichtDachTreppe", "536200":"Klingel1", "536201":"Klingel2", "A7A300":"Bewegung1", "557A00":"Bewegung2"}
FHT80 			= {"552D":"Multiraum", "1621":"Erdgeschoss", "0B48":"Lina", "095C":"Nico", "5A5B":"Dach"}
FHT80TF 		= {"52FB":"Multiraum", "9F63":"Kueche", "AD14":"Lina", "7D66":"Nico", "5A33":"Kellerbuero", "005E":"Kellertuere", "B79D":"Haustuere"}

try:
	from queue import Empty
except ImportError:
	from Queue import Empty

def logger(line):
	global logging
	logging.info(line)

def pt2(string):
	legal = set('.,/%°?~+-_abcdefghijklmnopqrstuvwxyz0123456789')
	s = ''.join(char if char.lower() in legal else ' ' for char in string)
	return s
	
def byte_to_time_string(value):
	seconds = 2**(ord(value) >> 4) * (ord(value) & 0x0f) * 0.25
	hours = seconds / 3600
	seconds %= 3600
	minutes = seconds / 60
	seconds %= 60
	return '%02i:%02i:%.3f' % (hours, minutes, seconds)

def parseS300TH(msg):
	msg = pt2(msg)
	firstByte = int(msg[0:2],16)	# int firstByte = Integer.parseInt(data.substring(1, 2), 16);
	typByte = int(msg[2:4+2],16)	# int typByte = Integer.parseInt(data.substring(2, 3), 16) & 7;
	sfirstByte = msg[6:6+2]			# int sfirstByte = firstByte & 7;
	#if len(msg) > 8 & len(msg) < 13): # S300TH default size = 9 characters
		
	#address = hex(int(msg[0:1],16) & 7)	

	print("S300TH:                                          raw[%s]" % (msg))
	mqtt_publish('S300TH', '{"state":%s,"raw":%s}' % (msg, ""))
	

def parseFS20(msg): #DC69-02-11-18 #DC69-00-11-1A #A7A3-00-3A-6F #557A-00-3A-6F 
	housecode = msg[0:4]	# Hauscode		 	/ device = data.substring(1, 5); 
	address = msg[4:4+2]	# Adresse (00) 		/ address = data.substring(5, 7);
	command = msg[6:6+2]	# Befehl  			/ command = data.substring(7, 9);
	argument = msg[8:8+2]	# Erweiterungbyte 	/ argument = data.substring(9, 11);
	check = msg[10:10+2]	# checksum
	splitmsg = "%s-%s-%s-%s" % (housecode, address, command, argument)
	FS20deviceID = housecode+address
	if FS20deviceID in FS20:
		FS20device = FS20[FS20deviceID]
		if command in FS20cmd:
			state = FS20cmd[command]
		else:	
			state = "unknown FS20 command"
		print("FS20:    %-10s %-10s [raw:%s]" % (FS20device, state, splitmsg))
		logger("FS20:    %-10s %-10s [raw:%s]" % (FS20device, state, splitmsg))
		mqtt_publish(FS20device, '{"state":%s,"raw":%s}' % (state, splitmsg))
	else:
		print("unknown FS20 device [raw:%s]" % (splitmsg))
		logger("unknown FS20 device [raw:%s]" % (splitmsg))


def parseFHT(msg):
	housecode = msg[0:4]	# Hauscode		 	/ device = data.substring(1, 5); // dev
	address = msg[4:4+2]	# Adresse (00) 		/ command = data.substring(5, 7); // cde
	origin = msg[6:6+2]		# Befehl  			/ origin = data.substring(7, 9); // ??
	argument = msg[8:8+2]	# Erweiterungbyte 	/ argument = data.substring(9, 11); // val
	check = msg[10:10+2]	# checksum 8bit-Summe von HC1 bis EE + Ch
	splitmsg = "%s-%s-%s-%s" % (housecode, address, origin, argument)
	#print(msg) # 7D66C00208. 095C4369000F
	
	if len(msg) == 12: # FHT80TF/Window
		# Format as follows: "TCCCCCCXX" with CCCCCC being the id of the
		# sensor in hex, XX being the current status: 02/82 is Window
		# closes, 01/81 is Window open, 0C is synchronization, ?? is the battery low warning.
		
		if housecode in FHT80TF: 
			state = "state unknown: <%s:%s>" % (origin, argument)
			if origin.startswith('1'):
				state = "FHT80TF_LOWBAT"
			if origin.startswith('9'):
				state = "FHT80TF_LOWBAT"
			if origin[1:1+1] == '1':	
				state = "FHT80TF_WINDOW_OPEN"
			if origin[1:1+1] == '2':	
				state = "FHT80TF_WINDOW_CLOSED"
			print("FHT80TF: %-12s %-29s [raw:%s]" % (FHT80TF[housecode], state, splitmsg))
			logger("FHT80TF: %-12s %-29s [raw:%s]" % (FHT80TF[housecode], state, splitmsg))
			mqtt_publish(FHT80TF[housecode], '{"state":%s,"raw":%s}' % (state, splitmsg ))
		else:
			print("unknown FHT80TF device [raw:%s]" % (splitmsg))
			logger("unknown FHT80TF device [raw:%s]" % (splitmsg))

	elif len(msg) == 14: #FHT80 #0B480026D70B
		if housecode in FHT80:
			state = "unknown state %s" % address
			if int(address,16) >= 0 & int(address,16) < 9: # FHT_ACTUATOR_0 .. FHT_ACTUATOR_8
				state = 'FHT_ACTUATOR_%s' % int(argument,16)
				value = str(round(float(int(argument,16) / 255.0) * 100,0))
			if address == '3e':
				state = 'FTH_Mode'
				value = argument
			if address == '41':
				state = 'FHT_DESIRED_TEMP'
				value = str(round(float(int(argument,16) / 2.0),0))
			if address == '42':
				state = 'FHT_MEASURED_TEMP_LOW'
				value = argument
			if address == '43':
				state = 'FHT_MEASURED_TEMP_HIGH'
				value = str(round(float(int(argument,16) * 256.0 / 10.0),0))
			if address == '82':
				state = 'FHT_DAY_TEMP'
				value = argument
			if address == '83':
				state = 'FHT_NIGHT_TEMP'
				value = argument
			if address == '85':
				state = 'FHT_WINDOWOPEN_TEMP'
				value = argument
			if address == '8a':
				state = 'FHT_LOWTEMP_OFFSET'	
				value = argument
			#tstr = byte_to_time_string(argument)
			print("FHT80:   %-12s %-22s %-6s [raw:%s]" % (FHT80[housecode], state, value, splitmsg))
			logger("FHT80:   %-12s %-22s %-6s [raw:%s]" % (FHT80[housecode], state, value, splitmsg))
			mqtt_publish(FHT80[housecode], '{"state":%s,"value":%s,"raw":%s}' % (state, value, splitmsg))
		else:
			print("unknown FHT80 device [raw:%s]" % (splitmsg))
			logger("unknown FHT80 device [raw:%s]" % (splitmsg))
	else:
		print("unknown device [raw:%s] %s" % (splitmsg, len(msg)))
		logger("unknown device [raw:%s] %s" % (splitmsg, len(msg)))

def culDecode(msg):
	rawmsg = msg[1: len(msg)+1]
	if msg.startswith('F'):
		parseFS20(rawmsg)
	elif msg.startswith('T'):
		parseFHT(rawmsg)
	elif msg.startswith('K'):
		parseS300TH(rawmsg)
	elif msg == "LOVF": # no send time available anymore
		print("No fs20 send time available");
		logger("No fs20 send time available");
	else:
		print("CUL received: " + msg)
		logger("CUL received: " + msg)

class CULManager(Process):

	def __init__(self, device, **kwargs):
		settings = dict()
		settings['baudrate'] = 9600
		settings['bytesize'] = serial.EIGHTBITS
		settings['parity'] = serial.PARITY_NONE
		settings['stopbits'] = serial.STOPBITS_ONE
		settings['timeout'] = 0.0005
		settings.update(kwargs)
		self._kwargs = settings
		self.ser = serial.Serial(device, **self._kwargs)
		self.in_queue = Queue()
		self.out_queue = Queue()
		self.closing = False # A flag to indicate thread shutdown
		self.read_num_bytes  = 128
		self.sleeptime = None
		print("initializing CUL ...")	
		self.ser.write(b'V\r\n') # init CUL
		time.sleep(1)
		self.ser.write(b'X21\r\n') # init CUL
		#print(" done.")	
		Process.__init__(self, target=self.loop)

	def loop(self):
		try:
			while not self.closing:
				if self.sleeptime: time.sleep(self.sleeptime)
				in_data = self.ser.read(self.read_num_bytes)
				if in_data:
					self.in_queue.put(in_data)
				try:
					out_buffer = self.out_queue.get_nowait()
					self.ser.write(out_buffer)
				except Empty:
					pass
		except (KeyboardInterrupt, SystemExit):
			pass
		print("closing CUL ...")	
		self.ser.write(b'X00\r\n') # close CUL
		self.ser.close()

	def close(self):
		self.closing = True

def mqtt_publish(topic, value):
	t = "smarthome/cul/device/%s" % (topic)
	mqtt_smarthome.publish(t, value) 

def on_message(client, userdata, msg):
	global s1
	print("Topic: %s - Message: %s" % (msg.topic, str(msg.payload)))
	logger("Topic: %s - Message: %s" % (msg.topic, str(msg.payload)))
	s1.ser.write(msg.payload)

def main():
	import argparse
	parser = argparse.ArgumentParser(description='A class to manage reading and writing from and to a serial port.')
	parser.add_argument('--timeout', '-t', type=float, default=0.0005, help='Seconds until reading from serial port times out [default: 0.0005].')
	parser.add_argument('--sleeptime', '-s', type=float, default=None, help='Seconds to sleep before reading from serial port again [default: none].')
	parser.add_argument('--baudrate', '-b', type=int, default=9600, help='Baudrate of serial port [default: 9600].')
	parser.add_argument('device', help='The serial port to use (COM4, /dev/ttyACM0 or similar).')
	args = parser.parse_args()

	s1 = CULManager(args.device, baudrate=args.baudrate, timeout=args.timeout)
	s1.sleeptime = args.sleeptime
	s1.read_num_size = 128
	s1.start()

	# loop forever ...
	try:
		while (True):
			cul_raw_message = s1.in_queue.get()
			#print(type(cul_raw_message))
			msg = binascii.b2a_qp(cul_raw_message)
			culDecode(msg.decode('utf-8'))
	except KeyboardInterrupt:
		s1.close()
	finally:
		s1.close()
	s1.join()


if __name__ == "__main__":		
	logging.basicConfig(format='%(asctime)-6s: - %(message)s', level=logging.DEBUG, filename="cul.log")

	# create the MQTT mqtt_smarthome
	mqtt_smarthome = paho.Client()
	if (MQTT_TLS == "True"):
		print("connecting using tls to smarthome")
		#mqtt_smarthome.tls_set(MQTT_CACERT)
		mqtt_smarthome.tls_set(ca_certs="/home/smarthome/.ssh/ca.crt")
		#mqtt_smarthome.tls_insecure_set(True)     # prevents error - ssl.SSLError: Certificate subject does not match remote hostname.
		
	#mqtt_smarthome.on_connect 	= on_connect
	#mqtt_smarthome.on_log		= on_log
	mqtt_smarthome.on_message 	= on_message

	mqtt_smarthome.username_pw_set(username=MQTT_USER,password=MQTT_PASSWD)
	mqtt_smarthome.connect(MQTT_SERVER, int(MQTT_PORT), 60)

	main()

	mqtt_smarthome.disconnect()
