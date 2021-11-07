# pycul

*** deprecated, since at least python 3.4 - not longer maintained ***

access CUL stick (based on http://culfw.de/) using Python3 

CUL stick: http://shop.busware.de/product_info.php/cPath/1_35/products_id/29


### usage of cul2mqtt.py:

change the folling setting depending on the local setup   
* cul_port            = '/dev/ttyACM1'
* cul_baud            = 9600
* mqtt_server         = '192.168.2.36'
* mqtt_port           = 1883
* mqtt_SubscribeTopic = 'smarthome/cul/to/#'
* mqtt_PublishTopic   = 'smarthome/cul/from/'
* mqtt_user           = '****'
* mqtt_pass           = '****'
* mqtt_ca             = ''  ### not yet supported

after starting the script, CUL messages are send to stdout, e.g.
```
MQTT TX: Topic: FDC6900                             >> Message: FDC690000F2          [True]
FS20:    LichtKueche       FS20_Off                [raw:DC69-00-00-F2] (rssi:-81.0) DC690000F2
MQTT TX: Topic: FDC6902                             >> Message: FDC690211E4          [True]
FS20:    LichtKellerflur   FS20_On                 [raw:DC69-02-11-E4] (rssi:-88.0) DC690211E4
MQTT TX: Topic: K012321                             >> Message: K0123217937          [True]
S300TH:  1                 T:12.3 H:79.2                 [raw:0123217937] (rssi:-46.5)
MQTT TX: Topic: T162100                             >> Message: T162100A604F6        [True]
FHT80:   Erdgeschoss       FHT_ACTUATOR_4         2.0    [raw:1621-00-A6-04] (rssi:-79.0) 162100A604F6
MQTT TX: Topic: T162154                             >> Message: T1621546712F6        [True]
FHT80:   Erdgeschoss       FHT_ACTUATOR_18        7.0    [raw:1621-54-67-12] (rssi:-79.0) 1621546712F6
MQTT TX: Topic: T52FB7B                             >> Message: T52FB7B0234          [True]
FHT80TF: Multiraum         FHT80TF_WINDOW_CLOSED         [raw:52FB-7B-02-34] (rssi:-48.0) 52FB7B0234
...
MQTT RX: Topic: V                                   >> Message: .                    [False]
CUL:     sending V
MQTT TX: Topic: V 1.55                              >> Message: V 1.55 CUL868        [True]
CUL received: V 1.55 CUL868
...
MQTT RX: Topic: X                                   >> Message: T02                  [False]
CUL:     sending raw T02
MQTT TX: Topic: N/A                                 >> Message: N/A                  [True]
CUL received: N/A

```

### controll CUL devices with mqtt messages:

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "smarthome/cul/to/$1" -m "$2`

with $1 and $2: device starting with one of the following chars:

  $1 | description | $2
  --- | ---- | ---
  V | get Version of CUL stick | refer to: http://culfw.de/commandref.html#cmd_V
  X | send raw command  | e.g. X21: , X00: , X61: , ... refer to: http://culfw.de/commandref.html#cmd_X
  l | control LED on the Stick | with l00: LED on, l01: LED off, l02: LED blinking, refer to http://culfw.de/commandref.html#cmd_l
  F | send message to FS20 device | e.g. FABCDEF xx yy with ABDC = housecode, EF = device, xx = command, yy = timing, refer to http://culfw.de/commandref.html#cmd_F 
  T | send message to FHT device | t.b.d., refer to http://culfw.de/commandref.html#cmd_T

### examples

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "/smarthome/cul/to/V" -m ""`  
returns the Version of the CUL stick, e.g. `V 1.55 CUL868`

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "/smarthome/cul/to/X" -m "X21"`   
sets the CUL stick to normal output mode

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "/smarthome/cul/to/X" -m "X25"`   
sets the CUL stick to debugging mode

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "/smarthome/cul/to/FDC69B1" -m "on"`

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "/smarthome/cul/to/FDC69B1" -m "toggle"`

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <password> -t "/smarthome/cul/to/FDC69B1" -m "on-for-timer 120"`


For more details on the CUL Stick, please check 
* http://culfw.de/commandref.html
* http://fhz4linux.info/tiki-index.php?page=FHT%20protocol
* http://fhz4linux.info/tiki-index.php?page=FS20%20Protocol

