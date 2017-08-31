#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#########################################################################
#  Copyright 2017 Stefan Widmer                                          
#########################################################################
#  This file is part of SmartHomeNG.   
#
#  SmartHomeNG is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SmartHomeNG is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SmartHomeNG. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

import logging
import socket
from urllib.parse import urlparse
import upnpclient
import lib.connection
from lib.model.smartplugin import SmartPlugin

logger = logging.getLogger(__name__)

class UPnP(SmartPlugin):
    """
    Main class of the Plugin. Does all plugin specific stuff and provides
    the update functions for the items
    """
    ALLOW_MULTIINSTANCE = False
    PLUGIN_VERSION = "1.3.1"
    
    argitems = {}
    event_subscriptions = {}

    def __init__(self, sh, subscribe_events=False, event_callback_ip='0.0.0.0', event_callback_port=0):
        """
        Initalizes the plugin. The parameters describe for this method are pulled from the entry in plugin.conf.

        :param sh:  The instance of the smarthome object, save it for later references
        """
        
        self._sh = sh
        
        self._subscribe_events = self.to_bool(subscribe_events)
        if self._subscribe_events:
            if self.is_int(event_callback_port):
                port = int(event_callback_port)
            else:
                port = 0
                logger.error("Invalid value '{}' configured for attribute event_callback_port in plugin.conf, using '{}' instead".format(event_callback_port, port if port != None else "random"))
                
            self.callbackserver = CallbackServer(sh, self.set_item_by_statevar, event_callback_ip, port)
       
    def run(self):
        if self._subscribe_events:
            self.callbackserver.connect()
        self.alive = True

    def stop(self):
        if self._subscribe_events:
            self.callbackserver.close()
        self.alive = False
    

    def parse_item(self, item):
        """
        Default plugin parse_item method. Is called when the plugin is initialized.
        The plugin can, corresponding to its attribute keywords, decide what to do with
        the item in future, like adding it to an internal array for future reference

        :param item:    The item to process.
        :return:        If the plugin needs to be informed of an items change you should return a call back function
                        like the function update_item down below. An example when this is needed is the knx plugin
                        where parse_item returns the update_item function when the attribute knx_send is found.
                        This means that when the items value is about to be updated, the call back function is called
                        with the item, caller, source and dest as arguments and in case of the knx plugin the value
                        can be sent to the knx with a knx write function within the knx plugin.

        """
        if self.has_iattr(item.conf, 'upnp_device') and self.has_iattr(item.conf, 'upnp_service'):
            if self.has_iattr(item.conf, 'upnp_statevar'):
                device = upnpclient.Device(self.get_iattr_value(item.conf, 'upnp_device'))
                service = device[self.get_iattr_value(item.conf, 'upnp_service')]
                statevarname = self.get_iattr_value(item.conf, 'upnp_statevar')

                self.argitems[(service,statevarname)] = item
                
                if self._subscribe_events:
                    self.callbackserver.add_subscription(service)
                
            return self.update_item

    def parse_logic(self, logic):
        """
        Default plugin parse_logic method
        """
        #if 'xxx' in logic.conf:
            # self.function(logic['name'])
        pass

    def update_item(self, item, caller=None, source=None, dest=None):
        """
        Write items values

        :param item: item to be updated towards the plugin
        :param caller: if given it represents the callers name
        :param source: if given it represents the source
        :param dest: if given it represents the dest
        """
        logger.debug("item: {}, caller: {}, source: {}, dest: {}".format(item, caller, source, dest))

        if caller != 'UPnP' and self.has_iattr(item.conf, 'upnp_action'):
            value = item()
            
            iattr_action = self.get_iattr_value(item.conf, 'upnp_action')
            
            # if action is not a list, make one with the single entry
            if not isinstance(iattr_action, list):
                iattr_action = [ iattr_action ]
            
            for actionname in iattr_action:
                if isinstance(actionname, dict):
                    actionname = actionname[item()]
                if actionname == None:
                    pass
                
                server = upnpclient.Device(self.get_iattr_value(item.conf, 'upnp_device'))
                action = server.find_action(actionname)
                arguments = eval(self.get_iattr_value(item.conf, 'upnp_arguments')) if self.has_iattr(item.conf, 'upnp_arguments') else {}
                
                for (argname, statevar) in action.argsdef_in:
                    if statevar['name'] in self.argitems:
                        arguments[argname] = self.argitems[statevar['name']]()
                #for argname, argval in arguments.items():
                #    logger.info("arg: {} = {}".format(argname, argval))
                
                #call UPnP action                
                logger.info("Calling {}({})".format(actionname, arguments))
                resp = action(**arguments)
                logger.debug("UPnP response: {}".format(resp))
                for outargname, val in resp.items():
                    statevarname = dict(action.argsdef_out)[outargname]['name']
                    #logger.debug(statevarname)
                    new_source = "Action {}.{}.{}".format(server.friendly_name, service.name, iattr_action)
                    self.set_item_by_statevar(service, statevarname, value, new_source)

    def set_item_by_statevar(self, service, statevarname, value, source):
        if self.argitems[(service, statevarname)] != None:
            self.argitems[(service, statevarname)](value, 'UPnP', source)


class CallbackServer(lib.connection.Server):

    HEADER_TERMINATOR = b"\r\n\r\n"
    
    active_subscriptions = {}
    pending_subscriptions = set()
    
    def __init__(self, smarthome, set_item_by_statevar_callback, ip, port):
        lib.connection.Server.__init__(self, ip, port)
        self._set_item_by_statevar_callback = set_item_by_statevar_callback
        self._sh = smarthome
        
    def add_subscription(self, service):
        if self.connected:            
            # find out apropriate hostname or ip address for upnp device
            deviceLocation = tuple(urlparse(service.device.location).netloc.split(":"))
            #sq = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sq = socket.create_connection(deviceLocation)
            callback_host = sq.getsockname()[0]
            sq.shutdown(socket.SHUT_RDWR)
            sq.close()
            current_callback_url = "http://{}:{}/event".format(callback_host, self.socket.getsockname()[1])
            logger.debug("Adding event subscription for service {}.{} with callback URL '{}'".format(service.device.friendly_name, service.name, current_callback_url))
            
            sid, timeout = service.subscribe(current_callback_url)
            self.active_subscriptions[sid] = { "service": service, "latest_seq": -1, "sid": sid }
            logger.info("Added event subscription with id '{}' for service {}.{}".format(sid, service.device.friendly_name, service.name))
            #TODO: scheduler for renew subscription before timeout
        else:
            self.pending_subscriptions.add(service)
            logger.debug("Pending event subscription for service {}.{}".format(service.device.friendly_name, service.name))
    
    def connect(self):
        try:
            logger.debug("Binding CallbackServer")
            super().connect()
            logger.info("CallbackServer listening on '{}'".format(self._callback_url))
            for service in self.pending_subscriptions:
                self.add_subscription(service)
        except Exception as e:
            logger.error(e)
    
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

        sock, remoteaddr = self.accept()
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
            logger.warning("Bad request from {}".format(remoteaddr))
            self.send(b"HTTP/1.1 400 Bad Request\r\n\r\n", close=True)
            return
        else:
            #TODO: Parse UPnP NOTIFY header
            logger.debug("Notify Header:\n{}".format(headerstring))

            while True:
                buffer = sock.recv(1024)
                if not buffer:
                    break
                contentbytes.extend(buffer)
            
            #TODO: parse UPnP XML in contentbytes
            """
            sid = ???
            seq = ???
            statevarname = ???
            value = ???
            subscription = active_subscriptions[sid]
            latest_seq = subscription["latest_seq"]
            service = subscription["service"]
            if seq <= last_seq:
                logger.info("Ignored obsolete event notification for {}.{} with SEQ '{}' (latest SEQ was '{}')", service.device.friendly_name, service.name, seq, latest_seq)
                return
            
            source = "Event by {}.{}".format(service.device.friendly_name, service.name)
            self._set_item_by_statevar_callback(service, statevarname, value, source)
            """
            logger.debug("Notify Header:\n{}".format(contentbytes))
            
            self.send(b"HTTP/1.1 200 OK\r\n\r\n", close=True)
            
    @property
    def _callback_url(self):
        sockname = self.socket.getsockname()
        return "http://{}:{}/event".format(sockname[0], sockname[1])


"""
If the plugin is run standalone e.g. for test purposes the follwing code will be executed
"""
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(relativeCreated)6d %(threadName)s %(message)s')
    # todo
    # change PluginClassName appropriately
    PluginClassName(None).run()
