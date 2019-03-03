# pycul
access CUL stick using Python3 

CUL stick: http://shop.busware.de/product_info.php/cPath/1_35/products_id/29


### usage of cul2mqtt.py:

`mosquitto_pub -h <hostname> -p <port> -u <username> -P <passworf> -t "smarthome/cul/to/$1" -m "$2`
  with $1: device starting with one of the following chars:

  $1 | description | $2
  --- | ---- | ---
  V | get Version of CUL stick | --
  X | send raw command  | e.g. X21: , X00: , X61: , ... refer to: http://culfw.de/commandref.html#cmd_X
  l | control LED on the Stick | with l00: LED on, l01: LED off, l02: LED blinking, refer to http://culfw.de/commandref.html#cmd_l
  F | send message to FS20 device | e.g. FABCDEF xx yy with ABDC = housecode, EF = device, xx = command, yy = timing, refer to http://culfw.de/commandref.html#cmd_F 
  T | send message to FHT device | t.b.d., refer to http://culfw.de/commandref.html#cmd_T
  
For more details on the CUL Stick, please check http://culfw.de/commandref.html
 
