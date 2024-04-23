# -*- coding: utf-8; -*-
"""
Copyright (C) 2007-2013 Guake authors

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License as
published by the Free Software Foundation; either version 2 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public
License along with this program; if not, write to the
Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor,
Boston, MA 02110-1301 USA
"""
import code
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import uuid

from enum import IntEnum
from pathlib import Path
from typing import Optional
from typing import Tuple
from urllib.parse import unquote
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")  # vte-0.38

from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import Vte

from guake.common import clamp
from guake.globals import QUICK_OPEN_MATCHERS
from guake.globals import TERMINAL_MATCH_EXPRS
from guake.globals import TERMINAL_MATCH_TAGS

# from guake.logging_decorator import logging_decorator
# from guake.logging_decorator import _file_
from guake.logging_decorator import _fl_two_

# from guake.logging_decorator import _line_
from guake.logging_decorator import logger

libutempter = None
try:
    # this allow to run some commands that requires libuterm to
    # be injected in current process, as: wall
    from atexit import register as at_exit_call
    from ctypes import cdll

    libutempter = cdll.LoadLibrary("libutempter.so.0")
    if libutempter is not None:
        # We absolutely need to remove the old tty from the utmp !!!
        at_exit_call(libutempter.utempter_remove_added_record)
except Exception as e:
    libutempter = None
    sys.stderr.write("[WARN] " + "=" * 80 + "\n")
    sys.stderr.write("[WARN] Unable to load the library libutempter !\n")
    sys.stderr.write(
        "[WARN] Some feature might not work:\n"
        "[WARN]  - 'exit' command might freeze the terminal instead of closing the tab\n"
        "[WARN]  - the 'wall' command is known to work badly\n")
    sys.stderr.write("[WARN] Error: " + str(e) + "\n")
    sys.stderr.write("[WARN] " + "=" * 80 + "²\n")


def halt(loc):
    code.interact(local=loc)


__all__ = ["GuakeTerminal"]

# pylint: enable=anomalous-backslash-in-string


class DropTargets(IntEnum):
    URIS = 0
    TEXT = 1


class GuakeTerminal(Vte.Terminal):
    """Just a vte.Terminal with some properties already set."""

    def __init__(self, guake):
        super(GuakeTerminal, self).__init__()
        # super().__init__()
        self._font_scale = None
        self.targets = Gtk.TargetList()
        self.guake = guake
        self.configure_terminal()
        self.add_matches()
        self.handler_ids = []
        self.handler_ids.append(
            self.connect("button-press-event", self.button_press))
        self.connect(
            "child-exited",
            self.on_child_exited)  # Call on_child_exited, don't remove it
        self.connect("selection-changed", self.copy_on_select)
        self.matched_value = ""
        self.font_scale_index = 0
        self._pid = None
        # self.custom_bgcolor = None
        # self.custom_fgcolor = None
        self.found_link = None
        self.uuid = uuid.uuid4()

        # Custom colors
        self.custom_bgcolor = None
        self.custom_fgcolor = None
        self.custom_palette = None

        self.setup_drag_and_drop()
        self.ENVV_EXCLUDE_LIST = ["GDK_BACKEND"]
        self.envv = [
            f"{i}={os.environ[i]}" for i in os.environ
            if i not in self.ENVV_EXCLUDE_LIST
        ]
        self.envv.append(f"GUAKE_TAB_UUID={self.uuid}")

    def setup_drag_and_drop(self):
        self.targets = Gtk.TargetList()
        self.targets.add_uri_targets(DropTargets.URIS)
        self.targets.add_text_targets(DropTargets.TEXT)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_set_target_list(self.targets)
        self.connect("drag-data-received", self.on_drag_data_received)

    def get_uuid(self):
        return self.uuid

    @property
    def pid(self):
        return self._pid

    @pid.setter
    def pid(self, pid):
        self._pid = pid

    def feed_child(self, resolved_cmdline):
        if (Vte.MAJOR_VERSION, Vte.MINOR_VERSION) >= (0, 42):
            encoded = resolved_cmdline.encode("utf-8")
            try:
                super().feed_child_binary(encoded)
            except TypeError:
                # The doc doest not say clearly at which version the feed_child* function has lost
                # the "len" parameter :(
                super().feed_child(resolved_cmdline, len(resolved_cmdline))
        else:
            super().feed_child(resolved_cmdline, len(resolved_cmdline))

    def execute_command(self, command):
        if command[-1] != "\n":
            command += "\n"
        self.feed_child(command)

    def copy_clipboard(self):
        if self.get_has_selection():
            super(GuakeTerminal, self).copy_clipboard()
            # super().copy_clipboard()
        elif self.matched_value:
            guake_clipboard = Gtk.Clipboard.get_default(
                self.guake.window.get_display())
            guake_clipboard.set_text(self.matched_value,
                                     len(self.matched_value))

    def copy_on_select(self, event):
        if self.guake.settings.general.get_boolean(
                "copy-on-select") and self.get_has_selection():
            self.copy_clipboard()

    def configure_terminal(self):
        """Sets all customized properties on the terminal"""
        client = self.guake.settings.general
        word_chars = client.get_string("word-chars")
        if word_chars:
            self.set_word_char_exceptions(word_chars)
        self.set_audible_bell(client.get_boolean("use-audible-bell"))
        self.set_sensitive(True)

        cursor_blink_mode = self.guake.settings.style.get_int(
            "cursor-blink-mode")
        self.set_property("cursor-blink-mode", cursor_blink_mode)

        if (Vte.MAJOR_VERSION, Vte.MINOR_VERSION) >= (0, 50):
            self.set_allow_hyperlink(True)

        if (Vte.MAJOR_VERSION, Vte.MINOR_VERSION) >= (0, 56):
            try:
                self.set_bold_is_bright(
                    self.guake.settings.styleFont.get_boolean(
                        "bold-is-bright"))
            except:  # pylint: disable=bare-except
                logger.error("%s set_bold_is_bright not supported your VTE",
                             _fl_two_())

        # TODO PORT is this still the case with the newer vte version?
        # -- Ubuntu has a patch to libvte which disables mouse scrolling in apps
        # -- like vim and less by default. If this is the case, enable it back.
        if hasattr(self, "set_alternate_screen_scroll"):
            self.set_alternate_screen_scroll(True)

        self.set_can_default(True)
        self.set_can_focus(True)

    def add_matches(self):
        """Adds all regular expressions declared in
        guake.globals.TERMINAL_MATCH_EXPRS to the terminal to make vte
        highlight text that matches them.
        """
        try:
            # NOTE: PCRE2_UTF | PCRE2_NO_UTF_CHECK | PCRE2_MULTILINE
            # reference from vte/bindings/vala/app.vala, flags = 0x40080400u
            # also ref: https://mail.gnome.org/archives/commits-list/2016-September/msg06218.html
            VTE_REGEX_FLAGS = 0x40080400
            for expr in TERMINAL_MATCH_EXPRS:
                tag = self.match_add_regex(
                    Vte.Regex.new_for_match(expr, len(expr), VTE_REGEX_FLAGS),
                    0)
                self.match_set_cursor_type(tag, Gdk.CursorType.HAND2)

            for _useless, match, _other_useless in QUICK_OPEN_MATCHERS:
                tag = self.match_add_regex(
                    Vte.Regex.new_for_match(match, len(match),
                                            VTE_REGEX_FLAGS), 0)
                self.match_set_cursor_type(tag, Gdk.CursorType.HAND2)
        except (GLib.Error, AttributeError):  # pylint: disable=catching-non-exception
            try:
                compile_flag = 0
                if (Vte.MAJOR_VERSION, Vte.MINOR_VERSION) >= (0, 44):
                    compile_flag = GLib.RegexCompileFlags.MULTILINE
                for expr in TERMINAL_MATCH_EXPRS:
                    tag = self.match_add_gregex(
                        GLib.Regex.new(expr, compile_flag, 0), 0)
                    self.match_set_cursor_type(tag, Gdk.CursorType.HAND2)

                for _useless, match, _other_useless in QUICK_OPEN_MATCHERS:
                    tag = self.match_add_gregex(
                        GLib.Regex.new(match, compile_flag, 0), 0)
                    self.match_set_cursor_type(tag, Gdk.CursorType.HAND2)
            except GLib.Error as err:  # pylint: disable=catching-non-exception
                emsg = (
                    "%s ERROR: PCRE2 does not seems to be enabled on your system. "
                    "Quick Edit and other Ctrl+click features are disabled. "
                    "Please update your VTE package or contact your distribution to ask "
                    "to enable regular expression support in VTE. Exception: '%s'"
                )
                logger.error(emsg, _fl_two_(), str(err))

    # @logging_decorator
    def get_current_directory(self):
        # logger.info("%s getcwd %r", _fl_two_(), os.getcwd())
        directory = os.path.expanduser("~")
        # logger.info("%s directory %r", _fl_two_(), directory)
        # logger.info("%s self.pid %r", _fl_two_(), self.pid)
        # logger.info("%s readlink %r", _fl_two_(), os.readlink(f"/proc/{self.pid}/cwd"))
        if self.pid is not None:
            try:
                cwd = os.readlink(f"/proc/{self.pid}/cwd")
            except Exception:
                return directory
            if os.path.exists(cwd):
                directory = cwd
        return directory

    def is_file_on_local_server(
            self, text) -> Tuple[Optional[Path], Optional[int], Optional[int]]:
        """Test if the provided text matches a file on local server

        Supports:
         - absolute path
         - relative path (using current working directory)
         - file:line syntax
         - file:line:column syntax

        Args:
            text (str): candidate for file search

        Returns
            - Tuple(None, None, None) if the provided text does not match anything
            - Tuple(file path, None, None) if only a file path is found
            - Tuple(file path, linenumber, None) if line number is found
            - Tuple(file path, linenumber, columnnumber) if line and column numbers are found
        """
        lineno = None
        colno = None
        py_func = None
        # "<File>:<line>:<col>"
        m = re.compile(r"(.*)\:(\d+)\:(\d+)$").match(text)
        if m:
            text = m.group(1)
            lineno = m.group(2)
            colno = m.group(3)
        else:
            # "<File>:<line>"
            m = re.compile(r"(.*)\:(\d+)$").match(text)
            if m:
                text = m.group(1)
                lineno = m.group(2)
            else:
                # "<File>::<python_function>"
                m = re.compile(r"^(.*)\:\:([a-zA-Z0-9\_]+)$").match(text)
                if m:
                    text = m.group(1)
                    py_func = m.group(2).strip()

        def find_lineno(text_local, pt_local, lineno_local, py_func_local):
            # print("text={!r}, pt={!r}, lineno={!r}, py_func={!r}".format(text,
            #                                                              pt, lineno, py_func))
            if lineno_local:
                return lineno_local
            if not py_func_local:
                return
            with pt_local.open() as f:
                for i, line in enumerate(f.readlines()):
                    if line.startswith(f"def {py_func_local}"):
                        return i + 1

        pt = Path(text)
        logger.debug("%s checking file existance: %r", _fl_two_(), pt)
        try:
            if pt.exists():
                lineno = find_lineno(text, pt, lineno, py_func)
                logger.info("%s File exists: %r, line=%r", _fl_two_(),
                            pt.absolute().as_posix(), lineno)
                return pt, lineno, colno
            logger.debug("%s No file found matching: %r", _fl_two_(), text)
            cwd = self.get_current_directory()
            pt = Path(cwd) / pt
            logger.debug("%s checking file existance: %r", _fl_two_(), pt.realpath())
            if pt.exists():
                lineno = find_lineno(text, pt, lineno, py_func)
                logger.info("%s File exists: %r, line=%r", _fl_two_(),
                            pt.absolute().as_posix(), lineno)
                return pt, lineno, colno
            logger.debug("%s file does not exist: %s", _fl_two_(), str(pt))
        except OSError:
            logger.debug("%s not a file name: %r", _fl_two_(), text)
        return None, None, None

    def button_press(self, terminal, event):
        """Handles the button press event in the terminal widget. If
        any match string is caught, another application is open to
        handle the matched resource uri.
        """
        self.matched_value = ""
        if (Vte.MAJOR_VERSION, Vte.MINOR_VERSION) >= (0, 46):
            matched_string = self.match_check_event(event)
        else:
            matched_string = self.match_check(
                int(event.x / self.get_char_width()),
                int(event.y / self.get_char_height()),
            )

        self.found_link = None

        if event.button == 1 and (event.get_state()
                                  & Gdk.ModifierType.CONTROL_MASK):
            if (Vte.MAJOR_VERSION, Vte.MINOR_VERSION) > (0, 50):
                s = self.hyperlink_check_event(event)
            else:
                s = None
            if s is not None:
                self._on_ctrl_click_matcher((s, None))
            elif self.get_has_selection():
                self.quick_open()
            elif matched_string and matched_string[0]:
                self._on_ctrl_click_matcher(matched_string)
        elif event.button == 3 and matched_string:
            self.found_link = self.handle_terminal_match(matched_string)
            self.matched_value = matched_string[0]

    def on_child_exited(self, target, status, *user_data):
        if libutempter is not None:
            if self.get_pty() is not None:
                libutempter.utempter_remove_record(self.get_pty().get_fd())

    def on_drag_data_received(self, widget, drag_context, x, y, data, info,
                              time):
        if info == DropTargets.URIS:
            uris = data.get_uris()
            for uri in uris:
                path = Path(unquote(urlparse(uri).path))
                self.feed_child(shlex.quote(str(path.absolute())) + " ")
        elif info == DropTargets.TEXT:
            text = data.get_text()
            if text:
                self.feed_child(text)

    def quick_open(self):
        self.copy_clipboard()
        project_cwd = self.get_current_directory()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        if not text:
            return
        (fp, lo, co) = self.is_file_on_local_server(text)
        self._execute_quick_open(fp, lo, project_cwd)

    def _on_ctrl_click_matcher(self, matched_string):
        value, tag = matched_string
        found_matcher = False
        project_cwd = self.get_current_directory()
        logger.debug("%s _on_ctrl_click_matcher() project_cwd: %s", _fl_two_(), project_cwd)
        logger.debug("%s _on_ctrl_click_matcher() matched string: %s", _fl_two_(), matched_string)
        # First searching in additional matchers
        use_quick_open = self.guake.settings.general.get_boolean(
            "quick-open-enable")
        if use_quick_open:
            found_matcher = self._find_quick_matcher(value, project_cwd)
        if not found_matcher:
            self.found_link = self.handle_terminal_match(matched_string)
            if self.found_link:
                self.browse_link_under_cursor()

    def _find_quick_matcher(self, value, project_cwd):
        for _useless, _other_useless, extractor in QUICK_OPEN_MATCHERS:
            try:
                g = re.compile(extractor).match(value)
            except:
                return False

            if g and g.groups():
                filename = g.group(1).strip()
                if len(g.groups()) >= 2:
                    line_number = g.group(2)
                else:
                    line_number = None
                logger.info("%s _find_quick_matcher() Quick action executed filename=%s, line=%s",
                            _fl_two_(), project_cwd + "/" + filename, line_number)
                (filepath, ln, _) = self.is_file_on_local_server(project_cwd + "/" + filename)
                if ln:
                    line_number = ln
                if not filepath:
                    continue
                if line_number is None:
                    line_number = "1"

                return self._execute_quick_open(filepath, line_number, project_cwd)
                # return True
        return False

    def check_file_writable(self, fnm):
        if os.path.exists(fnm):
            logger.info("%s os.path.exist ", _fl_two_())
            # path exists
            if os.path.isfile(fnm):  # is it a file or a dir?
                # also works when file is a link and the target is writable
                logger.info("%s os.path.isfile ", _fl_two_())
                # also works when file is a link and the target is readable
                if os.access(fnm, os.W_OK):
                    logger.info("%s os.access ", _fl_two_())
                else:
                    logger.info("%s not os.access ", _fl_two_())
                return os.access(fnm, os.W_OK)
            else:
                logger.info("%s not os.path.isfile ", _fl_two_())
                return False  # path is a dir, so cannot write as a file
        # target does not exist, check perms on parent dir
        pdir = os.path.dirname(fnm)
        if not pdir:
            pdir = '.'
        # target is creatable if parent dir is writable
        logger.info("%s os.path.isfile ", _fl_two_())
        # also works when file is a link and the target is readable
        if os.access(pdir, os.W_OK):
            logger.info("%s os.access dir ", _fl_two_())
        else:
            logger.info("%s not os.access dir ", _fl_two_())
        return os.access(pdir, os.W_OK)

    def check_file_readable(self, fnm):
        if os.path.exists(fnm):
            logger.info("%s os.path.exist ", _fl_two_())
            # path exists
            if os.path.isfile(fnm):  # is it a file or a dir?
                logger.info("%s os.path.isfile ", _fl_two_())
                # also works when file is a link and the target is readable
                if os.access(fnm, os.R_OK):
                    logger.info("%s os.access ", _fl_two_())
                else:
                    logger.info("%s not os.access ", _fl_two_())
                return os.access(fnm, os.R_OK)
            else:
                logger.info("%s not os.path.isfile ", _fl_two_())
                return False  # path is a dir, so cannot read as a file
        logger.info("%s not os.path.exist	", _fl_two_())
        # target does not exist, check perms on parent dir
        return False

    def _execute_quick_open(self, filepath, line_number, project_cwd):
        if not filepath:
            return False
        pt = Path(filepath)
        log.debug("_execute_quick_open checking file existance: %r", pt)
        try:
            file_path_exists = pt.exists()
        except:
            file_path_exists = False
        if not file_path_exists:
            # self.browse_link_under_cursor()
            return False
        file_pathpathpath = pt.absolute().as_posix()
        if not file_pathpathpath:
            return False
        log.info("_execute_quick_open File exists: %r, line=%r", file_pathpathpath, line_number)
        logging.debug("_find_quick_matcher() Current working directory %s ", projectcwd)
        logging.debug("_find_quick_matcher() Opening filepath:%s file_pathpathpath:%s at line %s",
                      filepath, file_pathpathpath, line_number)
        if not self.check_file_readable(file_pathpathpath):
            logger.error("%s _find_quick_matcher() Not found path: %s . so cannot read as a file ",
                         _fl_two_(), file_pathpathpath)
            return False

        cmdline = self.guake.settings.general.get_string(
            "quick-open-command-line")
        if not line_number:
            line_number = ""
        else:
            line_number = str(line_number)

        logger.debug("%s  _execute_quick_open() Opening file %s at line %s", _fl_two_(), filepath, line_number)
        resolved_cmdline = cmdline % {
            "file_path": filepath,
            "line_number": line_number
        }
        logger.debug("%s _execute_quick_open() Command line resolved_cmdline: %s", _fl_two_(), resolved_cmdline)
        quick_open_in_current_terminal = self.guake.settings.general.get_boolean(
            "quick-open-in-current-terminal")
        # Execute open file both
        if quick_open_in_current_terminal:
            logger.debug("%s Executing it in current tab", _fl_two_())
            if resolved_cmdline[-1] != "\n":
                resolved_cmdline += "\n"
            self.feed_child(resolved_cmdline)
            return True
        else:
            logger.debug("%s Executing it independently", _fl_two_())
            resolved_cmdline = "cd  " + project_cwd + " && " + resolved_cmdline + " "
            # resolved_cmdline += " &"
            # logger.debug(f"{_fl_two_()} Opening new tab QUICKOPEN to execute")
            # resolved_cmdline = "guake -n guake -e \"\"\""
            # + resolved_cmdline + "\"\"\" guake -r 'QUICKOPEN' & "
            logger.debug("%s Command line new: %s", _fl_two_(),
                         resolved_cmdline)
            subprocess.call(resolved_cmdline, shell=True)
            devnull = open(os.devnull, 'wb')  # Use this in Python < 3.3
            # Python >= 3.3 has subprocess.DEVNULL
            # with subprocess.Popen(['nohup', resolved_cmdline], shell=True, stdout=devnull, stderr=devnull):
            # os.system(resolved_cmdline)
            # with subprocess.call(resolved_cmdline, shell=True, stdout=devnull, stderr=devnull):
            with subprocess.Popen(
                ['nohup', 'xdotool search --name weise windowactivate'],
                    shell=False,
                    stdout=devnull,
                    stderr=devnull):
                pass
            return True
        return False

    @staticmethod
    def handle_terminal_match(matched_string):
        value, tag = matched_string
        logger.debug("%s found tag: %r, item: %r", _fl_two_(), tag, value)
        if tag in TERMINAL_MATCH_TAGS:
            if TERMINAL_MATCH_TAGS[tag] == "schema":
                # value here should not be changed, it is right and
                # ready to be used.
                pass
            elif TERMINAL_MATCH_TAGS[tag] == "http":
                value = f"http://{value}"
            elif TERMINAL_MATCH_TAGS[tag] == "https":
                value = f"https://{value}"
            elif TERMINAL_MATCH_TAGS[tag] == "ftp":
                value = f"ftp://{value}"
            elif TERMINAL_MATCH_TAGS[tag] == "email":
                value = f"mailto:{value}"

        if value:
            return value

    def get_link_under_cursor(self):
        return self.found_link

    def browse_link_under_cursor(self):
        # TODO move the call to xdg-open to guake.utils
        if not self.found_link:
            return
        logger.debug("%s Opening link: %s", _fl_two_(), self.found_link)
        cmd = ["xdg-open", self.found_link]
        devnull = open(os.devnull, 'wb')  # Use this in Python < 3.3
        # Python >= 3.3 has subprocess.DEVNULL
        with subprocess.Popen(['nohup', cmd],
                              shell=False,
                              stdout=devnull,
                              stderr=devnull):
            pass
        # subprocess.Popen(cmd, shell=False)
        # with subprocess.Popen(cmd, shell=False):
        #    pass

    def set_font(self, font):
        self.font = font
        self.set_font_scale_index(0)

    def set_font_scale_index(self, scale_index):
        self.font_scale_index = clamp(scale_index, -6, 12)

        font = Pango.FontDescription(self.font.to_string())
        scale_factor = 2**(self.font_scale_index / 6)
        new_size = int(scale_factor * font.get_size())

        if font.get_size_is_absolute():
            font.set_absolute_size(new_size)
        else:
            font.set_size(new_size)

        super(GuakeTerminal, self).set_font(font)
        # super().set_font(font)

    font_scale = property(fset=set_font_scale_index,
                          fget=lambda self: self.font_scale_index)

    def increase_font_size(self):
        self.font_scale += 1

    def decrease_font_size(self):
        self.font_scale -= 1

    def kill(self):
        pid = self.pid
        threading.Thread(target=self.delete_shell, args=(pid, )).start()
        # start_new_thread(self.delete_shell, (pid,))

    @staticmethod
    def delete_shell(pid):
        """Kill the shell with SIGHUP

        NOTE: Leave it alone, DO NOT USE os.waitpid

        > sys:1: Warning: GChildWatchSource: Exit status of a child process was requested but
                 ECHILD was received by waitpid(). See the documentation of
                 g_child_watch_source_new() for possible causes.

        g_child_watch_source_new() documentation:
            https://developer.gnome.org/glib/stable/glib-The-Main-Event-Loop.html#g-child-watch-source-new

        On POSIX platforms, the following restrictions apply to this API due to limitations
        in POSIX process interfaces:
            ...
            * the application must not wait for pid to exit by any other mechanism,
              including waitpid(pid, ...) or a second child-watch source for the same pid
            ...
        For this reason, we should not call os.waitpid(pid, ...), leave it to OS
        """
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass

    def spawn_sync_pid(self, directory=None, terminal=None):

        argv = []
        user_shell = self.guake.settings.general.get_string("default-shell")
        if user_shell and os.path.exists(user_shell):
            argv.append(user_shell)
        else:
            # argv.append(os.environ["SHELL"])
            try:
                argv.append(os.environ["SHELL"])
            except KeyError:
                argv.append("/usr/bin/bash")

        login_shell = self.guake.settings.general.get_boolean(
            "use-login-shell")
        if login_shell:
            argv.append("--login")

        logger.debug("%s Spawn command: %s", _fl_two_(), " ".join(argv))

        pid = self.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            directory,
            argv,
            # [],
            self.envv,
            # ["GUAKE_TAB_UUID={}".format(self.uuid)],
            # GLib.SpawnFlags.DO_NOT_REAP_CHILD,
            GLib.SpawnFlags(Vte.SPAWN_NO_PARENT_ENVV),
            None,
            None,
            None,
        )
        try:
            tuple_type = gi._gi.ResultTuple  # pylint: disable=c-extension-no-member
        except:  # pylint: disable=bare-except
            tuple_type = tuple
        if isinstance(pid, (tuple, tuple_type)):
            # Return a tuple in 2.91
            # https://lazka.github.io/pgi-docs/Vte-2.91/classes/Terminal.html#Vte.Terminal.spawn_sync
            pid = pid[1]
        assert isinstance(pid, int)
        # if not isinstance(pid, int):
        #    raise TypeError("pid must be an int")

        if libutempter is not None:
            libutempter.utempter_add_record(self.get_pty().get_fd(),
                                            os.uname()[1])
        self.pid = pid
        return pid

    def set_color_foreground(self, font_color, *args, **kwargs):
        real_fgcolor = self.custom_fgcolor if self.custom_fgcolor else font_color
        super(GuakeTerminal,
              self).set_color_foreground(real_fgcolor, *args, **kwargs)
        # super().set_color_foreground(real_fgcolor, *args, **kwargs)

    def set_color_background(self, bgcolor, *args, **kwargs):
        real_bgcolor = self.custom_bgcolor if self.custom_bgcolor else bgcolor
        super(GuakeTerminal,
              self).set_color_background(real_bgcolor, *args, **kwargs)
        # super().set_color_background(real_bgcolor, *args, **kwargs)

    def set_color_bold(self, font_color, *args, **kwargs):
        real_fgcolor = self.custom_fgcolor if self.custom_fgcolor else font_color
        super(GuakeTerminal, self).set_color_bold(real_fgcolor, *args,
                                                  **kwargs)
        # super().set_color_bold(real_fgcolor, *args, **kwargs)

    def set_colors(self, font_color, bg_color, palette_list, *args, **kwargs):
        real_bgcolor = self.custom_bgcolor if self.custom_bgcolor else bg_color
        real_fgcolor = self.custom_fgcolor if self.custom_fgcolor else font_color
        real_palette = self.custom_palette if self.custom_palette else palette_list
        super(GuakeTerminal, self).set_colors(real_fgcolor, real_bgcolor,
                                              real_palette, *args, **kwargs)
        # super().set_colors(real_fgcolor, real_bgcolor, real_palette, *args, **kwargs)

    def set_color_foreground_custom(self, fgcolor, *args, **kwargs):
        """Sets custom foreground color for this terminal"""
        print(f"set_color_foreground_custom: {self.uuid}")
        self.custom_fgcolor = fgcolor
        super(GuakeTerminal,
              self).set_color_foreground(self.custom_fgcolor, *args, **kwargs)
        # super().set_color_foreground(self.custom_fgcolor, *args, **kwargs)

    def set_color_background_custom(self, bgcolor, *args, **kwargs):
        """Sets custom background color for this terminal"""
        self.custom_bgcolor = bgcolor
        super(GuakeTerminal,
              self).set_color_background(self.custom_bgcolor, *args, **kwargs)
        # super().set_color_background(self.custom_bgcolor, *args, **kwargs)

    def reset_custom_colors(self):
        self.custom_fgcolor = None
        self.custom_bgcolor = None
        self.custom_palette = None

    @staticmethod
    def _color_to_list(color):
        """This method is used for serialization."""
        if color is None:
            return None
        return [color.red, color.green, color.blue, color.alpha]

    @staticmethod
    def _color_from_list(color_list):
        """This method is used for deserialization."""
        return Gdk.RGBA(
            red=color_list[0],
            green=color_list[1],
            blue=color_list[2],
            alpha=color_list[3],
        )

    def get_custom_colors_dict(self):
        """Returns dictionary of custom colors."""
        return {
            "fg_color":
            self._color_to_list(self.custom_fgcolor),
            "bg_color":
            self._color_to_list(self.custom_bgcolor),
            "palette":
            [self._color_to_list(col)
             for col in self.custom_palette] if self.custom_palette else None,
        }

    def set_custom_colors_from_dict(self, colors_dict):
        if not isinstance(colors_dict, dict):
            return

        bg_color = colors_dict.get("bg_color", None)
        if isinstance(bg_color, list):
            self.custom_bgcolor = self._color_from_list(bg_color)
        else:
            self.custom_bgcolor = None

        fg_color = colors_dict.get("fg_color", None)
        if isinstance(fg_color, list):
            self.custom_fgcolor = self._color_from_list(fg_color)
        else:
            self.custom_fgcolor = None

        palette = colors_dict.get("palette", None)
        if isinstance(palette, list):
            self.custom_palette = [
                self._color_from_list(col) for col in palette
            ]
        else:
            self.custom_palette = None

    @font_scale.setter
    def font_scale(self, value):
        self._font_scale = value

    @font_scale.setter
    def font_scale(self, value):
        pass
