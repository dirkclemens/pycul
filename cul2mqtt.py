#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Idea and parts taken from:
#   https://github.com/adlerweb/asysbus/blob/master/tools/mqtt-proxy.py
#   https://github.com/hobbyquaker/cul
#   https://github.com/HJvA/fshome
#   http://www.fhemwiki.de/wiki/FHT80b
#   http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
#   http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol
#
# Requires:
#   asyncio
#   aiomqtt (+ paho-mqtt)
#   pyserial-asyncio (+ pyserial)
#

import os
from time import strftime, localtime
import time

import asyncio
import serial_asyncio
import aiomqtt
from functools import partial

port                = '/dev/ttyACM1'
baud                = 9600

mqtt_server         = '192.168.2.36'
mqtt_port           = 1883
mqtt_SubscribeTopic = 'smarthome/cul/to/#'
mqtt_PublishTopic   = 'smarthome/cul/from/'
mqtt_user           = '***'
mqtt_pass           = '***'
mqtt_ca             = ''

if not os.path.exists(port):
    print('Serial port does not exist')

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
        self.transport.serial.write(b'V\r\n')
        asyncio.sleep(1.0)
        self.transport.serial.write(b'X21\r\n')
        print('CUL init done.')

        # start receiving loop
        asyncio.ensure_future(self.send())
        print('starting loop')

    def data_received(self, data):
        #print ('data_received')
        self.buf += data
        if b'\n' in self.buf:
            lines = self.buf.split(b'\n')
            self.buf = lines[-1] # whatever was left over
            for line in lines[:-1]:
                #print(line.strip().decode('ascii'))
                #asyncio.ensure_future(self.queueRX.put(line))
                message = line.strip().decode('ascii')
                topic = message[0:5]
                asyncio.ensure_future(mqttTxQueue.put([mqtt_PublishTopic + topic, message, True]))

    async def send(self): ## does not yet work (!!!)
        while True:
            msg = await self.queueTX.get()
            #print('Sending to CUL: %s' % (msg,))            
            msg = '%s\r\n' % msg

            hausc   = "DC69"
            devadr  = "B1"
            dur = 0    
            cmd = "toggle"
            cde = fs20commands.index(cmd)
            ee=""
            if not dur is None:
                cde |= 0x20
                for i in range(0,12):
                    if len(ee)==0:
                        for j in range(0,15):
                            val = (2**i)*j*0.25
                            if val >= dur:
                                ee = "%0.2X" % (i*16+j,)
                                break
            cmd = "%0.2X" % cde
            print("sending cmd to CUL: %s (%x) dur:%s to hc:%s adr:%s" % (cmd,cde,ee,hausc,devadr))
            self.transport.serial.write(bytes('F'+hausc+devadr+cmd+ee, 'ascii'))
            #self.transport.serial.write(bytes('{!r}'.format('F'+hausc+devadr+cmd+ee), 'ascii'))
            #self.transport.serial.write(bytes(msg, 'ascii'))

    def connection_lost(self, exc):
        print('CUL serial port closed.')
        self.transport.serial.write(b'X00\r\n') # close CUL
        asyncio.get_event_loop().stop()
        # the value passed to set_result will be transmitted to
        # run_until_complete(protocol.wait_connection_lost()).
        #self.__done.set_result(None)

    #def eof_received(self):
    #    print("eof_received")
    #    return True

    #def write_data(self):
    #    print("write_data")
    #    #self.transport.write(self.message)

    # When awaited, resumes execution after connection_lost()
    # has been invoked on this protocol.
    #def wait_connection_lost(self):
    #    print('wait_connection_lost')
    #    return self.__done



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
    
    await client.connect(server, port)
    await connected.wait()
    print("MQTT connected")

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
culSAIO = serial_asyncio.create_serial_connection(loop, culPartial, port, baudrate=baud)
asyncio.ensure_future(culSAIO)
asyncio.ensure_future(mqtt(mqttTxQueue, culTxQueue, mqtt_server, mqtt_port, mqtt_user, mqtt_pass, mqtt_ca))

loop.run_forever()
loop.close()
