#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Idea and parts taken from:
#   https://www.elv.at/downloads/faq/2013-05-27_Interne_Bezeichnungen_FS20-Befehlcodes.pdf
#   https://github.com/adlerweb/asysbus/blob/master/tools/mqtt-proxy.py
#   https://github.com/hobbyquaker/cul
#   https://github.com/HJvA/fshome
#   https://github.com/HJvA/fshome/blob/master/accessories/fs20/fs20_cul.py
#   http://www.fhemwiki.de/wiki/FHT80b
#   http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
#   http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol
#
# Requires:
#   pip3 install asyncio --user
#   pip3 install aiomqtt  --user (+ paho-mqtt)
#   pip3 install pyserial-asyncio --user
#
# Test:
#   mosquitto_pub -h "192.168.2.36" -p 1883 -u "*****" -P "*****" -t "/smarthome/cul/device/1" -m "DC69B111E9"
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

cul_port            = '/dev/ttyACM1'
cul_baud            = 9600
mqtt_server         = '192.168.2.36'
mqtt_port           = 1883
mqtt_SubscribeTopic = 'smarthome/cul/to/#'
mqtt_PublishTopic   = 'smarthome/cul/from/'
mqtt_user           = '*****'
mqtt_pass           = '*****'
mqtt_ca             = ''

if not os.path.exists(cul_port):
    print('Serial port does not exist')

################################################################################
# defines 
################################################################################
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
FS20 			= {"DC6900":"LichtKueche", "DC6901":"LichtAussenwand", "DC6902":"LichtKellerflur", "DC6903":"LichtGartentor", "DC69B0":"LichtDachHinten", "DC69B1":"LichtDachMitte", "DC69B2":"LichtDachTreppe", "536200":"Klingel1", "536201":"Klingel2", "A7A300":"Bewegung1", "557A00":"Bewegung2", "EEEF00":"FS20S8M_1", "EEEF01":"FS20S8M_2", "EEEF02":"FS20S8M_3"}
FHT80 			= {"552D":"Multiraum", "1621":"Erdgeschoss", "0B48":"Lina", "095C":"Nico", "5A5B":"Dach"}
FHT80TF 		= {"52FB":"Multiraum", "9F63":"Kueche", "AD14":"Lina", "7D66":"Nico", "5A33":"Kellerbuero", "005E":"Kellertuere", "B79D":"Haustuere"}

################################################################################
# FS20 
################################################################################
fs20commands = [
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
        self.transport.serial.write(b'X21\r\n')
        print('CUL init done.')

        # start receiving loop
        asyncio.ensure_future(self.send())
        print('starting loop')

        #self.transport.serial.write(b'FDC69B111E9\r\n')
        # FDC69B1120B Licht Dach Mitte toggle
        # FDC69B111E9 Licht Dach Mitte on
        # FDC69B100EC Licht Dach Mitte off
        # FDC69B21103 Licht Dach Treppe on
        # FDC69B20003 Licht Dach Treppe off

    
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
                topic = message[0:5]
                asyncio.ensure_future(mqttTxQueue.put([topic, message, True]))
        # Reset the data_buffer!
        #self.buf = ''

    def sendFS20(self, msg):
        if (msg[0] == 'F'):
            hausc   = msg[1:5] #"DC69"
            devadr  = msg[5:7] #"B1"
            dur     = 1
            cde     = 18 # toggle, dezimal
            ee      = ""
            try:
                #cde = int(msg[7:9])
                cde = int(msg[7:9], 16)
                pass
            except Exception as e:
                pass
            #print (cde)    
            # Calculating the time.
            if not dur is None:
                cde |= 0x20 # Set the extension bit
                for i in range(0,12):
                    if len(ee)==0:
                        for j in range(0,15):
                            val = (2**i)*j*0.25
                            if val >= dur:
                                #ee = '%0.2X' % (i*16+j,)
                                ee = '%X%X' % (i,j)
                                break
            cmd = '%0.2X' % (cde,)
            print("CUL:     sending FS20 cmd to CUL: %s (%x) dur:%s to hc:%s adr:%s" % (cmd,cde,ee,hausc,devadr))
            #self.transport.serial.write(bytes('F'+hausc+devadr+cmd+ee, 'ascii'))
            #self.transport.serial.write(b'FDC69B11205\r\n')
        else: # not 'F'
            print ('CUL:     unknown device code %s' % (msg, ))    
 
 
    def sendFHT(self, msg):
        if (msg[0] == 'T'):
            pass
        else: # not 'T'
            print ('CUL:     unknown device code %s' % (msg, ))    


    async def send(self):
        while True:
            msg = await self.queueTX.get()
            #if msg[0] in 'AFTKEHRStZrib':	# known cul messages
            if msg[0] in ['A','a','B','b','C','c','D','d','E','e','F','f','G','H','I','i','M','N','l','O','o','P','q','R','s','T','t','U','u','V','v','W','w','X','Y','Z','#']:
                if (msg[0] == 'V'):
                    print('CUL:     sending V')
                    self.transport.serial.write(b'V\r\n')
                if (msg[0] == 'X'):
                    print('CUL:     sending raw %s' % msg)
                    self.transport.serial.write(bytes('%s\r\n' % (msg, ), 'ascii'))
                if (msg[0] == 'F'):
                    print('CUL:     sending to FS20 %s' % (msg, ))
                    self.sendFS20(msg)
                if (msg[0] == 'T'):
                    print('CUL:     sending to FHT %s' % (msg, ))
                    self.sendFHT(msg)
                if (msg[0] == '#'):
                    print('CUL:     sending raw %s' % msg)
                    self.transport.serial.write(bytes('%s\r\n' % (msg[1:], ), 'ascii')) ## ab Zeichen 1, also ohne das #
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

def parseS300TH(msg, rssi):
    if len(msg)>=15:
        print("\tKS300 not implemented")
    elif len(msg)>8:
        firstByte = int(msg[0],16)
        sgn = firstByte & 8 
        cde = (firstByte & 7) + 1
        typ = int(msg[1])	# will be 1
        temperature= float(msg[5] + msg[2] + "." + msg[3])
        if sgn != 0:
            temperature *= -1
        humidity = float(msg[6] + msg[7] + "." + msg[4])		
        print("S300TH:  %-17s T:%-4s H:%-20s [raw:%s] (rssi:%s)" % (cde, temperature, humidity, clrstr(msg), rssi))


def parseFS20(msg, rssi): #DC69-02-11-18 #DC69-00-11-1A #A7A3-00-3A-6F #557A-00-3A-6F 
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
            state = "\t unknown FS20 command"
        print("FS20:    %-17s %-22s  [raw:%s] (rssi:%s) %s" % (FS20device, state, splitmsg, rssi, clrstr(msg)))
    else:
        print("\t unknown FS20 device [raw:%s]" % (splitmsg))


def parseFHT(msg, rssi):
    housecode = msg[0:4]	# Hauscode		 	/ device = data.substring(1, 5); // dev
    address = msg[4:4+2]	# Adresse (00) 		/ command = data.substring(5, 7); // cde
    origin = msg[6:6+2]		# Befehl  			/ origin = data.substring(7, 9); // ??
    argument = msg[8:8+2]	# Erweiterungbyte 	/ argument = data.substring(9, 11); // val
    check = msg[10:10+2]	# checksum 8bit-Summe von HC1 bis EE + Ch
    splitmsg = "%s-%s-%s-%s" % (housecode, address, origin, argument)
    #print(msg) # 7D66C00208. 095C4369000F

    if len(msg) == 10: # FHT80TF/Window
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
            print("FHT80TF: %-17s %-29s [raw:%s] (rssi:%s) %s" % (FHT80TF[housecode], state, splitmsg, rssi, clrstr(msg)))
        else:
            print("\t unknown FHT80TF device [raw:%s] (rssi:%s) %s" % (splitmsg, rssi, clrstr(msg)))

    elif len(msg) == 12: #FHT80 #0B480026D70B
        if housecode in FHT80:
            state = "unknown state %s" % address
            if int(address,16) >= 0 & int(address,16) < 9: # FHT_ACTUATOR_0 .. FHT_ACTUATOR_8
                state = 'FHT_ACTUATOR_%s' % int(argument,16)
                value = str(round(float(int(argument,16) / 255.0) * 100, 0))
            if address == '3e':
                state = 'FTH_Mode'
                value = argument
            if address == '41':
                state = 'FHT_DESIRED_TEMP'
                value = str(round(float(int(argument,16) / 2.0), 0))
            if address == '42':
                state = 'FHT_MEASURED_TEMP_LOW'
                value = argument
            if address == '43':
                state = 'FHT_MEASURED_TEMP_HIGH'
                value = str(round(float(int(argument,16) * 256.0 / 10.0), 0))
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
            print("FHT80:   %-17s %-22s %-6s [raw:%s] (rssi:%s) %s" % (FHT80[housecode], state, value, splitmsg, rssi, clrstr(msg)))
        else:
            print("\t unknown FHT80 device [raw:%s] (rssi:%s) %s" % (splitmsg, rssi, clrstr(msg)))
    else:
        print("\t unknown device [raw:%s] (rssi:%s) %s (%s)" % (splitmsg, rssi, clrstr(msg), len(msg)))


def culDecode(msg):
    rawmsg = msg[1: len(msg)+1]

    if len(msg)>2 and msg[0] in 'AFTKEHRStZrib':	# known cul messages
        #msg = msg.strip('\r\n')
        rssi=int(msg[-2:],16)
        if rssi>128: rssi -= 256
        rssi = (rssi/2) - 74

    if msg.startswith('F'):
        parseFS20(rawmsg, rssi)
    elif msg.startswith('T'):
        parseFHT(rawmsg, rssi)
    elif msg.startswith('K'):
        parseS300TH(rawmsg, rssi)
    elif msg == "LOVF": # no send time available anymore
        print("No fs20 send time available");
    else:
        print("CUL received: " + msg)

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
        print("MQTT RX: Topic: %-35s >> Message: %-20s [%s]" % (msg.topic, str(msg.payload.strip().decode('ascii')), bool(msg.retain)))
        asyncio.ensure_future(culTxQueue.put(str(msg.payload.strip().decode('ascii'))))
        
    client.on_message = on_message

    lwtPublish = client.publish(mqtt_PublishTopic + "LWT", 'ON')
    await lwtPublish.wait_for_publish()
    print("MQTT LWT published!")

    while True:
        msg = await mqttTxQueue.get()
        try:
            # von CUL an MQTT
            msgPublish = client.publish(mqtt_PublishTopic + msg[0], msg[1], retain=msg[2])
            await msgPublish.wait_for_publish()
            print("MQTT TX: Topic: %-35s >> Message: %-20s [%s]" % (msg[0], str(msg[1]), str(msg[2])))			
            culDecode(str(msg[1]))
        except IndexError:
            print("MQTT publish failed: \t")
            print(msg)


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
