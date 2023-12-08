from zim.plugins import PluginClass, find_extension
from zim.plugins.tasklist.gui import TaskListWindowExtension, DESC_COL, PAGE_COL
from zim.plugins.tasklist import TaskListNotebookViewExtension
from pathlib import Path
import os
from datetime import datetime, timedelta
from html.parser import HTMLParser
import atexit
import re

import logging

logger = logging.getLogger("zim.plugins.timetracker")


class TimeTrackerPlugin(PluginClass):
	plugin_info = {
		'name': _('Time Tracker'),  # T: plugin name
		'description': _('This plugin extends the taskbar plugin to enable tracking .'
						 'the time spent on each task. '),  # T: plugin description
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

	with open(os.path.join(Path.home(), "zim_time_tracker.txt"), "a+", encoding="utf-8") as tracking_file:
		tracking_file.write(f"::{datetime.now().isoformat(timespec='seconds', sep=' ')}:: {striper.raw_data}\n")

def on_todo_item_selected(treeview, path, _):
	model = treeview.get_model()
	write_item_to_tracking_file(f"{model[path][DESC_COL]} :: {model[path][PAGE_COL]}")

def end_session():
	write_item_to_tracking_file("__________END_SESSION___________")

def on_exit():
	end_session()

def po_toggled(b):
	if not b.get_active(): # Meaning it was toggled
		end_session()

def show_report(b):
	win = TimeTrackerReportWindow()
	win.show_all()

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class TimeTrackerReportWindow(Gtk.Window):
	def __init__(self):
		super().__init__(title="Zim Time Tracker Report visualizer")

		self.initialize_layout()
		self.set_default_size(1200, 700)

		self._raw_entries = self.load_raw_data() #TODO: rename to raw_data
		self.update_filtered_data()

		self.show_by_task_report()

	def show_by_task_report(self):
		self._treeview.show_report(self._filtered_data, self._bar)

	def update_filtered_data(self):
		self._filtered_data = self.filter_raw_data(self._raw_entries)

	def initialize_layout(self):
		box_range = Gtk.VBox()
		box_range.pack_start(Gtk.Label(label="Range Presets:"), False, False, 0)
		date_preset_box = Gtk.ComboBoxText()
		for r in ["This Week", "Last Week", "Today", "Yesterday"]:
			date_preset_box.append_text(r)

		date_preset_box.connect("changed", self.on_date_preset_changed)
		box_range.pack_start(date_preset_box, False, False, 3)

		box = Gtk.HBox()
		box.pack_start(Gtk.Button(label="Cal>"), False, False, 3)
		self._from_date = Gtk.Entry()
		box.pack_start(self._from_date, False, False, 3)
		box_from_date = Gtk.VBox()
		box_from_date.pack_start(Gtk.Label(label="From Date (dd/mm/yyyy):"), False, False, 0)
		box_from_date.pack_start(box, False, False, 3)

		box = Gtk.HBox()
		box.pack_start(Gtk.Button(label="Cal>"), False, False, 3)
		self._to_date = Gtk.Entry()
		box.pack_start(self._to_date, False, False, 3)
		box_to_date = Gtk.VBox()
		box_to_date.pack_start(Gtk.Label(label="To Date (dd/mm/yyyy):"), False, True, 0)
		box_to_date.pack_start(box, False, False, 3)

		box_search = Gtk.VBox()
		box_search.pack_start(Gtk.Label(label="Filter:"), False, True, 0)
		self._searchentry = Gtk.SearchEntry()
		self._searchentry.connect("search-changed", self.on_search_entry_edited)
		box_search.pack_start(self._searchentry, True, True, 3)

		box_top_strip = Gtk.HBox()
		box_top_strip.pack_start(box_range, False, True, 3)
		box_top_strip.pack_start(box_from_date, False, True, 3)
		box_top_strip.pack_start(box_to_date, False, True, 3)
		clear_all = Gtk.Button(label="Clear All")
		clear_all.connect("clicked", self.on_clear_all)
		box_top_strip.pack_start(clear_all, False, True, 3)
		box_top_strip.pack_end(box_search, True, True, 3)

		box_main_vbox = Gtk.VBox()
		box_main_vbox.pack_start(box_top_strip, False, False, 0)

		# setting up the layout, putting the treeview in a scrollwindow
		scrollable_treeview = Gtk.ScrolledWindow()
		scrollable_treeview.set_vexpand(True)

		self._treeview = ByTaskTreeView()
		scrollable_treeview.add(self._treeview)

		notebook = Gtk.Notebook()
		notebook.append_page(scrollable_treeview, Gtk.Label(label="By Task"))
		notebook.append_page(Gtk.Label(label="Place holder"), Gtk.Label(label="By Tag"))
		notebook.append_page(Gtk.Label(label="Place holder"), Gtk.Label(label="By Day"))
		notebook.append_page(Gtk.Label(label="Place holder"), Gtk.Label(label="Log File"))
		box_main_vbox.pack_start(notebook, True, True, 0)

		self._bar = Gtk.Statusbar()
		box_main_vbox.pack_end(self._bar, False, False, 0)

		self.add(box_main_vbox)

	def on_clear_all(self, button):
		self._from_date.set_text("")
		self._to_date.set_text("")
		self._searchentry.set_text("")
		self.update_filtered_data()
		self.show_by_task_report()

	def on_search_entry_edited(self, widget):
		self.update_filtered_data()
		self.show_by_task_report()

	def on_date_preset_changed(self, b):
		def first_day_of_week(reference_day):
			""" Returns the first day (Sunday) in the week of the reference day """

			ic = reference_day.isocalendar()
			if ic.weekday == 7:
				return reference_day

			return datetime.fromisocalendar(ic.year, ic.week, 1) - \
				timedelta(days=1) # Using Sunday as the first day of the week

		selection = b.get_active_text()
		n = datetime.now()

		if selection == "Today":
			self._from_date.set_text(f"{n.day}/{n.month}/{n.year}")
			self._to_date.set_text(f"{n.day}/{n.month}/{n.year}")
		elif selection == "Yesterday":
			n -=  timedelta(days=1)
			self._from_date.set_text(f"{n.day}/{n.month}/{n.year}")
			self._to_date.set_text(f"{n.day}/{n.month}/{n.year}")
		elif selection in ["Last Week", "This Week"]:
			if selection == "Last Week":
				n -= timedelta(weeks=1)

			n = first_day_of_week(n)
			self._from_date.set_text(f"{n.day}/{n.month}/{n.year}")
			n += timedelta(days=6)
			self._to_date.set_text(f"{n.day}/{n.month}/{n.year}")

		self.update_filtered_data()
		self.show_by_task_report()

	def load_raw_data(self):
		"""
		Loads the time tracking date from the tracking files.
		Also perform canonization of the entries and extraction of tags

		:returns: list of canonized entries
		"""
		# TODO: take the path from the plugin
		with open(os.path.join(Path.home(), "zim_time_tracker.txt"), "r", encoding="utf-8") as tracking_file:
			lines = tracking_file.readlines()

		old_entry_re = re.compile("::(\d+-\d+-\d+ \d+:\d+:\d+):: (.*)$") # old format, before adding page name
		new_entry_re = re.compile("::(\d+-\d+-\d+ \d+:\d+:\d+):: (.*) :: (.*)$")
		date_format = '%Y-%m-%d %H:%M:%S'

		entries = [] # would be list of tuples: (timestamp, task name, page)
		for line in lines:
			m = new_entry_re.match(line)
			if m:
				entries.append((datetime.strptime(m.group(1), date_format), m.group(2), m.group(3)))
				continue

			m = old_entry_re.match(line)
			if m:
				entries.append((datetime.strptime(m.group(1), date_format), m.group(2), ""))
				continue

		canonized_entries = []
		# Collecting only entries which are not identical to their preview entry in their task name and page
		for i in range(len(entries)):
			if i == 0:
				canonized_entries.append(entries[i])
				continue

			if entries[i][1] != entries[i-1][1] or entries[i][2] != entries[i-1][2]:
				canonized_entries.append(entries[i])

		# Extracting out the tags
		tagless_entries = [] # would be list of tuples: (timestamp, task name, page, tags_list)
		tag_re = re.compile("@\w+")
		for index, entry in enumerate(canonized_entries):
			tags = set()
			tagless_task = re.sub(tag_re, lambda m: tags.add(m.group(0)), entry[1])
			tagless_entries.append( (entry[0], tagless_task.strip(), entry[2], tags) )

		return tagless_entries

	def is_filtered(self, entry):
		"""
		Returns true if the given entry should be filtered based on the Search Entry
		:param entry: An list containing the entry data (in the column format loaded from file)
		:return: True iff entry should be filtered
		"""
		search_tokens = self._searchentry.get_text().split()
		if not search_tokens:
			return False

		match = [False, False] # positive, negative
		saw_positive = False

		for token in search_tokens:
			match_index = int(token[0] == '-')
			if token[0] == '-':
				token = token[1:]
			token = token[1:] if token[0] == '-' else token
			if not token:
				continue

			if token in entry[1] or token in " ".join(entry[3]):
				match[match_index] = True

		return match[1] or not match[0]

	def filter_raw_data(self, raw_entries):
		"""
		Filters the raw data based on the date and text filters. Puts the result into a list of the form
		 (start_time, end_time, task name, page, tags_list)
		:param raw_entries:
		:return: the list holding all the filtered data
		"""
		from_date = self._from_date.get_text()
		to_date = self._to_date.get_text()
		date_format = '%d/%m/%Y %H:%M:%S'

		from_date = datetime.strptime(f"{from_date} 00:00:00", date_format) if from_date else None
		to_date = datetime.strptime(f"{to_date} 23:59:59", date_format) if to_date else None

		filtered_data = []
		end_session_str = "__________END_SESSION___________"

		for i in range(len(raw_entries) - 1):
			# Filtering out dates not between from_date and to_date, inclusive
			if from_date is not None and raw_entries[i][0] < from_date:
				continue
			if to_date is not None and raw_entries[i][0] > to_date:
				continue

			entry_desc = raw_entries[i][1]
			if entry_desc == end_session_str:
				continue

			if self.is_filtered(raw_entries[i]):
				continue

			start_time = raw_entries[i][0]
			end_time = raw_entries[i+1][0]
			page = raw_entries[i][2]
			tags = raw_entries[i][3]

			filtered_data.append( (start_time, end_time, entry_desc, page, tags) )

		return filtered_data


class ByTaskTreeView(Gtk.TreeView):

	# Class-level variables
	_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"  # format use for visualization
	# TreeView column indices
	_HEADER_NAMES = ["Task", "Tags", "Duration", "Start", "End", "Page"]
	_COL_TASK_NAME = 0
	_COL_TAGS = 1
	_COL_DURATION = 2
	_COL_START_TIME = 3
	_COL_END_TIME = 4
	_COL_PAGE_NAME = 5
	_COL_DURATION_SECONDS = 6 # Duration of the item (or total duration for all items if it's a parent item)
	_COL_DURATION_BAR = 7 # percent (0-100) of duration out of total duration
	_COL_DURATION_SORT = 8 # total duration to be used for sorting. Only parent items get non-zero values

	def __init__(self):
		super().__init__()

		# Setting up the treeview columns
		for i, name in enumerate(ByTaskTreeView._HEADER_NAMES):
			if i == ByTaskTreeView._COL_DURATION:
				column = Gtk.TreeViewColumn(name, Gtk.CellRendererProgress(),
											value=ByTaskTreeView._COL_DURATION_BAR,
											text=i)
			else:
				column = Gtk.TreeViewColumn(name, Gtk.CellRendererText(), text=i, weight=1)
			column.set_resizable(True)
			self.append_column(column)

		# Sets on which columns sorting is supported
		# TODO: add the rest of the columns
		column = self.get_column(ByTaskTreeView._COL_DURATION)
		column.set_sort_column_id(ByTaskTreeView._COL_DURATION_SECONDS)
		column = self.get_column(ByTaskTreeView._COL_TASK_NAME)
		column.set_sort_column_id(ByTaskTreeView._COL_TASK_NAME)

	def show_report(self, entries, statubar):
		tree_model = Gtk.TreeStore(str,  # task name
								   str,  # tags
								   str,  # duration (as string)
								   str,  # start time
								   str,  # end time
								   str,  # page name
								   int,  # duration as seconds
								   int,  # duration percent (for the progress bar)
								   int  # # duration as total seconds (for sorting)
								   )

		total_tasks = 0
		total_task_durations = timedelta(0)
		parent_tasks = dict() # dict from task description

		# first organizing all the entries by the task description
		for entry in entries:
			start_timestamp = entry[0] # TODO: use enums instead of indices
			end_timestamp = entry[1]
			desc = entry[2]
			page = entry[3]
			tags = entry[4]
			total_tasks += 1

			if desc not in parent_tasks:
				parent_tasks[desc] = {"iter": tree_model.append(None, [desc, "", "N/A", "N/A", "N/A", "", 0, 0, 0]),
									  "tags": set(),
									  "duration": timedelta(0),
									  "start": start_timestamp,
									  "end": end_timestamp,
									  "pages": set()}

			parent_task = parent_tasks[desc]
			parent_task["start"] = min(parent_task["start"], start_timestamp)
			parent_task["end"] = max(parent_task["end"], end_timestamp)
			entry_duration = end_timestamp - start_timestamp
			total_task_durations += entry_duration
			parent_task["duration"] += entry_duration
			parent_task["pages"].add(page)
			for tag in tags:
				parent_task["tags"].add(tag)

			tree_model.append(parent_tasks[desc]["iter"], ["",
													  " ".join(tags),
													  str(entry_duration),
													  start_timestamp.strftime(ByTaskTreeView._DATETIME_FORMAT),
													  end_timestamp.strftime(ByTaskTreeView._DATETIME_FORMAT),
													  page,
													  entry_duration.total_seconds(),
													  0,
													  0]) # child row

		# Updating the parent rows data
		for _, parent in parent_tasks.items():
			treeiter = parent["iter"]
			tree_model.set_value(treeiter, ByTaskTreeView._COL_TAGS, " ".join(parent["tags"]))
			tree_model.set_value(treeiter, ByTaskTreeView._COL_DURATION, str(parent["duration"]))
			tree_model.set_value(treeiter, ByTaskTreeView._COL_START_TIME,
								 parent["start"].strftime(ByTaskTreeView._DATETIME_FORMAT))
			tree_model.set_value(treeiter, ByTaskTreeView._COL_END_TIME,
								 parent["end"].strftime(ByTaskTreeView._DATETIME_FORMAT))
			tree_model.set_value(treeiter, ByTaskTreeView._COL_DURATION_SECONDS,
								 parent["duration"].total_seconds())
			tree_model.set_value(treeiter, ByTaskTreeView._COL_PAGE_NAME, " ".join(parent["pages"]))

		# Updating the progress cell values
		def update_duration_bar(store, treepath, it):
			task_duration = store[it][ByTaskTreeView._COL_DURATION_SECONDS]
			store[it][ByTaskTreeView._COL_DURATION_BAR] = (task_duration / total_task_durations.total_seconds()) * 100

		tree_model.foreach(update_duration_bar)

		sorted_model = Gtk.TreeModelSort(tree_model)
		sorted_model.set_sort_column_id(ByTaskTreeView._COL_DURATION_SECONDS,
										Gtk.SortType.DESCENDING) # this will sort the table programmatically

		self.set_model(sorted_model)
		statubar.push(0, f"Total time: {total_task_durations}    Tasks: {total_tasks}")

class TimeTrackerTaskListWindowExtension(TaskListWindowExtension):
	def __init__(self, _, window):
		window.tasklisttreeview.connect("row-activated", on_todo_item_selected)


class TimeTrackerTaskListWidgetExtension(TaskListNotebookViewExtension):
	def __init__(self, plugin, pageview):
		ext = find_extension(pageview, TaskListNotebookViewExtension)
		ext._widget.tasklisttreeview.connect("row-activated", on_todo_item_selected)
		atexit.register(on_exit)

		from gi.repository import Gtk
		punchout = Gtk.ToggleButton()
		punchout.set_label("PO")
		punchout.set_tooltip_text(_('Punch Out'))  # T: tooltip
		punchout.set_alignment(0.5, 0.5)
		ext._widget._header_hbox.pack_start(punchout, False, True, 0)

		ext._widget.tasklisttreeview.connect("row-activated", lambda a,b,y: punchout.set_active(True))
		punchout.connect("toggled", po_toggled)

		report = Gtk.Button(label="R")
		report.set_tooltip_text("Show Report")
		ext._widget._header_hbox.pack_start(report, False, True, 0)
		report.connect("clicked", show_report)
