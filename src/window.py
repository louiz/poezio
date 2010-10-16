# Copyright 2010 Le Coz Florent <louiz@louiz.org>
#
# This file is part of Poezio.
#
# Poezio is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# Poezio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Poezio.  If not, see <http://www.gnu.org/licenses/>.

from gettext import (bindtextdomain, textdomain, bind_textdomain_codeset,
                     gettext as _)
from os.path import isfile

import locale
locale.setlocale(locale.LC_ALL, '')

import shlex
import curses
from config import config

from threading import Lock

from contact import Contact
from roster import RosterGroup

from message import Line
from tab import MIN_WIDTH, MIN_HEIGHT

import theme

from common import debug

g_lock = Lock()

class Win(object):
    def __init__(self, height, width, y, x, parent_win):
        self._resize(height, width, y, x, parent_win, True)

    def _resize(self, height, width, y, x, parent_win, visible):
        if not visible:
            return
        self.height, self.width, self.x, self.y = height, width, x, y
        try:
            self.win = curses.newwin(height, width, y, x)
        except:
            # When resizing in a too little height (less than 3 lines)
            # We don't need to resize the window, since this size
            # just makes no sense
            # Just don't crash when this happens.
            # (°>       also, a penguin
            # //\
            # V_/_
            return
        self.win.leaveok(1)

    def refresh(self):
        self.win.noutrefresh()

    def addnstr(self, *args):
        """
        Safe call to addnstr
        """
        try:
            self.win.addnstr(*args)
        except:
            pass

    def addstr(self, *args):
        """
        Safe call to addstr
        """
        try:
            self.win.addstr(*args)
        except:
            pass

    def finish_line(self, color):
        """
        Write colored spaces until the end of line
        """
        (y, x) = self.win.getyx()
        size = self.width-x
        self.addnstr(' '*size, size, curses.color_pair(color))

class UserList(Win):
    def __init__(self, height, width, y, x, parent_win, visible):
        Win.__init__(self, height, width, y, x, parent_win)
        self.visible = visible
        self.color_role = {'moderator': theme.COLOR_USER_MODERATOR,
                           'participant':theme.COLOR_USER_PARTICIPANT,
                           'visitor':theme.COLOR_USER_VISITOR,
                           'none':theme.COLOR_USER_NONE,
                           '':theme.COLOR_USER_NONE
                           }
        self.color_show = {'xa':theme.COLOR_STATUS_XA,
                           'none':theme.COLOR_STATUS_NONE,
                           '':theme.COLOR_STATUS_NONE,
                           'dnd':theme.COLOR_STATUS_DND,
                           'away':theme.COLOR_STATUS_AWAY,
                           'chat':theme.COLOR_STATUS_CHAT
                           }

    def refresh(self, users):
        if not self.visible:
            return
        with g_lock:
            self.win.erase()
            y = 0
            for user in sorted(users):
                if not user.role in self.color_role:
                    role_col = theme.COLOR_USER_NONE
                else:
                    role_col = self.color_role[user.role]
                if not user.show in self.color_show:
                    show_col = theme.COLOR_STATUS_NONE
                else:
                    show_col = self.color_show[user.show]
                self.addstr(y, 0, theme.CHAR_STATUS, curses.color_pair(show_col))
                self.addnstr(y, 1, user.nick, self.width-1, curses.color_pair(role_col))
                y += 1
                if y == self.height:
                    break
            self.win.refresh()

    def resize(self, height, width, y, x, stdscr, visible):
        self.visible = visible
        if not visible:
            return
        self._resize(height, width, y, x, stdscr, visible)
        self.win.attron(curses.color_pair(theme.COLOR_VERTICAL_SEPARATOR))
        self.win.vline(0, 0, curses.ACS_VLINE, self.height)
        self.win.attroff(curses.color_pair(theme.COLOR_VERTICAL_SEPARATOR))

class Topic(Win):
    def __init__(self, height, width, y, x, parent_win, visible):
        self.visible = visible
        Win.__init__(self, height, width, y, x, parent_win)

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)

    def refresh(self, topic):
        if not self.visible:
            return
        with g_lock:
            self.win.erase()
            self.addstr(0, 0, topic[:self.width-1], curses.color_pair(theme.COLOR_TOPIC_BAR))
            (y, x) = self.win.getyx()
            remaining_size = self.width - x
            if remaining_size:
                self.addnstr(' '*remaining_size, remaining_size,
                             curses.color_pair(theme.COLOR_INFORMATION_BAR))
            self.win.refresh()

class GlobalInfoBar(Win):
    def __init__(self, height, width, y, x, parent_win, visible):
        self.visible = visible
        Win.__init__(self, height, width, y, x, parent_win)

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)

    def refresh(self, tabs, current):
        if not self.visible:
            return
        def compare_room(a):
            # return a.nb - b.nb
            return a.nb
        comp = lambda x: x.nb
        with g_lock:
            self.win.erase()
            self.addstr(0, 0, "[", curses.color_pair(theme.COLOR_INFORMATION_BAR))
            sorted_tabs = sorted(tabs, key=comp)
            for tab in sorted_tabs:
                color = tab.get_color_state()
                try:
                    self.addstr("%s" % str(tab.nb), curses.color_pair(color))
                    self.addstr("|", curses.color_pair(theme.COLOR_INFORMATION_BAR))
                except:             # end of line
                    break
            (y, x) = self.win.getyx()
            self.addstr(y, x-1, '] ', curses.color_pair(theme.COLOR_INFORMATION_BAR))
            (y, x) = self.win.getyx()
            remaining_size = self.width - x
            self.addnstr(' '*remaining_size, remaining_size,
                         curses.color_pair(theme.COLOR_INFORMATION_BAR))
            self.win.refresh()

class InfoWin(Win):
    """
    Base class for all the *InfoWin, used in various tabs. For example
    MucInfoWin, etc. Provides some useful methods.
    """
    def __init__(self, height, width, y, x, parent_win, visible):
        self.visible = visible
        Win.__init__(self, height, width, y, x, parent_win)

    def print_scroll_position(self, text_buffer):
        """
        Print, link in Weechat, a -PLUS(n)- where n
        is the number of available lines to scroll
        down
        """
        if text_buffer.pos > 0:
            plus = ' -PLUS(%s)-' % text_buffer.pos
            self.addstr(plus, curses.color_pair(theme.COLOR_SCROLLABLE_NUMBER) | curses.A_BOLD)

class PrivateInfoWin(InfoWin):
    """
    The live above the information window, displaying informations
    about the MUC user we are talking to
    """
    def __init__(self, height, width, y, x, parent_win, visible):
        InfoWin.__init__(self, height, width, y, x, parent_win, visible)

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)

    def refresh(self, room):
        if not self.visible:
            return
        with g_lock:
            self.win.erase()
            self.write_room_name(room)
            self.print_scroll_position(room)
            self.finish_line(theme.COLOR_INFORMATION_BAR)
            self.win.refresh()

    def write_room_name(self, room):
        (room_name, nick) = room.name.split('/', 1)
        self.addstr(nick, curses.color_pair(13))
        txt = ' from room %s' % room_name
        self.addstr(txt, curses.color_pair(theme.COLOR_INFORMATION_BAR))

class ConversationInfoWin(InfoWin):
    """
    The line above the information window, displaying informations
    about the MUC user we are talking to
    """
    def __init__(self, height, width, y, x, parent_win, visible):
        InfoWin.__init__(self, height, width, y, x, parent_win, visible)

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)

    def refresh(self, room, contact):
        if not self.visible:
            return
        # contact can be None, if we receive a message
        # from someone not in our roster. In this case, we display
        # only the maximum information from the message we can get.
        with g_lock:
            self.win.erase()
            self.write_room_name(contact, room)
            self.print_scroll_position(room)
            self.finish_line(theme.COLOR_INFORMATION_BAR)
            self.win.refresh()

    def write_room_name(self, contact, room):
        if not contact:
            txt = '%s' % room.name
        else:
            txt = '%s' % contact.get_jid().bare
        self.addstr(txt, curses.color_pair(theme.COLOR_INFORMATION_BAR))

class MucInfoWin(InfoWin):
    """
    The line just above the information window, displaying informations
    about the MUC we are viewing
    """
    def __init__(self, height, width, y, x, parent_win, visible):
        InfoWin.__init__(self, height, width, y, x, parent_win, visible)

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)

    def refresh(self, room):
        if not self.visible:
            return
        with g_lock:
            self.win.erase()
            self.write_room_name(room)
            self.write_own_nick(room)
            self.write_disconnected(room)
            self.write_role(room)
            self.print_scroll_position(room)
            self.finish_line(theme.COLOR_INFORMATION_BAR)
            self.win.refresh()

    def write_room_name(self, room):
        """
        """
        self.addstr('[', curses.color_pair(theme.COLOR_INFORMATION_BAR))
        self.addnstr(room.name, len(room.name), curses.color_pair(13))
        self.addstr('] ', curses.color_pair(theme.COLOR_INFORMATION_BAR))

    def write_disconnected(self, room):
        """
        Shows a message if the room is not joined
        """
        if not room.joined:
            self.addstr(' -!- Not connected ', curses.color_pair(theme.COLOR_INFORMATION_BAR))

    def write_own_nick(self, room):
        """
        Write our own nick in the info bar
        """
        nick = room.own_nick
        if not nick:
            return
        if len(nick) > 13:
            nick = nick[:13]+'…'
        self.addstr(nick, curses.color_pair(theme.COLOR_INFORMATION_BAR))

    def write_role(self, room):
        """
        Write our own role and affiliation
        """
        own_user = None
        for user in room.users:
            if user.nick == room.own_nick:
                own_user = user
                break
        if not own_user:
            return
        txt = ' ('
        if own_user.affiliation != 'none':
            txt += own_user.affiliation+', '
        txt += own_user.role+')'
        self.addstr(txt, curses.color_pair(theme.COLOR_INFORMATION_BAR))

class TextWin(Win):
    """
    Just keep ONE single window for the text area and rewrite EVERYTHING
    on each change. (thanks weechat :o)
    """
    def __init__(self, height, width, y, x, parent_win, visible):
        Win.__init__(self, height, width, y, x, parent_win)
        self.visible = visible

    def build_lines_from_messages(self, messages):
        """
        From all the existing messages in the window, create the that will
        be displayed on the screen
        """
        lines = []
        for message in messages:
            if message == None:  # line separator
                lines.append(None)
                continue
            txt = message.txt
            if not txt:
                continue
            # length of the time
            offset = 9+len(theme.CHAR_TIME_LEFT[:1])+len(theme.CHAR_TIME_RIGHT[:1])
            if message.nickname and len(message.nickname) >= 30:
                nick = message.nickname[:30]+'…'
            else:
                nick = message.nickname
            if nick:
                offset += len(nick) + 2 # + nick + spaces length
            first = True
            this_line_was_broken_by_space = False
            while txt != '':
                if txt[:self.width-offset].find('\n') != -1:
                    limit = txt[:self.width-offset].find('\n')
                else:
                    # break between words if possible
                    if len(txt) >= self.width-offset:
                        limit = txt[:self.width-offset].rfind(' ')
                        this_line_was_broken_by_space = True
                        if limit <= 0:
                            limit = self.width-offset
                            this_line_was_broken_by_space = False
                    else:
                        limit = self.width-offset-1
                        this_line_was_broken_by_space = False
                color = message.user.color if message.user else None
                if not first:
                    nick = None
                    time = None
                else:
                    time = message.time
                l = Line(nick, color,
                         time,
                         txt[:limit], message.color,
                         offset,
                         message.colorized)
                lines.append(l)
                if this_line_was_broken_by_space:
                    txt = txt[limit+1:] # jump the space at the start of the line
                else:
                    txt = txt[limit:]
                if txt.startswith('\n'):
                    txt = txt[1:]
                first = False
        return lines
        return lines[-len(messages):] # return only the needed number of lines

    def refresh(self, room):
        """
        Build the Line objects from the messages, and then write
        them in the text area
        """
        if not self.visible:
            return
        if self.height <= 0:
            return
        with g_lock:
            self.win.erase()
            lines = self.build_lines_from_messages(room.messages)
            if room.pos + self.height > len(lines):
                room.pos = len(lines) - self.height
                if room.pos < 0:
                    room.pos = 0
            if room.pos != 0:
                lines = lines[-self.height-room.pos:-room.pos]
            else:
                lines = lines[-self.height:]
            y = 0
            for line in lines:
                self.win.move(y, 0)
                if line == None:
                    self.write_line_separator()
                    y += 1
                    continue
                if line.time is not None:
                    self.write_time(line.time)
                if line.nickname is not None:
                    self.write_nickname(line.nickname, line.nickname_color)
                self.write_text(y, line.text_offset, line.text, line.text_color, line.colorized)
                y += 1
            self.win.refresh()

    def write_line_separator(self):
        """
        """
        self.win.attron(curses.color_pair(theme.COLOR_NEW_TEXT_SEPARATOR))
        self.addnstr('- '*(self.width//2), self.width)
        self.win.attroff(curses.color_pair(theme.COLOR_NEW_TEXT_SEPARATOR))

    def write_text(self, y, x, txt, color, colorized):
        """
        write the text of a line.
        """
        txt = txt
        if not colorized:
            if color:
                self.win.attron(curses.color_pair(color))
            self.addstr(y, x, txt)
            if color:
                self.win.attroff(curses.color_pair(color))

        else:                   # Special messages like join or quit
            special_words = {
                theme.CHAR_JOIN: theme.COLOR_JOIN_CHAR,
                theme.CHAR_QUIT: theme.COLOR_QUIT_CHAR,
                theme.CHAR_KICK: theme.COLOR_KICK_CHAR,
                }
            try:
                splitted = shlex.split(txt)
            except ValueError:
                # FIXME colors are disabled on too long words
                txt = txt.replace('"[', '').replace(']"', '')\
                    .replace('"{', '').replace('}"', '')\
                    .replace('"(', '').replace(')"', '')
                splitted = txt.split()
            for word in splitted:
                if word in list(special_words.keys()):
                    self.addstr(word, curses.color_pair(special_words[word]))
                elif word.startswith('(') and word.endswith(')'):
                    self.addstr('(', curses.color_pair(color))
                    self.addstr(word[1:-1], curses.color_pair(theme.COLOR_CURLYBRACKETED_WORD))
                    self.addstr(')', curses.color_pair(color))
                elif word.startswith('{') and word.endswith('}'):
                    self.addstr(word[1:-1], curses.color_pair(theme.COLOR_ACCOLADE_WORD))
                elif word.startswith('[') and word.endswith(']'):
                    self.addstr(word[1:-1], curses.color_pair(theme.COLOR_BRACKETED_WORD))
                else:
                    self.addstr(word, curses.color_pair(color))
                self.win.addch(' ')

    def write_nickname(self, nickname, color):
        """
        Write the nickname, using the user's color
        and return the number of written characters
        """
        if color:
            self.win.attron(curses.color_pair(color))
        self.addstr(nickname)
        if color:
            self.win.attroff(curses.color_pair(color))
        self.addstr("> ")

    def write_time(self, time):
        """
        Write the date on the yth line of the window
        """
        self.addstr(theme.CHAR_TIME_LEFT, curses.color_pair(theme.COLOR_TIME_LIMITER))
        self.addstr(time.strftime("%H"), curses.color_pair(theme.COLOR_TIME_NUMBERS))
        self.addstr(':', curses.color_pair(theme.COLOR_TIME_SEPARATOR))
        self.addstr(time.strftime("%M"), curses.color_pair(theme.COLOR_TIME_NUMBERS))
        self.addstr(':', curses.color_pair(theme.COLOR_TIME_SEPARATOR))
        self.addstr(time.strftime('%S'), curses.color_pair(theme.COLOR_TIME_NUMBERS))
        self.addnstr(theme.CHAR_TIME_RIGHT, curses.color_pair(theme.COLOR_TIME_LIMITER))
        self.addstr(' ')

    def resize(self, height, width, y, x, stdscr, visible):
        self.visible = visible
        self._resize(height, width, y, x, stdscr, visible)

class Input(Win):
    """
    The line where text is entered
    """
    def __init__(self, height, width, y, x, stdscr, visible):
        self.key_func = {
            "KEY_LEFT": self.key_left,
            "M-D": self.key_left,
            "KEY_RIGHT": self.key_right,
            "M-C": self.key_right,
            "KEY_UP": self.key_up,
            "M-A": self.key_up,
            "KEY_END": self.key_end,
            "KEY_HOME": self.key_home,
            "KEY_DOWN": self.key_down,
            "M-B": self.key_down,
            "KEY_DC": self.key_dc,
            '^D': self.key_dc,
            'M-b': self.jump_word_left,
            '^W': self.delete_word,
            '^K': self.delete_end_of_line,
            '^U': self.delete_begining_of_line,
            '^Y': self.paste_clipboard,
            '^A': self.key_home,
            '^E': self.key_end,
            'M-f': self.jump_word_right,
            "KEY_BACKSPACE": self.key_backspace,
            '^?': self.key_backspace,
            '^J': self.get_text,
            '\n': self.get_text,
            }

        Win.__init__(self, height, width, y, x, stdscr)
        self.visible = visible
        self.history = []
        self.text = ''
        self.clipboard = None
        self.pos = 0            # cursor position
        self.line_pos = 0 # position (in self.text) of
        # the first char to display on the screen
        self.histo_pos = 0
        self.hit_list = [] # current possible completion (normal)
        self.last_completion = None # Contains the last nickname completed,
                                    # if last key was a tab

    def is_empty(self):
        return len(self.text) == 0

    def resize(self, height, width, y, x, stdscr, visible):
        self.visible = visible
        if not visible:
            return
        self._resize(height, width, y, x, stdscr, visible)
        self.win.clear()
        self.addnstr(0, 0, self.text, self.width-1)

    def jump_word_left(self):
        """
        Move the cursor one word to the left
        """
        if not len(self.text) or self.pos == 0:
            return
        previous_space = self.text[:self.pos+self.line_pos].rfind(' ')
        if previous_space == -1:
            previous_space = 0
        diff = self.pos+self.line_pos-previous_space
        for i in range(diff):
            self.key_left()

    def jump_word_right(self):
        """
        Move the cursor one word to the right
        """
        if len(self.text) == self.pos+self.line_pos or not len(self.text):
            return
        next_space = self.text.find(' ', self.pos+self.line_pos+1)
        if next_space == -1:
            next_space = len(self.text)
        diff = next_space - (self.pos+self.line_pos)
        for i in range(diff):
            self.key_right()

    def delete_word(self):
        """
        Delete the word just before the cursor
        """
        if not len(self.text) or self.pos == 0:
            return
        previous_space = self.text[:self.pos+self.line_pos].rfind(' ')
        if previous_space == -1:
            previous_space = 0
        diff = self.pos+self.line_pos-previous_space
        for i in range(diff):
            self.key_backspace(False)
        self.rewrite_text()

    def delete_end_of_line(self):
        """
        Cut the text from cursor to the end of line
        """
        if len(self.text) == self.pos+self.line_pos:
            return              # nothing to cut
        self.clipboard = self.text[self.pos+self.line_pos:]
        self.text = self.text[:self.pos+self.line_pos]
        self.key_end()

    def delete_begining_of_line(self):
        """
        Cut the text from cursor to the begining of line
        """
        if self.pos+self.line_pos == 0:
            return
        self.clipboard = self.text[:self.pos+self.line_pos]
        self.text = self.text[self.pos+self.line_pos:]
        self.key_home()

    def paste_clipboard(self):
        """
        Insert what is in the clipboard at the cursor position
        """
        if not self.clipboard or len(self.clipboard) == 0:
            return
        for letter in self.clipboard:
            self.do_command(letter)

    def key_dc(self):
        """
        delete char just after the cursor
        """
        self.reset_completion()
        if self.pos + self.line_pos == len(self.text):
            return              # end of line, nothing to delete
        self.text = self.text[:self.pos+self.line_pos]+self.text[self.pos+self.line_pos+1:]
        self.rewrite_text()

    def key_up(self):
        """
        Get the previous line in the history
        """
        if not len(self.history):
            return
        self.win.erase()
        if self.histo_pos >= 0:
            self.histo_pos -= 1
        self.text = self.history[self.histo_pos+1]
        self.key_end()

    def key_down(self):
        """
        Get the next line in the history
        """
        if not len(self.history):
            return
        self.reset_completion()
        if self.histo_pos < len(self.history)-1:
            self.histo_pos += 1
            self.text = self.history[self.histo_pos]
            self.key_end()
        else:
            self.histo_pos = len(self.history)-1
            self.text = ''
            self.pos = 0
            self.line_pos = 0
            self.rewrite_text()

    def key_home(self):
        """
        Go to the begining of line
        """
        self.reset_completion()
        self.pos = 0
        self.line_pos = 0
        self.rewrite_text()

    def key_end(self, reset=False):
        """
        Go to the end of line
        """
        if reset:
            self.reset_completion()
        if len(self.text) >= self.width-1:
            self.pos = self.width-1
            self.line_pos = len(self.text)-self.pos
        else:
            self.pos = len(self.text)
            self.line_pos = 0
        self.rewrite_text()

    def key_left(self):
        """
        Move the cursor one char to the left
        """
        self.reset_completion()
        (y, x) = self.win.getyx()
        if self.pos == self.width-1 and self.line_pos > 0:
            self.line_pos -= 1
        elif self.pos >= 1:
            self.pos -= 1
        self.rewrite_text()

    def key_right(self):
        """
        Move the cursor one char to the right
        """
        self.reset_completion()
        (y, x) = self.win.getyx()
        if self.pos == self.width-1:
            if self.line_pos + self.width-1 < len(self.text):
                self.line_pos += 1
        elif self.pos < len(self.text):
            self.pos += 1
        self.rewrite_text()

    def key_backspace(self, reset=True):
        """
        Delete the char just before the cursor
        """
        self.reset_completion()
        (y, x) = self.win.getyx()
        if self.pos == 0:
            return
        self.text = self.text[:self.pos+self.line_pos-1]+self.text[self.pos+self.line_pos:]
        self.key_left()
        if reset:
            self.rewrite_text()

    def auto_completion(self, user_list, add_after=True):
        """
        Complete the nickname
        """
        if self.pos+self.line_pos != len(self.text): # or len(self.text) == 0
            return # we don't complete if cursor is not at the end of line
        completion_type = config.get('completion', 'normal')
        if completion_type == 'shell' and self.text != '':
            self.shell_completion(user_list, add_after)
        else:
            self.normal_completion(user_list, add_after)

    def reset_completion(self):
        """
        Reset the completion list (called on ALL keys except tab)
        """
        self.hit_list = []
        self.last_completion = None

    def normal_completion(self, user_list, add_after):
        """
        Normal completion
        """
        if add_after and (" " not in self.text.strip() or\
                self.last_completion and self.text == self.last_completion+config.get('after_completion', ',')+" "):
            after = config.get('after_completion', ',')+" "
            #if " " in self.text.strip() and (not self.last_completion or ' ' in self.last_completion):
        else:
            after = " " # don't put the "," if it's not the begining of the sentence
        (y, x) = self.win.getyx()
        if not self.last_completion:
            # begin is the begining of the nick we want to complete
            if self.text.strip() != '':
                begin = self.text.split()[-1].lower()
            else:
                begin = ''
            hit_list = []       # list of matching nicks
            for user in user_list:
                if user.lower().startswith(begin):
                    hit_list.append(user)
            if len(hit_list) == 0:
                return
            self.hit_list = hit_list
            end = len(begin)
        else:
            begin = self.text[-len(after)-len(self.last_completion):-len(after)]
            self.hit_list.append(self.hit_list.pop(0)) # rotate list
            end = len(begin) + len(after)
        self.text = self.text[:-end]
        nick = self.hit_list[0] # take the first hit
        self.last_completion = nick
        self.text += nick +after
        self.key_end(False)

    def shell_completion(self, user_list, add_after):
        """
        Shell-like completion
        """
        if " " in self.text.strip() or not add_after:
            after = " " # don't put the "," if it's not the begining of the sentence
        else:
            after = config.get('after_completion', ',')+" "
        (y, x) = self.win.getyx()
        if self.text != '':
            begin = self.text.split()[-1].lower()
        else:
            begin = ''
        hit_list = []       # list of matching nicks
        for user in user_list:
            if user.lower().startswith(begin):
                hit_list.append(user)
        if len(hit_list) == 0:
            return
        end = False
        nick = ''
        last_completion = self.last_completion
        self.last_completion = True
        if len(hit_list) == 1:
            nick = hit_list[0] + after
            self.last_completion = False
        elif last_completion:
            for n in hit_list:
                if begin.lower() == n.lower():
                    nick = n+after # user DO want this completion (tabbed twice on it)
                    self.last_completion = False
        if nick == '':
            while not end and len(nick) < len(hit_list[0]):
                nick = hit_list[0][:len(nick)+1]
                for hit in hit_list:
                    if not hit.lower().startswith(nick.lower()):
                        end = True
                        break
            if end:
                nick = nick[:-1]
        x -= len(begin)
        self.text = self.text[:-len(begin)]
        self.text += nick
        self.key_end(False)

    def do_command(self, key, reset=True):
        if key in self.key_func:
            return self.key_func[key]()
        # if not key or len(key) > 1:
        #     return    # ignore non-handled keyboard shortcuts
        self.reset_completion()
        self.text = self.text[:self.pos+self.line_pos]+key+self.text[self.pos+self.line_pos:]
        (y, x) = self.win.getyx()
        if x == self.width-1:
            self.line_pos += 1
        else:
            self.pos += 1
        if reset:
            self.rewrite_text()

    def get_text(self):
        """
        Clear the input and return the text entered so far
        """
        txt = self.text
        self.text = ''
        self.pos = 0
        self.line_pos = 0
        if len(txt) != 0:
            self.history.append(txt)
            self.histo_pos = len(self.history)-1
        self.rewrite_text()
        return txt

    def rewrite_text(self):
        """
        Refresh the line onscreen, from the pos and pos_line
        """
        with g_lock:
            self.clear_text()
            self.addstr(self.text[self.line_pos:self.line_pos+self.width-1])
            # self.win.chgat(0, self.pos, 1, curses.A_REVERSE)
            self.win.refresh()

    def refresh(self):
        if not self.visible:
            return
        self.rewrite_text()

    def clear_text(self):
        self.win.erase()

class VerticalSeparator(Win):
    """
    Just a one-column window, with just a line in it, that is
    refreshed only on resize, but never on refresh, for efficiency
    """
    def __init__(self, height, width, y, x, parent_win, visible):
        Win.__init__(self, height, width, y, x, parent_win)
        self.visible = visible

    def rewrite_line(self):
        with g_lock:
            self.win.vline(0, 0, curses.ACS_VLINE, self.height, curses.color_pair(theme.COLOR_VERTICAL_SEPARATOR))
            self.win.refresh()

    def resize(self, height, width, y, x, stdscr, visible):
        self.visible = visible
        self._resize(height, width, y, x, stdscr, visible)
        if not visible:
            return

    def refresh(self):
        if not self.visible:
            return
        self.rewrite_line()

class RosterWin(Win):
    color_show = {'xa':theme.COLOR_STATUS_XA,
                  'none':theme.COLOR_STATUS_ONLINE,
                  '':theme.COLOR_STATUS_ONLINE,
                  'available':theme.COLOR_STATUS_ONLINE,
                  'dnd':theme.COLOR_STATUS_DND,
                  'away':theme.COLOR_STATUS_AWAY,
                  'chat':theme.COLOR_STATUS_CHAT,
                  'unavailable': theme.COLOR_STATUS_UNAVAILABLE
                  }
    # subscription_char = {'both': '
    def __init__(self, height, width, y, x, parent_win, visible):
        self.visible = visible
        Win.__init__(self, height, width, y, x, parent_win)
        self.pos = 0            # cursor position in the contact list
        self.start_pos = 1      # position of the start of the display
        self.roster_len = 0
        self.selected_row = None

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)
        self.visible = visible

    def move_cursor_down(self):
        if self.pos < self.roster_len-1:
            self.pos += 1
        if self.pos == self.start_pos-1 + self.height-1:
            self.scroll_down()

    def move_cursor_up(self):
        if self.pos > 0:
            self.pos -= 1
        if self.pos == self.start_pos-2:
            self.scroll_up()

    def scroll_down(self):
        self.start_pos += 8

    def scroll_up(self):
        self.start_pos -= 8

    def refresh(self, roster):
        """
        We get the roster object
        """
        if not self.visible:
            return
        with g_lock:
            self.roster_len = len(roster)
            self.win.erase()
            self.draw_roster_information(roster)
            y = 1
            for group in roster.get_groups():
                if y-1 == self.pos:
                    self.selected_row = group
                if y >= self.start_pos:
                    self.draw_group(y-self.start_pos+1, group, y-1==self.pos)
                y += 1
                if group.folded:
                    continue
                for contact in group.get_contacts():
                    if y-1 == self.pos:
                        self.selected_row = contact
                    if y-self.start_pos+1 == self.height:
                        break
                    if y >= self.start_pos:
                        self.draw_contact_line(y-self.start_pos+1, contact, y-1==self.pos)
                    y += 1
                if y-self.start_pos+1 == self.height:
                    break
            if self.start_pos > 1:
                self.draw_plus(1)
            if self.start_pos + self.height-2 < self.roster_len:
                self.draw_plus(self.height-1)
            self.win.refresh()

    def draw_plus(self, y):
        """
        Draw the indicator that shows that
        the list is longer that what is displayed
        """
        self.win.addstr(y, self.width-5, '++++', curses.color_pair(42))

    def draw_roster_information(self, roster):
        """
        """
        self.win.addstr('%s contacts' % roster.get_contact_len(), curses.color_pair(12))
        self.finish_line(12)

    def draw_group(self, y, group, colored):
        """
        Draw a groupname on a line
        """
        if colored:
            self.win.attron(curses.color_pair(14))
        if group.folded:
            self.addstr(y, 0, '[+] ')
        else:
            self.addstr(y, 0, '[-] ')
        self.addstr(y, 4, group.name)
        if colored:
            self.win.attroff(curses.color_pair(14))

    def draw_contact_line(self, y, contact, colored):
        """
        Draw on a line all informations about one contact
        Use 'color' to draw the jid/display_name to show what is
        is currently selected contact in the list
        """
        color = RosterWin.color_show[contact.get_presence()]
        if contact.get_name():
            display_name = '%s (%s)' % (contact.get_name(),
                                        contact.get_jid().bare)
        else:
            display_name = '%s' % (contact.get_jid().bare,)
        self.win.addstr(y, 1, " ", curses.color_pair(color))
        if colored:
            self.win.addstr(y, 4, display_name, curses.color_pair(14))
        else:
            self.win.addstr(y, 4, display_name)

    def get_selected_row(self):
        return self.selected_row

class ContactInfoWin(Win):
    def __init__(self, height, width, y, x, parent_win, visible):
        self.visible = visible
        Win.__init__(self, height, width, y, x, parent_win)

    def resize(self, height, width, y, x, stdscr, visible):
        self._resize(height, width, y, x, stdscr, visible)
        self.visible = visible

    def draw_contact_info(self, contact):
        """
        draw the contact information
        """
        self.addstr(0, 0, contact.get_jid().full, curses.color_pair(theme.COLOR_INFORMATION_BAR))
        self.addstr(' (%s)'%(contact.get_presence(),), curses.color_pair(theme.COLOR_INFORMATION_BAR))
        self.finish_line(theme.COLOR_INFORMATION_BAR)

    def draw_group_info(self, group):
        """
        draw the group information
        """
        self.addstr(0, 0, group.name, curses.color_pair(theme.COLOR_INFORMATION_BAR))
        self.finish_line(theme.COLOR_INFORMATION_BAR)

    def refresh(self, selected_row):
        if not self.visible:
            return
        with g_lock:
            self.win.erase()
            if isinstance(selected_row, RosterGroup):
                self.draw_group_info(selected_row)
            elif isinstance(selected_row, Contact):
                self.draw_contact_info(selected_row)
            self.win.refresh()
