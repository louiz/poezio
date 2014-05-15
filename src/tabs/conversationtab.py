"""
Module for the ConversationTabs

A ConversationTab is a direct chat between two JIDs, outside of a room.

There are two different instances of a ConversationTab:
- A DynamicConversationTab that implements XEP-0296 (best practices for
    resource locking), which means it will switch the resource it is
    focused on depending on the presences received. This is the default.
- A StaticConversationTab that will stay focused on one resource all
    the time.

"""
from gettext import gettext as _

import logging
log = logging.getLogger(__name__)

import curses

from . basetabs import OneToOneTab, Tab

import common
import fixes
import windows
import xhtml
from common import safeJID
from config import config
from decorators import refresh_wrapper
from roster import roster
from theming import get_theme, dump_tuple

class ConversationTab(OneToOneTab):
    """
    The tab containg a normal conversation (not from a MUC)
    Must not be instantiated, use Static or Dynamic version only.
    """
    plugin_commands = {}
    plugin_keys = {}
    additional_informations = {}
    message_type = 'chat'
    def __init__(self, jid):
        OneToOneTab.__init__(self, jid)
        self.nick = None
        self.nick_sent = False
        self.state = 'normal'
        self.name = jid        # a conversation tab is linked to one specific full jid OR bare jid
        self.text_win = windows.TextWin()
        self._text_buffer.add_window(self.text_win)
        self.upper_bar = windows.ConversationStatusMessageWin()
        self.input = windows.MessageInput()
        # keys
        self.key_func['^I'] = self.completion
        # commands
        self.register_command('unquery', self.command_unquery,
                shortdesc=_('Close the tab.'))
        self.register_command('close', self.command_unquery,
                shortdesc=_('Close the tab.'))
        self.register_command('version', self.command_version,
                desc=_('Get the software version of the current interlocutor (usually its XMPP client and Operating System).'),
                shortdesc=_('Get the software version of the user.'))
        self.register_command('info', self.command_info,
                shortdesc=_('Get the status of the contact.'))
        self.register_command('last_activity', self.command_last_activity,
                usage=_('[jid]'),
                desc=_('Get the last activity of the given or the current contact.'),
                shortdesc=_('Get the activity.'),
                completion=self.core.completion_last_activity)
        self.resize()
        self.update_commands()
        self.update_keys()

    @property
    def general_jid(self):
        return safeJID(self.name).bare

    @staticmethod
    def add_information_element(plugin_name, callback):
        """
        Lets a plugin add its own information to the ConversationInfoWin
        """
        ConversationTab.additional_informations[plugin_name] = callback

    @staticmethod
    def remove_information_element(plugin_name):
        del ConversationTab.additional_informations[plugin_name]

    def completion(self):
        self.complete_commands(self.input)

    def command_say(self, line, attention=False, correct=False):
        msg = self.core.xmpp.make_message(self.get_dest_jid())
        msg['type'] = 'chat'
        msg['body'] = line
        if not self.nick_sent:
            msg['nick'] = self.core.own_nick
            self.nick_sent = True
        # trigger the event BEFORE looking for colors.
        # and before displaying the message in the window
        # This lets a plugin insert \x19xxx} colors, that will
        # be converted in xhtml.
        self.core.events.trigger('conversation_say', msg, self)
        if not msg['body']:
            self.cancel_paused_delay()
            self.text_win.refresh()
            self.input.refresh()
            return
        replaced = False
        if correct or msg['replace']['id']:
            msg['replace']['id'] = self.last_sent_message['id']
            if config.get_by_tabname('group_corrections', True, self.name):
                try:
                    self.modify_message(msg['body'], self.last_sent_message['id'], msg['id'], jid=self.core.xmpp.boundjid,
                            nickname=self.core.own_nick)
                    replaced = True
                except:
                    log.error('Unable to correct a message', exc_info=True)
        else:
            del msg['replace']
        if msg['body'].find('\x19') != -1:
            msg.enable('html')
            msg['html']['body'] = xhtml.poezio_colors_to_html(msg['body'])
            msg['body'] = xhtml.clean_text(msg['body'])
        if config.get_by_tabname('send_chat_states', True, self.general_jid, True) and self.remote_wants_chatstates is not False:
            needed = 'inactive' if self.inactive else 'active'
            msg['chat_state'] = needed
        if attention and self.remote_supports_attention:
            msg['attention'] = True
        self.core.events.trigger('conversation_say_after', msg, self)
        if not msg['body']:
            self.cancel_paused_delay()
            self.text_win.refresh()
            self.input.refresh()
            return
        if not replaced:
            self.add_message(msg['body'],
                    nickname=self.core.own_nick,
                    nick_color=get_theme().COLOR_OWN_NICK,
                    identifier=msg['id'],
                    jid=self.core.xmpp.boundjid,
                    typ=1)

        self.last_sent_message = msg
        if self.remote_supports_receipts:
            msg._add_receipt = True
        msg.send()
        self.cancel_paused_delay()
        self.text_win.refresh()
        self.input.refresh()

    def command_xhtml(self, arg):
        message = self.generate_xhtml_message(arg)
        if message:
            message.send()
            self.core.add_message_to_text_buffer(self._text_buffer, message['body'], None, self.core.own_nick)
            self.refresh()

    def command_last_activity(self, arg):
        """
        /activity [jid]
        """
        if arg.strip():
            return self.core.command_last_activity(arg)

        def callback(iq):
            if iq['type'] != 'result':
                if iq['error']['type'] == 'auth':
                    self.core.information('You are not allowed to see the activity of this contact.', 'Error')
                else:
                    self.core.information('Error retrieving the activity', 'Error')
                return
            seconds = iq['last_activity']['seconds']
            status = iq['last_activity']['status']
            from_ = iq['from']
            msg = '\x19%s}The last activity of %s was %s ago%s'
            if not safeJID(from_).user:
                msg = '\x19%s}The uptime of %s is %s.' % (
                        dump_tuple(get_theme().COLOR_INFORMATION_TEXT),
                        from_,
                        common.parse_secs_to_str(seconds))
            else:
                msg = '\x19%s}The last activity of %s was %s ago%s' % (
                    dump_tuple(get_theme().COLOR_INFORMATION_TEXT),
                    from_,
                    common.parse_secs_to_str(seconds),
                    (' and his/her last status was %s' % status) if status else '',)
            self.add_message(msg)
            self.core.refresh_window()

        self.core.xmpp.plugin['xep_0012'].get_last_activity(self.general_jid, block=False, callback=callback)

    @refresh_wrapper.conditional
    def command_info(self, arg):
        contact = roster[self.get_dest_jid()]
        jid = safeJID(self.get_dest_jid())
        if contact:
            if jid.resource:
                resource = contact[jid.full]
            else:
                resource = contact.get_highest_priority_resource()
        else:
            resource = None
        if resource:
            status = (_('Status: %s') % resource.status) if resource.status else ''
            self._text_buffer.add_message("\x19%(info_col)s}Show: %(show)s, %(status)s\x19o" % {
                'show': resource.show or 'available', 'status': status, 'info_col': dump_tuple(get_theme().COLOR_INFORMATION_TEXT)})
            return True
        else:
            self._text_buffer.add_message("\x19%(info_col)s}No information available\x19o" % {'info_col': dump_tuple(get_theme().COLOR_INFORMATION_TEXT)})
            return True

    def command_unquery(self, arg):
        self.core.close_tab()

    def command_version(self, arg):
        """
        /version
        """
        def callback(res):
            if not res:
                return self.core.information('Could not get the software version from %s' % (jid,), 'Warning')
            version = '%s is running %s version %s on %s' % (jid,
                                                             res.get('name') or _('an unknown software'),
                                                             res.get('version') or _('unknown'),
                                                             res.get('os') or _('an unknown platform'))
            self.core.information(version, 'Info')
        if arg:
            return self.core.command_version(arg)
        jid = safeJID(self.name)
        if not jid.resource:
            if jid in roster:
                resource = roster[jid].get_highest_priority_resource()
                jid = resource.jid if resource else jid
        fixes.get_version(self.core.xmpp, jid,
                callback=callback)

    def resize(self):
        self.need_resize = False
        if self.size.tab_degrade_y:
            display_bar = False
            info_win_height = 0
            tab_win_height = 0
            bar_height = 0
        else:
            display_bar = True
            info_win_height = self.core.information_win_size
            tab_win_height = Tab.tab_win_height()
            bar_height = 1

        self.text_win.resize(self.height - 2 - bar_height - info_win_height
                                - tab_win_height,
                             self.width, bar_height, 0)
        self.text_win.rebuild_everything(self._text_buffer)
        if display_bar:
            self.upper_bar.resize(1, self.width, 0, 0)
        self.info_header.resize(1, self.width,
                                self.height - 2 - info_win_height
                                    - tab_win_height,
                                0)
        self.input.resize(1, self.width, self.height - 1, 0)

    def refresh(self):
        if self.need_resize:
            self.resize()
        log.debug('  TAB   Refresh: %s', self.__class__.__name__)
        display_bar = display_info_win = not self.size.tab_degrade_y

        self.text_win.refresh()

        if display_bar:
            self.upper_bar.refresh(self.get_dest_jid(), roster[self.get_dest_jid()])
        self.info_header.refresh(self.get_dest_jid(), roster[self.get_dest_jid()], self.text_win, self.chatstate, ConversationTab.additional_informations)

        if display_info_win:
            self.info_win.refresh()
        self.refresh_tab_win()
        self.input.refresh()

    def refresh_info_header(self):
        self.info_header.refresh(self.get_dest_jid(), roster[self.get_dest_jid()],
                self.text_win, self.chatstate, ConversationTab.additional_informations)
        self.input.refresh()

    def get_nick(self):
        jid = safeJID(self.name)
        contact = roster[jid.bare]
        if contact:
            return contact.name or jid.user
        else:
            if self.nick:
                return self.nick
            return jid.user

    def on_input(self, key, raw):
        if not raw and key in self.key_func:
            self.key_func[key]()
            return False
        self.input.do_command(key, raw=raw)
        empty_after = self.input.get_text() == '' or (self.input.get_text().startswith('/') and not self.input.get_text().startswith('//'))
        self.send_composing_chat_state(empty_after)
        return False

    def on_lose_focus(self):
        contact = roster[self.get_dest_jid()]
        jid = safeJID(self.get_dest_jid())
        if contact:
            if jid.resource:
                resource = contact[jid.full]
            else:
                resource = contact.get_highest_priority_resource()
        else:
            resource = None
        if self.input.text:
            self.state = 'nonempty'
        else:
            self.state = 'normal'
        self.text_win.remove_line_separator()
        self.text_win.add_line_separator(self._text_buffer)
        if config.get_by_tabname('send_chat_states', True, self.general_jid, True) and (not self.input.get_text() or not self.input.get_text().startswith('//')):
            if resource:
                self.send_chat_state('inactive')
        self.check_scrolled()

    def on_gain_focus(self):
        contact = roster[self.get_dest_jid()]
        jid = safeJID(self.get_dest_jid())
        if contact:
            if jid.resource:
                resource = contact[jid.full]
            else:
                resource = contact.get_highest_priority_resource()
        else:
            resource = None

        self.state = 'current'
        curses.curs_set(1)
        if config.get_by_tabname('send_chat_states', True, self.general_jid, True) and (not self.input.get_text() or not self.input.get_text().startswith('//')):
            if resource:
                self.send_chat_state('active')

    def on_info_win_size_changed(self):
        if self.core.information_win_size >= self.height-3:
            return
        self.text_win.resize(self.height-3-self.core.information_win_size - Tab.tab_win_height(), self.width, 1, 0)
        self.info_header.resize(1, self.width, self.height-2-self.core.information_win_size - Tab.tab_win_height(), 0)

    def get_text_window(self):
        return self.text_win

    def on_close(self):
        Tab.on_close(self)
        if config.get_by_tabname('send_chat_states', True, self.general_jid, True):
            self.send_chat_state('gone')

    def matching_names(self):
        res = []
        jid = safeJID(self.name)
        res.append((2, jid.bare))
        res.append((1, jid.user))
        contact = roster[self.name]
        if contact and contact.name:
            res.append((0, contact.name))
        return res

class DynamicConversationTab(ConversationTab):
    """
    A conversation tab associated with one bare JID that can be “locked” to
    a full jid, and unlocked, as described in the XEP-0296.
    Only one DynamicConversationTab can be opened for a given jid.
    """
    def __init__(self, jid, resource=None):
        self.locked_resource = None
        self.name = safeJID(jid).bare
        if resource:
            self.lock(resource)
        self.info_header = windows.DynamicConversationInfoWin()
        ConversationTab.__init__(self, jid)
        self.register_command('unlock', self.unlock_command,
                shortdesc=_('Unlock the converstation from a particular resource.'))

    def lock(self, resource):
        """
        Lock the tab to the resource.
        """
        assert(resource)
        if resource != self.locked_resource:
            self.locked_resource = resource

            message = _('\x19%s}Conversation locked to %s/%s.') % (
                    dump_tuple(get_theme().COLOR_INFORMATION_TEXT),
                    self.name,
                    resource)
            self.add_message(message, typ=0)
            self.check_features()

    def unlock_command(self, arg=None):
        self.unlock()
        self.refresh_info_header()

    def unlock(self, from_=None):
        """
        Unlock the tab from a resource. It is now “associated” with the bare
        jid.
        """
        self.remote_wants_chatstates = None
        if self.locked_resource != None:
            self.locked_resource = None

            if from_:
                message = _('\x19%s}Conversation unlocked '
                            '(received activity from %s).') % (
                        dump_tuple(get_theme().COLOR_INFORMATION_TEXT),
                        from_)
                self.add_message(message, typ=0)
            else:
                message = _('\x19%s}Conversation unlocked.') % (
                        dump_tuple(get_theme().COLOR_INFORMATION_TEXT))
                self.add_message(message, typ=0)

    def get_dest_jid(self):
        """
        Returns the full jid (using the locked resource), or the bare jid if
        the conversation is not locked.
        """
        if self.locked_resource:
            return "%s/%s" % (self.name, self.locked_resource)
        return self.name

    def refresh(self):
        """
        Different from the parent class only for the info_header object.
        """
        if self.need_resize:
            self.resize()
        log.debug('  TAB   Refresh: %s', self.__class__.__name__)
        display_bar = display_info_win = not self.size.tab_degrade_y

        self.text_win.refresh()
        if display_bar:
            self.upper_bar.refresh(self.name, roster[self.name])
        if self.locked_resource:
            displayed_jid = "%s/%s" % (self.name, self.locked_resource)
        else:
            displayed_jid = self.name
        self.info_header.refresh(displayed_jid, roster[self.name],
                                 self.text_win, self.chatstate,
                                 ConversationTab.additional_informations)
        if display_info_win:
            self.info_win.refresh()

        self.refresh_tab_win()
        self.input.refresh()

    def refresh_info_header(self):
        """
        Different from the parent class only for the info_header object.
        """
        if self.locked_resource:
            displayed_jid = "%s/%s" % (self.name, self.locked_resource)
        else:
            displayed_jid = self.name
        self.info_header.refresh(displayed_jid, roster[self.name],
                self.text_win, self.chatstate, ConversationTab.additional_informations)
        self.input.refresh()

class StaticConversationTab(ConversationTab):
    """
    A conversation tab associated with one Full JID. It cannot be locked to
    an different resource or unlocked.
    """
    def __init__(self, jid):
        assert(safeJID(jid).resource)
        self.info_header = windows.ConversationInfoWin()
        ConversationTab.__init__(self, jid)


