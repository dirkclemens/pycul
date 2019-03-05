#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Idea and parts taken from:
#   http://www.fhemwiki.de/wiki/FHT80b
#   http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
#   http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol
#   https://www.elv.at/downloads/faq/2013-05-27_Interne_Bezeichnungen_FS20-Befehlcodes.pdf
#   https://www.elv.de/CUxD-–-das-Leatherman-für-die-Homematic®-CCU-Teil-2/x.aspx/cid_726/detail_50052
#   https://github.com/adlerweb/asysbus/blob/master/tools/mqtt-proxy.py
#   https://github.com/hobbyquaker/cul
#   https://github.com/HJvA/fshome
#   https://github.com/HJvA/fshome/blob/master/accessories/fs20/fs20_cul.py
#   https://github.com/helpsterTee/cul-hass-mqtt
#
# Requires:
#   pip3 install asyncio --user
#   pip3 install aiomqtt  --user (+ paho-mqtt)
#   pip3 install pyserial-asyncio --user
#
# Test:
#   mosquitto_pub -h "192.168.2.36" -p 1883 -u "***" -P "***" -t "/smarthome/cul/to/FDC69B1" -m "on-for-timer 120"
#

import os
import sys
from time import strftime, localtime
import time
import binascii
import asyncio
import serial_asyncio
import aiomqtt
from functools import partial
import re

cul_port            = '/dev/ttyACM1'
cul_baud            = 9600
mqtt_server         = '192.168.2.36'
mqtt_port           = 1883
mqtt_SubscribeTopic = 'smarthome/cul/to/#'
mqtt_PublishTopic   = 'smarthome/cul/from/'
mqtt_user           = '***'
mqtt_pass           = '***'
mqtt_ca             = ''

if not os.path.exists(cul_port):
	print('Serial port does not exist')
	sys.exit(1)

################################################################################
# defines 
################################################################################
FS20 			= {"DC6900":"LichtKueche", "DC6901":"LichtAussenwand", "DC6902":"LichtKellerflur", "DC6903":"LichtGartentor", "DC69B0":"LichtDachHinten", "DC69B1":"LichtDachMitte", "DC69B2":"LichtDachTreppe", "536200":"Klingel1", "536201":"Klingel2", "A7A300":"Bewegung1", "557A00":"Bewegung2", "EEEF00":"FS20S8M_1", "EEEF01":"FS20S8M_2", "EEEF02":"FS20S8M_3"}
FHT80 			= {"552D":"Multiraum", "1621":"Erdgeschoss", "0B48":"Lina", "095C":"Nico", "5A5B":"Dach"}
FHT80TF 		= {"52FB7B":"Multiraum", "9F63ED":"Kueche", "AD141B":"Lina", "7D66C0":"Nico", "5A3392":"Kellerbuero", "005E4F":"Kellertuere", "B79DA0":"Haustuere"}

################################################################################
# FS20 
################################################################################
fs20codes = [
  "off",   
  "dim06%", "dim12%", "dim18%", "dim25%", "dim31%", "dim37%", "dim43%", "dim50%", "dim56%",
  "dim62%",  "dim68%","dim75%", "dim81%", "dim87%", "dim93%", "dim100%",   
  "on",     # Set to previous dim value (before switching it off)
  "toggle", # between off and previous dim val
  "dimup",   "dimdown",   "dimupdown",
  "timer",
  "sendstate",
  "off-for-timer",   "on-for-timer",   "on-old-for-timer",
  "reset",
  "ramp-on-time",      #time to reach the desired dim value on dimmers
  "ramp-off-time",     #time to reach the off state on dimmers
  "on-old-for-timer-prev", # old val for timer, then go to prev. state
  "on-100-for-timer-prev" # 100% for timer, then go to previous state
]

################################################################################
# CUL Stick - serial asyncIO interface
################################################################################
class culRxTx(asyncio.Protocol):
	def __init__(self, queueRX, queueTX):
		super().__init__()
		self.transport = None
		self.buf = None
		self.queueRX = queueRX
		self.queueTX = queueTX


	def connection_made(self, transport):
		self.transport = transport
		self.buf = bytes()
		print('CUL serial port opened:\r\n', transport)

		# initialize CUL
		#self.transport.serial.write(b'V\r\n')
		#asyncio.sleep(1.0)
		#self.transport.serial.write(b'X21\r\n')
		print('CUL init done.')

		# start receiving loop
		asyncio.ensure_future(self.send())
		#print('starting loop')


	def data_received(self, data):
		#print ('data_received')
		self.buf += binascii.b2a_qp(data)
		if b'\n' in self.buf:
			lines = self.buf.split(b'\n')
			self.buf = lines[-1] # whatever was left over
			for line in lines[:-1]:
				#print(line.strip().decode('ascii'))
				#asyncio.ensure_future(self.queueRX.put(line))
				message = line.strip().decode('ascii')
				topic = message[0:7] # house code + device addr
				asyncio.ensure_future(mqttTxQueue.put([topic, message, True]))
		# Reset the data_buffer!
		#self.buf = b''


	def sendFS20(self, msg, cmd='toggle', dur=None):
		if (msg[0] == 'F'):
			hausc   = msg[1:5] # FS20-Hauscode	DC69
			devadr  = msg[5:7] # FS20-Adresse	B1
			#dur     = None
			#cmd     = "toggle"
			#cde     = 18 # toggle, dezimal
			cde 		= fs20codes.index(cmd)
			ee		= ""
			if not dur is None:
				cde |= 0x20
				for i in range(0,12):
					if len(ee)==0:
						for j in range(0,15):
							val = (2**i)*j*0.25
							if val >= int(dur):
								ee = "%0.2X" % (i*16+j,)
								break
			cmd = "%0.2X" % cde
			rawmsg = str('F'+hausc+devadr+cmd+ee+'\r\n').encode(encoding='utf-8', errors='strict')
			print("CUL:     sending FS20 cmd to CUL: %s (%x) dur:%s to hc:%s adr:%s [raw:%s]" % (cmd,cde,ee,hausc,devadr,rawmsg))
			self.transport.serial.write(rawmsg)
		else: # not 'F'
			print ('CUL:     unknown device code %s' % (msg, ))    
 
 
	def sendFHT(self, msg, cmd, subcmd):
		if (msg[0] == 'T'):
			pass
		else: # not 'T'
			print ('CUL:     unknown device code %s' % (msg, ))    


	async def send(self):
		""" sends a terminated string to the device """
		# data = bytes(msg+terminate, 'ascii')
		while True:
			rawmsg = await self.queueTX.get()
			msg,rawcmd = rawmsg.split('=')
			subcmd 	= ''
			cmd		= rawcmd
			if ' ' in rawcmd: # if cmd contains two parts
				cmd,subcmd = rawcmd.split(' ')
			#print('msg:%s >>>> cmd:%s >>>subcmd:%s' % (msg,cmd,subcmd))

			if msg[0] in ['F','l','T','t','V','X','#']:
				if (msg[0] == 'V'):
					print('CUL:     sending V')
					self.transport.serial.write(b'V\r\n')
				if (msg[0] == 'X'):
					print('CUL:     sending raw %s' % rawcmd)
					self.transport.serial.write(bytes('%s\r\n' % (rawcmd, ), 'ascii'))
				if (msg[0] == 'l'): # l00: an, l01: aus, l02: blink
					print('CUL:     sending raw %s' % rawcmd)
					self.transport.serial.write(bytes('%s\r\n' % (rawcmd, ), 'ascii'))
				if (msg[0] == 'F'):
					#print('CUL:     sending to FS20 %s' % (msg, ))
					self.sendFS20(msg,cmd,subcmd)
				if (msg[0] == 'T'):
					#print('CUL:     sending to FHT %s' % (msg, ))
					self.sendFHT(msg,cmd,subcmd)
				if (msg[0] == '#'):
					#https://webkul.com/blog/string-and-bytes-conversion-in-python3-x/
					rawmsg = str(msg[1:]+'\r\n').encode(encoding='utf-8', errors='strict')
					print('CUL:     sending raw %s' % rawmsg)
					self.transport.serial.write(rawmsg) # ab Zeichen 1, also ohne das #
			else: 
				print ('CUL:     sending unknown code %s' % (msg, ))    


	def connection_lost(self, exc):
		print('CUL serial port closed.')
		self.transport.serial.write(b'X00\r\n') # close CUL
		asyncio.get_event_loop().stop()
		# the value passed to set_result will be transmitted to
		# run_until_complete(protocol.wait_connection_lost()).
		#self.__done.set_result(None)


	def eof_received(self):
		print("eof_received")
		return True


	def write_data(self):
		print("write_data")
		self.transport.serial.write(self.message)


	# When awaited, resumes execution after connection_lost()
	# has been invoked on this protocol.
	def wait_connection_lost(self):
		print('wait_connection_lost')
		self.transport.serial.write(b'X00\r\n') # close CUL
		return self.__done


################################################################################
# decoding messages from CUL 
################################################################################
def clrstr(string):
	legal = set('.,/%°?~+-_abcdefghijklmnopqrstuvwxyz0123456789')
	s = ''.join(char if char.lower() in legal else ' ' for char in string)
	return s

# from fhem: 14_CUL_WS.pm
def parseS300TH(msg, rssi):
	typbyte = int(msg[2],16) & 7
	if len(msg)>=15:
		print("\tKS300 not implemented")
	elif len(msg)>8:	# AND typbyte == 1 ---> temp/hum
		firstByte = int(msg[0],16)
		sgn = firstByte & 8 
		cde = (firstByte & 7) + 1
		typ = int(msg[1])	# will be 1
		temperature= float(msg[5] + msg[2] + "." + msg[3]) 	# + $hash->{corr1}
		if sgn != 0:
			temperature *= -1
		humidity = float(msg[6] + msg[7] + "." + msg[4])	# + $hash->{corr2}
		print("S300TH:  %-17s T:%-4s H:%-20s [raw:%s]    (rssi:%s)" % (cde, temperature, humidity, clrstr(msg), rssi))


# from fhem: 10_FS20.pm
# http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol
def parseFS20(msg, rssi):
								# FDC690200
								# FHHHHAABBTTRR
	housecode	= msg[0:4]		# HHHH FS20-Hauscode
	address		= msg[4:4+2]	# AA   FS20-Adresse
	command		= msg[6:6+2]	# BB   FS20-Befehl
	argument		= msg[8:8+2]	# TT   FS20-Timer Erweiterungbyte
	splitmsg		= "   %s-%s-%s" % (housecode, address, command)
	if len(argument)>0:
		splitmsg		= "%s-%s-%s-%s" % (housecode, address, command, argument)
	FS20deviceID = housecode+address
	
	cx  = int(command,16) # hex to int
	cde 		= ' '
	to 		= '        ' # placeholder only
	if (cx & 0x20) and len(argument)>0:  # Timed command
		dur	= int(argument, 16) 	# eigentlich "check"
		i 	= (dur & 0xf0)/16;
		j 	= (dur & 0xf)
		dur = (2**i)*j*0.25;
		cde = "%0.2X" % (cx & ~0x20)
		to  = ('%02d:%02d:%02d' % (dur/3600, (dur%3600)/60, dur%60))
		#command:56 - i:0.0 - j:11 - dur:2.75 - cde:18 - to:00:00:02
		#command:38 (38) - i:0.0 - j:7 - dur:1.75 - cde:18 - to:00:00:01
		#FS20:    FS20S8M_1         unknown command 56   00:00:01 [raw:EEEF-00-38-AF] (rssi:-70.5) FEEEF0038AF07
		print('\t\t\t   command:%s (%0.2X) - i:%s - j:%s - dur:%s - cde:%s - to:%s' % (command, cx, i, j, dur, cde, to))

	if FS20deviceID in FS20:
		FS20device = FS20[FS20deviceID]
		state = "unknown command %s" % cx
		try:	
			state = fs20codes[cx].upper()
			pass
		except Exception as e:
			pass
		print("FS20:    %-17s %-22s %-15s [raw:%s] (rssi:%s) F%s" % (FS20device, state, to, splitmsg, rssi, clrstr(msg)))
	else:
		print("unknown FS20 device [raw:F%s]" % (splitmsg))

fhtcodes = { 
  "00":"actuator", "01":"actuator1", "02":"actuator2", "03":"actuator3", "04":"actuator4", "05":"actuator5", "06":"actuator6", "07":"actuator7", "08":"actuator8",
  "14":"mon-from1", "15":"mon-to1", "16":"mon-from2", "17":"mon-to2", "18":"tue-from1", "19":"tue-to1", "1A":"tue-from2", "1B":"tue-to2", "1C":"wed-from1", "1D":"wed-to1", "1E":"wed-from2", "1F":"wed-to2", "20":"thu-from1", "21":"thu-to1", "22":"thu-from2", "23":"thu-to2", "24":"fri-from1", "25":"fri-to1", "26":"fri-from2", "27":"fri-to2", "28":"sat-from1", "29":"sat-to1", "2A":"sat-from2", "2B":"sat-to2", "2C":"sun-from1", "2D":"sun-to1", "2E":"sun-from2", "2F":"sun-to2",
  "3E":"mode",
  "3F":"holiday1",		# Not verified
  "40":"holiday2",		# Not verified
  "41":"desired-temp", "XX":"measured-temp",		# sum of next. two, never really sent
  "42":"measured-low", "43":"measured-high", "44":"warnings", "45":"manu-temp",	# No clue what it does.
  "4B":"ack", "53":"can-xmit", "54":"can-rcv",
  "60":"year", "61":"month", "62":"day", "63":"hour", "64":"minute", "65":"report1", "66":"report2", "69":"ack2", "7D":"start-xmit", "7E":"end-xmit",
  "82":"day-temp", "84":"night-temp",
  "85":"lowtemp-offset",         # Alarm-Temp.-Differenz
  "8A":"windowopen-temp" 
}
# from fhem: 11_FHT.pm
# from http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
fht_measured_low  = -1
def parseFHT(msg, rssi):
	global fht_measured_low
	device	 	= msg[0:4]		# Hauscode		 	/ my $dev = substr($msg, 16, 4);
	cde 			= msg[4:4+2]	# Kommando (00) 	/ my $cde = substr($msg, 20, 2);
	origin 		= msg[6:6+2]	# Befehl  			/ 22
	val 			= msg[8:8+2]	# Erweiterungbyte 	/ 24
	check 		= msg[10:10+2]	# checksum 8bit-Summe von HC1 bis EE + Ch # 26
	splitmsg 	= "%s-%s-%s-%s" % (device, cde, origin, val)
	if len(msg)>10:
		splitmsg 	= "%s-%s-%s-%s-%s" % (device, cde, origin, val, check)
	dec_val		= int(val,16)
	confirm		= 0
	fht_measured_high = -1
	'''
	FHT80:   Lina         FHT_ACTUATOR_81        32.0   [raw:0B48-00-A6-51]
	FHT80:   Lina         FHT_MEASURED_TEMP_LOW  D4     [raw:0B48-42-69-D4]
				 unknown FHT state 3E   00              [raw:0B48-3E-69-00] 
	FHT80:   Multiraum    FHT_ACTUATOR_42        16.0   [raw:552D-00-A6-2A]
	'''
	if device in FHT80:
		if cde in fhtcodes:
			state = 'FTH_'+fhtcodes[cde].upper()
		else:
			state = "unknown FHT state %s" % cde
		value = val

		if int(cde,16) >= 0 and int(cde,16) < 9: # FHT_ACTUATOR_0 .. FHT_ACTUATOR_8
			fv = "%d%%" % int(100*dec_val/255 + 0.5)
			value = fv
			sval  = val[1:1].upper()
			if sval == '0':
				value = 'SYNCNOW'
			if sval == '1':
				value = '99%'
			if sval == '2':
				value = '0%'
			if sval == '8':
				if dec_val>128:
					value = 'OFFSET: %s' % (128-dec_val)
				else:
					value = 'OFFSET: %s' % dec_val  
			if val == '2A' or val == '3A':
				value = 'LIME-PROTECTION'
			if sval == 'C':
				value = 'SYNCTIME: %f' % int(dec_val/2-1)
			if sval == 'E':
				value = 'TEST'
			if sval == 'F':
				value = 'PAIR'

		if int(cde,16) > 19 and int(cde,16) < 48: # 0x14 - 0x2f --> -from and -to
			value = ("%02d:%02d" % (dec_val/6, (dec_val%6)*10))

		if cde == '3E': # FTH_Mode
			fhtmodes = ["AUTO", "MANUAL", "HOLIDAY", "HOLIDAY_SHORT"]
			if dec_val >= 0 and dec_val < 4:
				value = 'MODE: %s' % fhtmodes[dec_val].upper()
			else:
				value = 'UNKNOWN MODE'

		if cde == '41': # FHT_DESIRED_TEMP
			value = str(round(float(dec_val / 2.0), 0))
			if value > 30: 
				value = "ON"
			if value < 6: 
				value = "OFF"

		if cde == '42': # FHT_MEASURED_TEMP_LOW
			fht_measured_low  = dec_val
			return 0
		if cde == '43': # FHT_MEASURED_TEMP_HIGH
			# special treatment for measured-temp which is actually sent in two bytes
			# measured-temp= (measured-high * 256 + measured-low) / 10.
			if fht_measured_low>=0:
				state = 'FHT_MEASURED_TEMP'
				value = str(round(float((dec_val * 256.0 + fht_measured_low) / 10.0), 0))
				fht_measured_low  = -1 

		if cde == '44': # parse warnings
			nVal = ''
			if (dec_val & 1):
				nVal  = "BATTERY LOW "
			if(dec_val & 2):
				nVal += "TEMPERATURE TOO LOW "
			if(dec_val & 32):
				nVal += "WINDOW OPEN "
			if(dec_val & 16):
				nVal += "FAULT ON WINDOW SENSOR";
			value = nVal

		if cde == '65' or cde == '66':
			state = ('FHT_REPORT%s %s' % (int(cde)-64, origin))
			confirm = 1

		if cde == '45': #"manu-temp"
			value = "%.1f" % dec_val / 2
		if cde == '82': #"day-temp"
			value = "%.1f" % dec_val / 2
		if cde == '84': #"night-temp"
			value = "%.1f" % dec_val / 2
		if cde == '85': #"lowtemp-offset"
			value = "%d.0" % dec_val
		if cde == '8A': #"windowopen-temp"
			value = "%.1f" % dec_val / 2

		print("FHT80:   %-17s %-22s %-15s [raw:%s] (rssi:%s) T%s" % (FHT80[device], state, value, splitmsg, rssi, clrstr(msg)))
	else:
		print("\t unknown FHT80 device [raw:%s] (rssi:%s) T%s" % (splitmsg, rssi, clrstr(msg)))


# from fhem: 09_CUL_FHTTK.pm
# from http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
def parseFHTTK(msg, rssi):
	sensor 		= msg[0:6]		# my $sensor= lc(substr($msg, 1, 6));
	state 		= msg[6:8]		# my $state = lc(substr($msg, 7, 2));
	splitmsg 	= "%9s-%s" % (sensor, state)
	# from 09_CUL_FHTTK.pm -> %fhttfk_codes
	# Format as follows: "TCCCCCCXX" with CCCCCC being the id of the sensor in hex, 
	# if 1st char of XX is 0 or 8 then Battery:ok
	# if 1st char of XX is 1 or 9 then Battery:low
	# if 2nd char of XX is 0 then Window:Closed
	# if 2nd char of XX is 1 then Window:Open
	# if 2nd char of XX is c then Sync:Syncing
	# if 2nd char of XX is f then Test:Success
	if sensor in FHT80TF: 
		state = state.upper()
		value = "FHT80TF - state unknown: <%s>" % (state)
		if state.endswith('1'):
			value = "FHT80TF_WINDOW_OPEN"
		if state.endswith('2'):
			value = "FHT80TF_WINDOW_CLOSED"
		if state.endswith('C'):
			value = "FHT80TF_SYNCING"
		if state.endswith('F'):
			value = "FHT80TF_TEST_SUCCESS"
		if state.startswith('1'):
			value += "_LOWBAT"
		if state.startswith('9'):
			value += "_LOWBAT"
		print("FHT80TF: %-17s %-38s [raw: %s] (rssi:%s) T%s" % (FHT80TF[sensor], value, splitmsg, rssi, clrstr(msg)))
	else:
		print("\t unknown FHT80TF device [raw:%s] (rssi:%s) T%s" % (splitmsg, rssi, clrstr(msg)))


# from fhem: 00_CUL.pm
def culDecode(msg):
	rawmsg = msg[1:len(msg)+1]

	#if($dmsg =~ m/^[AFTKEHRStZrib]([A-F0-9][A-F0-9])+$/) { # RSSI
	dmsg = re.match('^[AFTKEHRStZribXV]([A-F0-9][A-F0-9])+$', msg)
	if dmsg: # calculate rssi values
		rssi		= int(msg[-2:],16)
		if rssi >= 128: 
			rssi = (rssi-256)/2-74
		rssi 	= (rssi/2)-74
	else:
		rssi 	= '   na'

	# decode first char, select device type 
	if msg.startswith('X'):			# credit10ms
		dmsg = re.match('^.. *\d*[\r\n]*$', msg)
		if dmsg:
			print('CUL:\t CREDIT10MS: %s' % (dmsg,))

	if msg.startswith('V'):			# Version
		print('CUL:\t %s' % msg)

	if msg.startswith('F'):			# FS20
		parseFS20(rawmsg, rssi)

	elif msg.startswith('T'):
		if len(rawmsg) > 9 and len(rawmsg) < 13:	# FHT80
			parseFHT(rawmsg, rssi)
		elif len(rawmsg) < 9 :			# FHT80TF/Window
			parseFHTTK(rawmsg, rssi)
		else:
			print("\t unknown device [raw:%s] (rssi:%s) T%s (%s)" % (rawmsg, rssi, clrstr(rawmsg), len(rawmsg)))

	elif msg.startswith('K'):		# S300TH
		parseS300TH(rawmsg, rssi)

	elif msg.startswith('H'): 		# HMS
		print('HMS [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('i'): 		# Intertechno
		print('Intertechno [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('r'): 		# Revolt
		print('Revolt [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('Y'): 		# SOMFY RTS
		print('SOMFY RTS [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('S'): 		# CUL_ESA / ESA2000 / Native
		print('CUL_ESA [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('E'): 		# CUL_EM / Native
		print('CUL_EM [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('R'): 		# CUL_HOERMANN / Native
		print('CUL_HOERMANN [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('A'): 		# AskSin/BidCos/HomeMatic
		print('AskSin/BidCos/HomeMatic [%s] (%s)' % (rawmsg, rssi))

	elif msg.startswith('Z'): 		# Moritz/Max
		print('Moritz/Max [%s] (%s)' % (rawmsg, rssi))

	elif msg == "LOVF": # no send time available anymore
		print("CUL:\t no send time available\t\t\t [raw:%s]" % msg);
	else:
		dmsg = re.match('^[0-9A-F]{8}[\r\n]*$', msg)
		if dmsg: 
			dmsg = int(dmsg.group(0),16)
			print('CUL:\t UPTIME\t\t   %d %02d:%02d:%02d' % (dmsg/86400, (dmsg%86400)/3600, (dmsg%3600)/60, dmsg%60))
		else:
			print("CUL:\t received: %s" % str(msg))

################################################################################
# MQTT interface
################################################################################
async def mqtt(mqttTxQueue, canTxQueue, server, port, user, passwd, ca):
	client = aiomqtt.Client(loop)
	client.loop_start()

	connected = asyncio.Event(loop=loop)
	def on_connect(client, userdata, flags, rc):
		connected.set()
	client.on_connect = on_connect

	client.will_set(mqtt_PublishTopic + 'LWT', 'OFF', 0, False)
	if ca:
		client.tls_set(ca);
	if user and passwd:
		client.username_pw_set(user, passwd)
	
	try:
		await client.connect(server, port)
		await connected.wait()
		print("MQTT connected")
	except ConnectionRefusedError as e:
		print(e)
		await client.loop_stop()
		print("MQTT loop stopped!")
		sys.exit(-1)    

	subscribed = asyncio.Event(loop=loop)
	def on_subscribe(client, userdata, mid, granted_qos):
		subscribed.set()
	client.on_subscribe = on_subscribe

	client.subscribe(mqtt_SubscribeTopic)
	await subscribed.wait()
	print("MQTT Subscribed to " + mqtt_SubscribeTopic)

	def on_message(client, userdata, msg):
		# von MQTT an CUL
		payload	= str(msg.payload, 'utf-8') # decode byte to string
		device 	= msg.topic.rsplit('/', 1)[-1] # cut device part from topic
		print("MQTT RX: Topic: %-35s >> Message: %-20s [%s]" % (device, payload, bool(msg.retain)))
		asyncio.ensure_future(culTxQueue.put(device+'='+payload))

	client.on_message = on_message

	lwtPublish = client.publish(mqtt_PublishTopic + "LWT", 'ON')
	await lwtPublish.wait_for_publish()
	print("MQTT LWT published!")

	while True:
		msg = await mqttTxQueue.get()
		try:		# von CUL an MQTT
			msgPublish = client.publish(mqtt_PublishTopic + msg[0], msg[1], retain=msg[2])
			await msgPublish.wait_for_publish()
			#print("MQTT TX: Topic: %-35s >> Message: %-20s [%s]" % (msg[0], str(msg[1]), str(msg[2])))			
			culDecode(str(msg[1]))
		except IndexError:
			print("MQTT publish failed: \t%s" % (msg, ))


################################################################################
# init
################################################################################
culRxQueue = asyncio.Queue()
culTxQueue = asyncio.Queue()
mqttTxQueue = asyncio.Queue()
culPartial = partial(culRxTx, culRxQueue, culTxQueue)

loop = asyncio.get_event_loop()
#   serial_asyncio.create_serial_connection(loop, protocol_factory, *args, **kwargs)
#   loop – The event handler
#   protocol_factory – Factory function for a asyncio.Protocol
culSAIO = serial_asyncio.create_serial_connection(loop, culPartial, cul_port, baudrate=cul_baud)
asyncio.ensure_future(culSAIO)
asyncio.ensure_future(mqtt(mqttTxQueue, culTxQueue, mqtt_server, mqtt_port, mqtt_user, mqtt_pass, mqtt_ca))

loop.run_forever()
loop.close()

