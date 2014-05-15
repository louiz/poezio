# Copyright 2010-2011 Florent Le Coz <louiz@louiz.org>
#
# This file is part of Poezio.
#
# Poezio is free software: you can redistribute it and/or modify
# it under the terms of the zlib license. See the COPYING file.

"""
Defines the Connection class
"""

import logging
log = logging.getLogger(__name__)


import getpass
import sleekxmpp
from sleekxmpp.plugins.xep_0184 import XEP_0184

import common
import fixes
from common import safeJID
from config import config, options

class Connection(sleekxmpp.ClientXMPP):
    """
    Receives everything from Jabber and emits the
    appropriate signals
    """
    __init = False
    def __init__(self):
        resource = config.get('resource', '')
        if config.get('jid', ''):
            # Field used to know if we are anonymous or not.
            # many features will be handled differently
            # depending on this setting
            self.anon = False
            jid = '%s' % config.get('jid', '')
            if resource:
                jid = '%s/%s'% (jid, resource)
            password = config.get('password', '') or getpass.getpass()
        else: # anonymous auth
            self.anon = True
            jid = config.get('server', 'anon.jeproteste.info')
            if resource:
                jid = '%s/%s' % (jid, resource)
            password = None
        jid = safeJID(jid)
        # TODO: use the system language
        sleekxmpp.ClientXMPP.__init__(self, jid, password,
                                      lang=config.get('lang', 'en'))

        force_encryption = config.get('force_encryption', True)
        if force_encryption:
            self['feature_mechanisms'].unencrypted_plain = False
            self['feature_mechanisms'].unencrypted_digest = False
            self['feature_mechanisms'].unencrypted_cram = False
            self['feature_mechanisms'].unencrypted_scram = False

        self.core = None
        self.auto_reconnect = config.get('auto_reconnect', False)
        self.reconnect_max_attempts = 0
        self.auto_authorize = None
        # prosody defaults, lowest is AES128-SHA, it should be a minimum
        # for anything that came out after 2002
        self.ciphers = config.get('ciphers',
                                  'HIGH+kEDH:HIGH+kEECDH:HIGH:!PSK'
                                    ':!SRP:!3DES:!aNULL')
        self.ca_certs = config.get('ca_cert_path', '') or None
        interval = config.get('whitespace_interval', '300')
        if interval.isdecimal() and int(interval) > 0:
            self.whitespace_keepalive_interval = int(interval)
        else:
            self.whitespace_keepalive_interval = 300
        self.register_plugin('xep_0004')
        self.register_plugin('xep_0012')
        self.register_plugin('xep_0030')
        self.register_plugin('xep_0045')
        self.register_plugin('xep_0048')
        self.register_plugin('xep_0050')
        self.register_plugin('xep_0060')
        self.register_plugin('xep_0066')
        self.register_plugin('xep_0071')
        self.register_plugin('xep_0077')
        self.plugin['xep_0077'].create_account = False
        self.register_plugin('xep_0085')
        self.register_plugin('xep_0115')

        # monkey-patch xep_0184 to avoid requesting receipts for messages
        # without a body
        XEP_0184._filter_add_receipt_request = fixes._filter_add_receipt_request
        self.register_plugin('xep_0184')
        self.plugin['xep_0184'].auto_ack = config.get('ack_message_receipts',
                                                      True)
        self.plugin['xep_0184'].auto_request = config.get(
                'request_message_receipts', True)

        self.register_plugin('xep_0191')
        self.register_plugin('xep_0199')
        self.set_keepalive_values()

        if config.get('enable_user_tune', True):
            self.register_plugin('xep_0118')

        if config.get('enable_user_nick', True):
            self.register_plugin('xep_0172')

        if config.get('enable_user_mood', True):
            self.register_plugin('xep_0107')

        if config.get('enable_user_activity', True):
            self.register_plugin('xep_0108')

        if config.get('enable_user_gaming', True):
            self.register_plugin('xep_0196')

        if config.get('send_poezio_info', True):
            info = {'name':'poezio',
                    'version': options.version}
            if config.get('send_os_info', True):
                info['os'] = common.get_os_info()
            self.plugin['xep_0030'].set_identities(
                    identities=set([('client', 'pc', None, 'Poezio')]))
        else:
            info = {'name': '', 'version': ''}
            self.plugin['xep_0030'].set_identities(
                    identities=set([('client', 'pc', None, '')]))
        self.register_plugin('xep_0092', pconfig=info)
        if config.get('send_time', True):
            self.register_plugin('xep_0202')
        self.register_plugin('xep_0224')
        self.register_plugin('xep_0249')
        self.register_plugin('xep_0280')
        self.register_plugin('xep_0297')
        self.register_plugin('xep_0308')

    def set_keepalive_values(self, option=None, value=None):
        """
        Called at startup, or triggered when one of
        "connection_timeout_delay" and "connection_check_interval" options
        is changed.
        Unload and reload the ping plugin, with the new values.
        """
        ping_interval = config.get('connection_check_interval', 60)
        timeout_delay = config.get('connection_timeout_delay', 10)
        if timeout_delay <= 0:
            # We help the stupid user (with a delay of 0, poezio will try to
            # reconnect immediately because the timeout is immediately
            # passed)
            # 1 second is short, but, well
            timeout_delay = 1
        self.plugin['xep_0199'].disable_keepalive()
        # If the ping_interval is 0 or less, we just disable the keepalive
        if ping_interval > 0:
            self.plugin['xep_0199'].enable_keepalive(ping_interval,
                                                     timeout_delay)

    def start(self):
        """
        Connect and process events.

        TODO: try multiple servers with anon auth.
        """
        custom_host = config.get('custom_host', '')
        custom_port = config.get('custom_port', 5222)
        if custom_port == -1:
            custom_port = 5222
        if custom_host:
            res = self.connect((custom_host, custom_port), reattempt=True)
        elif custom_port != 5222 and custom_port != -1:
            res = self.connect((self.boundjid.host, custom_port),
                               reattempt=True)
        else:
            res = self.connect(reattempt=True)
        if not res:
            return False
        self.process(threaded=True)
        return True

    def send_raw(self, data, now=False, reconnect=None):
        """
        Overrides XMLStream.send_raw, with an event added
        """
        if self.core:
            self.core.outgoing_stanza(data)
        sleekxmpp.ClientXMPP.send_raw(self, data, now, reconnect)

class MatchAll(sleekxmpp.xmlstream.matcher.base.MatcherBase):
    """
    Callback to retrieve all the stanzas for the XML tab
    """
    def match(self, xml):
        "match everything"
        return True
