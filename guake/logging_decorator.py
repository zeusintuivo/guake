# Solution:
#
# Try this:
#
# app.py:
#
# from decorators import logging_decorator
#
# @logging_decorator
# def app():
#     a
#
# app()
#
# decorators.py:

import inspect
import logging
import os

from pathlib import Path
from typing import Any

xdg_config_home: str = os.environ.get("XDG_CONFIG_HOME",
                                      os.path.expandvars("$HOME/.config"))


def get_xdg_config_directory():
    return Path(xdg_config_home, "guake").expanduser()


# Create a custom logger

logger = logging.getLogger(__name__)

# Create handlers
c_handler = logging.StreamHandler()
# os.path.expandvars("$HOME/.config/guake/")
# f_handler = logging.FileHandler(os.path.expandvars(xdg_config_home + "guake.log"))
# f_handler = logging.FileHandler(os.path.expandvars("$HOME/.config/guake") + "/guake.log")
c_handler.setLevel(logging.WARNING)
# f_handler.setLevel(logging.ERROR)

# formatter = logging.Formatter('%(levelname)s - File %(real_pathname)s,'
#                               ' line %(real_lineno)s, %(real_funcName)s: %(message)s')
#
# console_handle = logging.StreamHandler()
# console_handle.setFormatter(formatter)
# logger.addHandler(console_handle)

# def logging_decorator(func):
#   def error_log():
#     try:
#       func()
#     except Exception as err:
#       logger.error(err,
# path to source file
#          extra={'real_pathname': inspect.getsourcefile(func),
# line number from trace
#          'real_lineno': inspect.trace()[-1][2],
# function name
#          'real_funcName': func.__name__})
#
#     return error_log


def _line_():
    """Returns the current line number in our program."""
    return str(inspect.currentframe().f_back.f_lineno)


def _file_():
    return str(__file__)


def _fl_():
    return f"{_file_()}:{_line_()}"


def _line_two_():
    """Returns the current line number in our program."""
    return str(inspect.currentframe().f_back.f_back.f_lineno)


def _file_two_():
    return str(inspect.currentframe().f_back.f_back.f_code.co_filename)
    # return str(__file__)


def _fl_two_():
    return f"{_file_two_()}:{_line_two_()}".replace(
        "/usr/local/lib64/python3.10/site-packages/",
        "/home/zeus/_/software/guake/")


def _line_three_():
    """Returns the current line number in our program."""
    return str(inspect.currentframe().f_back.f_back.f_back.f_lineno)


def _file_three_():
    return str(inspect.currentframe().f_back.f_back.f_back.f_code.co_filename)
    # return str(__file__)


def _fl_three_():
    return f"{_file_three_()}:{_line_three_()}"


def _line_four_():
    """Returns the current line number in our program."""
    return str(inspect.currentframe().f_back.f_back.f_back.f_back.f_lineno)


def _file_four_():
    return str(
        inspect.currentframe().f_back.f_back.f_back.f_back.f_code.co_filename)
    # return str(__file__)


def _fl_four_():
    return f"{_file_four_()}:{_line_four_()}"


BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

# The background is set with 40 plus the number of the color, and the foreground with 30

# These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"


def formatter_message(message, use_color=True):
    if use_color:
        message = message.replace("$RESET",
                                  RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        message = message.replace("$RESET", "").replace("$BOLD", "")
    return message


COLORS = {
    "WARNING": YELLOW,
    "INFO": WHITE,
    "DEBUG": BLUE,
    "CRITICAL": YELLOW,
    "ERROR": RED
}


class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color=True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        level_name = record.levelname
        if self.use_color and level_name in COLORS:
            level_name_color = COLOR_SEQ % (
                30 + COLORS[level_name]) + level_name + RESET_SEQ
            record.levelname = level_name_color
        # file_name = record.filename
        # if file_name:
        #     file_name_path = os.path.expandvars(
        #         "$HOME/_/software/guake/guake/") + file_name
        #     record.filename = file_name_path
        #     line_no = record.lineno
        #     if line_no:
        #         spacer = ' ' * (abs(20 - len(file_name)) + 1)
        #         line_no_with_spacer = str(line_no) + spacer
        #         record.line_no_with_spacer = line_no_with_spacer
        return logging.Formatter.format(self, record)


# Custom logger class with multiple destinations
class ColoredLogger(logging.Logger):
    # real_pathname = _file_()
    # real_pathname = inspect.getsourcefile(caller)
    # FORMAT = "%(message)s [$BOLD%(name)-20s$RESET][%(levelname)-18s]
    #              ($BOLD%(filename)s$RESET:%(lineno)d)"
    # FORMAT = "%(pathname)s:%(lineno)d
    #               ($HOME/_/software/guake/$BOLD%(filename)s$RESET) %(message)s "
    # spacer = _file_()
    FORMAT = "%(filename)s:%(lineno)s %(levelname)-5s %(message)s "
    # FORMAT = "%(real_pathname)s:%(lineno)d) %(message)s
    #               [$BOLD%(name)-20s$RESET][%(levelname)-18s] "
    COLOR_FORMAT = formatter_message(FORMAT, True)

    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)

        color_formatter = ColoredFormatter(self.COLOR_FORMAT)

        console = logging.StreamHandler()
        console.setFormatter(color_formatter)

        self.addHandler(console)


# Create formatters and add it to handlers
logging.setLoggerClass(ColoredLogger)
# c_format = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
c_format = logging.Formatter(
    "%(filename)s:%(lineno)s %(levelname)-5s %(message)s ")
# c_format = logging.setLoggerClass(ColoredLogger)
# f_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
c_handler.setFormatter(c_format)
# f_handler.setFormatter(f_format)

# Add handlers to the logger
logger.addHandler(c_handler)
# logger.addHandler(f_handler)
