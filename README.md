# pycul
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


For more details on the CUL Stick, please check http://culfw.de/commandref.html
 
