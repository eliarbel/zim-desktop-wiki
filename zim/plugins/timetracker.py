from zim.plugins import PluginClass, find_extension
from zim.plugins.tasklist.gui import TaskListWindowExtension, DESC_COL
from zim.plugins.tasklist import TaskListNotebookViewExtension
from pathlib import Path
import os
from datetime import datetime
from html.parser import HTMLParser
import atexit

import logging

logger = logging.getLogger("zim.plugins.timetracker")


class TimeTrackerPlugin(PluginClass):
	plugin_info = {
		'name': _('Time Tracker'),  # T: plugin name
		'description': _('This plugin extends the taskbar plugin to enable tracking .'
						 'time spent on each task. '),  # T: plugin description
		'author': 'Eli Arbel <eliarbel@gmail.com>',
		'help': 'Plugins:Time Tracker',
	}


class StripHTML(HTMLParser):
	def __init__(self, *, convert_charrefs=True):
		super().__init__(convert_charrefs=convert_charrefs)
		self._raw_data = ""

	def handle_data(self, data: str) -> None:
		self._raw_data += data

	@property
	def raw_data(self):
		return self._raw_data

def write_item_to_tracking_file(line_text):
	striper = StripHTML()
	striper.feed(line_text)

	tracking_file = open(os.path.join(Path.home(), "zim_time_tracker.txt"), "a+")
	tracking_file.write(f"::{datetime.now().isoformat(timespec='seconds', sep=' ')}:: {striper.raw_data}\n")
	tracking_file.flush()


def on_todo_item_selected(treeview, path, _):
	model = treeview.get_model()
	write_item_to_tracking_file(model[path][DESC_COL])

def on_exit():
	write_item_to_tracking_file("__________END_SESSION___________")


class TimeTrackerTaskListWindowExtension(TaskListWindowExtension):
	def __init__(self, _, window):
		window.tasklisttreeview.connect("row-activated", on_todo_item_selected)


class TimeTrackerTaskListWidgetExtension(TaskListNotebookViewExtension):
	def __init__(self, plugin, pageview):
		ext = find_extension(pageview, TaskListNotebookViewExtension)
		ext._widget.tasklisttreeview.connect("row-activated", on_todo_item_selected)
		atexit.register(on_exit)
