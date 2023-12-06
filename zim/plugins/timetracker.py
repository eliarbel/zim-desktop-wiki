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
	if not b.get_active(): # Meaning it's was toggled
		end_session()

def show_report(b):
	win = TimeTrackerReportWindow()
	win.show_all()

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class TimeTrackerReportWindow(Gtk.Window):

	# Class-level varibales
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
		super().__init__(title="Zim Time Tracker Report visualizer")

		self._initialize_layout()
		self.set_default_size(1200, 700)

		self._raw_entries = self._load_raw_data()
		self._set_sort_columns()

		self._show_report()

	def _show_report(self, button=None):
		tree_model, total_tasks, total_duration = self._build_tree_model()
		sorted_model = Gtk.TreeModelSort(tree_model)
		sorted_model.set_sort_column_id(TimeTrackerReportWindow._COL_DURATION_SECONDS,
										Gtk.SortType.DESCENDING) # this will sort the table programmatically

		self._treeview.set_model(sorted_model)
		self._bar.push(0, f"Total time: {total_duration}    Tasks: {total_tasks}")

	def _initialize_layout(self):
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

		self._treeview = Gtk.TreeView()
		scrollable_treeview.add(self._treeview)

		notebook = Gtk.Notebook()
		notebook.append_page(scrollable_treeview, Gtk.Label(label="Aggregate Report"))
		notebook.append_page(Gtk.Label(label="Place holder"), Gtk.Label(label="Day Report"))
		notebook.append_page(Gtk.Label(label="Place holder"), Gtk.Label(label="Week Report"))
		notebook.append_page(Gtk.Label(label="Place holder"), Gtk.Label(label="Log File"))
		box_main_vbox.pack_start(notebook, True, True, 0)

		# Setting up the treeview columns
		for i, name in enumerate(TimeTrackerReportWindow._HEADER_NAMES):
			if i == TimeTrackerReportWindow._COL_DURATION:
				column = Gtk.TreeViewColumn(name, Gtk.CellRendererProgress(),
											value=TimeTrackerReportWindow._COL_DURATION_BAR,
											text=i)
			else:
				column = Gtk.TreeViewColumn(name, Gtk.CellRendererText(), text=i, weight=1)
			column.set_resizable(True)
			self._treeview.append_column(column)

		self._bar = Gtk.Statusbar()
		box_main_vbox.pack_end(self._bar, False, False, 0)

		self.add(box_main_vbox)

	def on_clear_all(self, button):
		self._from_date.set_text("")
		self._to_date.set_text("")
		self._searchentry.set_text("")
		self._show_report()

	def on_search_entry_edited(self, widget):
		self._show_report()

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

		self._show_report()


	def _build_tree_model(self):
		"""
		Builds the tree model after filtering and including durations
		:return: the new tree model, number of tasks, total task duration
		"""
		filtered_tasks = self._filter_raw_data(self._raw_entries)

		tree_model = Gtk.TreeStore(str, # task name
								   str, # tags
								   str, # duration (as string)
								   str, # start time
								   str, # end time
								   str, # page name
								   int, # duration as seconds
								   int, # duration percent (for the progress bar)
								   int # # duration as total seconds (for sorting)
								   )

		total_tasks = 0
		total_task_duration = timedelta(0)

		for task, task_times in filtered_tasks.items():
			treeiter = tree_model.append(None, [task, "", "N/A", "N/A", "N/A", "", 0, 0, 0])
			item_duration = timedelta(0)
			first_timestamp = None
			last_timestamp = None
			total_tasks += len(task_times)
			all_tags = set()
			pages = set()

			for task_time in task_times:
				item_duration += task_time[3]
				start_timestamp = task_time[0]
				end_timestamp = task_time[1]
				tags = task_time[4] # this is a list
				for t in tags:
					all_tags.add(t)
				page = task_time[2]
				pages.add(page)

				if first_timestamp is None or start_timestamp < first_timestamp:
					first_timestamp = start_timestamp
				if last_timestamp is None or end_timestamp > last_timestamp:
					last_timestamp = end_timestamp

				tree_model.append(treeiter, ["",
											 " ".join(tags),
											 str(task_time[3]),
											 start_timestamp.strftime(TimeTrackerReportWindow._DATETIME_FORMAT),
											 end_timestamp.strftime(TimeTrackerReportWindow._DATETIME_FORMAT),
											 page,
											 task_time[3].total_seconds(),
											 0,
											 0 # not putting total seconds here (as in the parent item) to have the child
											 # kept sorted by timestamp (which is the default order by consruction)
											])

			total_task_duration += item_duration
			tree_model.set_value(treeiter, TimeTrackerReportWindow._COL_TAGS, " ".join(all_tags))
			tree_model.set_value(treeiter, TimeTrackerReportWindow._COL_DURATION, str(item_duration))
			tree_model.set_value(treeiter, TimeTrackerReportWindow._COL_START_TIME,
								 first_timestamp.strftime(TimeTrackerReportWindow._DATETIME_FORMAT))
			tree_model.set_value(treeiter, TimeTrackerReportWindow._COL_END_TIME,
								 last_timestamp.strftime(TimeTrackerReportWindow._DATETIME_FORMAT))
			tree_model.set_value(treeiter, TimeTrackerReportWindow._COL_DURATION_SECONDS,
								 item_duration.total_seconds())
			tree_model.set_value(treeiter, TimeTrackerReportWindow._COL_PAGE_NAME, " ".join(pages))

		# Updating the progress bar cell values
		def update_duration_bar(store, treepath, it):
			task_duration = store[it][TimeTrackerReportWindow._COL_DURATION_SECONDS]
			store[it][TimeTrackerReportWindow._COL_DURATION_BAR] = (task_duration / total_task_duration.total_seconds()) * 100
			
		tree_model.foreach(update_duration_bar)

		return tree_model, total_tasks, total_task_duration

	def _set_sort_columns(self):
		"""
		Sets on which columns sorting is supported
		:return:
		"""
		column = self._treeview.get_column(TimeTrackerReportWindow._COL_DURATION)
		column.set_sort_column_id(TimeTrackerReportWindow._COL_DURATION_SECONDS)

		column = self._treeview.get_column(TimeTrackerReportWindow._COL_TASK_NAME)
		column.set_sort_column_id(TimeTrackerReportWindow._COL_TASK_NAME)

		#TODO: add the rest of the columns

	def _load_raw_data(self):
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
			tags = []
			tagless_task = re.sub(tag_re, lambda m: tags.append(m.group(0)), entry[1])
			tagless_entries.append( (entry[0], tagless_task.strip(), entry[2], tags) )

		return tagless_entries

	def is_filtered(self, entry):
		"""
		Returns true is the given entry should be filtered based on the Search Entry
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

	def _filter_raw_data(self, raw_entries):
		"""
		Filters the raw data based on the date and text filters. Puts the result into a dictionary of the form
		 {task name: [(start,end,page, duration)]}

		Note that there are still no task durations calculated

		:param entries:
		:return: the dictionary holding all the filtered data
		"""
		from_date = self._from_date.get_text()
		to_date = self._to_date.get_text()
		date_format = '%d/%m/%Y %H:%M:%S'

		from_date = datetime.strptime(f"{from_date} 00:00:00", date_format) if from_date else None
		to_date = datetime.strptime(f"{to_date} 23:59:59", date_format) if to_date else None

		task_times = {}
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
			entry_timedelta = end_time - start_time
			page = raw_entries[i][2]
			tags = raw_entries[i][3]

			if entry_desc not in task_times:
				task_times[entry_desc] = []

			task_times[entry_desc].append( (start_time, end_time, page, entry_timedelta, tags) )

		return task_times



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
