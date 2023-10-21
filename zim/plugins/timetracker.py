from zim.plugins import PluginClass, find_extension
from zim.plugins.tasklist.gui import TaskListWindowExtension, DESC_COL
from zim.plugins.tasklist import TaskListNotebookViewExtension
from pathlib import Path
import os
from datetime import datetime

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


def write_item_to_tracking_file(line_text):
	print(line_text)
	tracking_file = open(os.path.join(Path.home(), "zim_time_tracker.txt"), "a+")
	tracking_file.write(f"::{str(datetime.now())}:: {line_text}\n")
	tracking_file.flush()


def on_todo_item_selected(treeview, path, _):
	model = treeview.get_model()
	write_item_to_tracking_file(model[path][DESC_COL])


class TimeTrackerTaskListWindowExtension(TaskListWindowExtension):
	def __init__(self, _, window):
		window.tasklisttreeview.connect("row-activated", on_todo_item_selected)
		window.connect("hide", self.__class__.on_hide)

	@staticmethod
	def on_hide(windows, *a):
		write_item_to_tracking_file("__________CLOSING_TASKLIST_WINDOW___________")


class TimeTrackerTaskListWidgetExtension(TaskListNotebookViewExtension):
	def __init__(self, plugin, pageview):
		ext = find_extension(pageview, TaskListNotebookViewExtension)
		ext._widget.tasklisttreeview.connect("row-activated", on_todo_item_selected)

