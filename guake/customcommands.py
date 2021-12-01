import json
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# from guake.logging_decorator import logging_decorator
# from guake.logging_decorator import _file_
from guake.logging_decorator import _fl_two_

# from guake.logging_decorator import _line_
from guake.logging_decorator import logger


class CustomCommands:
    """
    Example for a custom commands file
        [
            {
                "type": "menu",
                "description": "dir listing",
                "items": [
                    {
                        "description": "la",
                        "cmd":["ls", "-la"]
                    },
                    {
                        "description": "tree",
                        "cmd":["tree", ""]
                    }
                ]
            },
            {
                "description": "less ls",
                "cmd": ["ls | less", ""]
            }
        ]
    """

    def __init__(self, settings, callback):
        self.settings = settings
        self.callback = callback

    def should_load(self):
        file_path = self.settings.general.get_string("custom-command-file")
        return file_path is not None

    def get_file_path(self):
        return os.path.expanduser(self.settings.general.get_string("custom-command-file"))

    def _load_json(self, file_name):
        logger.info("%s Loading menu json file::: %s", _fl_two_(), file_name)
        if not os.path.exists(file_name):
            logger.error("%s Custom file does not exit: %s", _fl_two_(), file_name)
            return None
        try:
            with open(file_name, encoding="utf-8") as f:
                data_file = f.read()
                return json.loads(data_file)
        except Exception as e:
            logger.exception("%s Invalid custom command file %s. Exception: %s", _fl_two_(), file_name, str(e))

    def build_menu(self):
        if not self.should_load():
            return None
        menu = Gtk.Menu()
        logger.info("%s Loading session json file: %s", _fl_two_(), self.get_file_path())
        cust_comms = self._load_json(self.get_file_path())
        if not cust_comms:
            return None
        for obj in cust_comms:
            try:
                self._parse_custom_commands(obj, menu)
            except AttributeError:
                logger.error("%s Loading session json file: %s", _fl_two_(), self.get_file_path())
                logger.error("%s _parse_custom_commands parsing type: %s", _fl_two_(), type(obj))
                logger.error("%s _parse_custom_commands parsing json: %s", _fl_two_(), obj)
                # AttributeError: 'str' object has no attribute 'get', ignore and move on
                pass

        return menu

    def _parse_custom_commands(self, json_object, menu):
        logger.info("%s _parse_custom_commands parsing type: %s", _fl_two_(), type(json_object))
        logger.info("%s _parse_custom_commands parsing json: %s", _fl_two_(), json_object)
        if json_object.get("type") == "menu":
            newmenu = Gtk.Menu()
            newmenuitem = Gtk.MenuItem(json_object["description"])
            newmenuitem.set_submenu(newmenu)
            newmenuitem.show()
            menu.append(newmenuitem)
            for item in json_object["items"]:
                self._parse_custom_commands(item, newmenu)
        else:
            menu_item = Gtk.MenuItem(json_object["description"])
            custom_command = ""
            space = ""
            for command in json_object["cmd"]:
                custom_command += space + command
                space = " "
            menu_item.connect("activate", self.on_menu_item_activated, custom_command)
            menu.append(menu_item)
            menu_item.show()

    def on_menu_item_activated(self, item, cmd):
        self.callback.on_command_selected(cmd)
