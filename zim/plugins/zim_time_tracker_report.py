import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
import re
from datetime import datetime, timedelta
import os
from pathlib import Path

_DATETIME_FORMAT = "%d/%m/%Y %H:%M:%S"  # format use for visualization

class MyWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Zim Time Tracker Report visualizer")

        self._initialize_layout()
        self.set_default_size(1200, 700)

        self._raw_entries = self._load_raw_data()
        self._set_sort_columns()

        self._show_report(None)

    def _show_report(self, button):
        tree_model, total_tasks, total_duration = self._build_tree_model()
        self._treeview.set_model(tree_model)
        self._bar.push(0, f"Total time: {total_duration}    Tasks: {total_tasks}")

    def _initialize_layout(self):
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
        box_search.pack_start(Gtk.SearchEntry(), False, True, 3)

        box_top_strip = Gtk.HBox()
        box_top_strip.pack_start(box_from_date, False, True, 3)
        box_top_strip.pack_start(box_to_date, False, True, 3)
        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", self._show_report)
        box_top_strip.pack_start(refresh, False, False, 3)
        box_top_strip.pack_end(box_search, False, True, 3)

        box_main_vbox = Gtk.VBox()
        box_main_vbox.pack_start(box_top_strip, False, False, 0)

        # setting up the layout, putting the treeview in a scrollwindow
        scrollable_treeview = Gtk.ScrolledWindow()
        scrollable_treeview.set_vexpand(True)

        self._treeview = Gtk.TreeView()
        scrollable_treeview.add(self._treeview)

        box_main_vbox.pack_start(scrollable_treeview, True, True, 0)
        for i, name in enumerate(["Task", "Duration", "Start", "End", "Page"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(name, renderer, text=i, weight=1)
            column.set_resizable(True )
            self._treeview.append_column(column)

        self._bar = Gtk.Statusbar()
        box_main_vbox.pack_end(self._bar, False, False, 0)

        self.add(box_main_vbox)

    def _build_tree_model(self):
        """
        Builds the tree model after filtering and including durations
        :return: the new tree model, number of tasks, total task duration
        """
        filtered_tasks = self._filter_raw_data(self._raw_entries)

        tree_model = Gtk.TreeStore(str, # task name
                                   str, # duration (as string)
                                   str, # start time
                                   str, # end time
                                   str, # page name
                                   float # duration as total seconds (for sorting)
                                   )

        total_tasks = 0
        total_task_duration = timedelta(0)

        for task, task_times in filtered_tasks.items():
            treeiter = tree_model.append(None, [task, "N/A", "N/A", "N/A", "", 0])
            item_duration = timedelta(0)
            first_timestamp = None
            last_timestamp = None
            total_tasks += len(task_times)

            for task_time in task_times:
                item_duration += task_time[3]
                start_timestamp = task_time[0]
                end_timestamp = task_time[1]

                if first_timestamp is None or start_timestamp < first_timestamp:
                    first_timestamp = start_timestamp
                if last_timestamp is None or end_timestamp > last_timestamp:
                    last_timestamp = end_timestamp

                tree_model.append(treeiter, ["",
                                            str(task_time[3]),   # TODO: use column names (enums) instead of indices
                                            start_timestamp.strftime(_DATETIME_FORMAT),
                                            end_timestamp.strftime(_DATETIME_FORMAT),
                                            task_time[2],
                                            0 # not putting total seconds here (as in the parent item) to have the child
                                              # kept sorted by timestamp (which is the default order by consruction)
                                            ])

            total_task_duration += item_duration
            tree_model.set_value(treeiter, 1, str(item_duration))
            tree_model.set_value(treeiter, 2, first_timestamp.strftime(_DATETIME_FORMAT))
            tree_model.set_value(treeiter, 3, last_timestamp.strftime(_DATETIME_FORMAT))
            tree_model.set_value(treeiter, 5, item_duration.total_seconds())

        return tree_model, total_tasks, total_task_duration

    def _set_sort_columns(self):
        """
        Sets on which columns sorting is supported
        :return:
        """
        column = self._treeview.get_column(1)
        column.set_sort_column_id(5)

        column = self._treeview.get_column(0)
        column.set_sort_column_id(0)

        #TODO: add the reset of the columns

    def _load_raw_data(self):
        """
        Loads the time tracking date from the tracking files

        :returns: list of entries
        """
        # tracking_file = open(os.path.join(Path.home(), "zim_time_tracker.txt"), "r") #TODO: take the path from the plugin
        tracking_file = open("/mnt/c/Users/361073756/zim_time_tracker.txt", "r")  # TODO: take the path from the plugin


        lines = tracking_file.readlines()
        old_entry_re = re.compile("::(\d+-\d+-\d+ \d+:\d+:\d+):: (.*)$") # old format, before adding page name
        new_entry_re = re.compile("::(\d+-\d+-\d+ \d+:\d+:\d+):: (.*) :: (.*)$")
        date_format = '%Y-%m-%d %H:%M:%S'

        entries = [] # would be list of tuples: (timestamp, task name)
        for line in lines:
            m = new_entry_re.match(line)
            if m:
                entries.append((datetime.strptime(m.group(1), date_format), m.group(2), m.group(3)))
                continue

            m = old_entry_re.match(line)
            if m:
                entries.append((datetime.strptime(m.group(1), date_format), m.group(2), ""))
                continue

        return entries

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

            start_time = raw_entries[i][0]
            end_time = raw_entries[i+1][0]
            entry_timedelta = end_time - start_time
            page = raw_entries[i][2]
            if entry_desc not in task_times:
                task_times[entry_desc] = []

            task_times[entry_desc].append( (start_time, end_time, page, entry_timedelta) )

        return task_times


win = MyWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

