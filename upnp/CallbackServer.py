import logging
from lib.model.smartplugin import SmartPlugin

"""
in __init__.py
--------------

    def __init__(self, smarthome, subscribe_events=false, event_callback_ip='0.0.0.0', event_callback_port=0):
        self._subscribe_events = self.to_bool(subscribe_events)
        if self._subscribe_events:
            if self.is_int(event_callback_port):
                port = int(event_callback_port)
            else:
                port = 0
                self.logger.error("Invalid value '{}' configured for attribute event_callback_port in plugin.conf, using '{}' instead".format(event_callback_port, port if port != None else "random")
            
            self.callbackserver = CallbackServer(smarthome, event_callback_ip, event_callback_port)
            

    def run(self):
        if self._subscribe_events:
            self.callbackserver.connect()
            self.actual_port = self.callbackserver.sock.getsockname()[1];
    
    def stop(self):
        if self._subscribe_events:
            self.callbackserver.close()
"""

class CallbackServer(lib.connection.Server):

    HEADER_TERMINATOR = b"\r\n\r\n"
    
    def __init__(self, smarthome, ip, port):
        lib.connection.Server.__init__(self, ip, port)
        self.logger = logging.getLogger(__name__)
        self._sh = smarthome

    def handle_connection(self):
# Notify message sample:
"""    
NOTIFY delivery path HTTP/1.1
HOST: delivery host:delivery port
CONTENT-TYPE: text/xml; charset="utf-8"
NT: upnp:event
NTS: upnp:propchange
SID: uuid:subscription-UUID
SEQ: event key
CONTENT-LENGTH: bytes in body

<?xml version="1.0"?>
<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
    <e:property>
        <variableName>new value</variableName>
    </e:property>
</e:propertyset>
"""

        sock, address = self.accept()
        if sock is None:
            return
        
        headerbytes = bytearray()
        contentbytes = bytearray()
        while True:
            buffer = sock.recv(1024)
            if not buffer:
                break
            if HEADER_TERMINATOR not in buffer:
                headerbytes.extend(buffer)
            else:
                index = buffer.find(HEADER_TERMINATOR)
                headerbytes.extend(buffer[:index])
                contentbytes = buffer[index]
        
        headerstring = headerbytes.decode()
        if not headerstring.startswith('NOTIFY '):
            self.send(b"HTTP/1.1 400 Bad Request\r\n\r\n", close=True)
            return
        else:
            #TODO: Parse UPnP NOTIFY header

            while True:
                buffer = sock.recv(1024)
                if not buffer:
                    break
                contentbytes.extend(buffer)
            
            #TODO: parse UPnP XML in contentbytes
            
            self.send(b"HTTP/1.1 200 OK\r\n\r\n", close=True)
