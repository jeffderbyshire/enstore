#!/usr/bin/env python

###############################################################################
#
# $Id$
#
###############################################################################

"""
Plot number of files read and written per mount versus date, stacked by
storage group, individually for each unique drive type.
"""

# Python imports
from __future__ import division, print_function
import os
import time

# Enstore imports
import dbaccess
import enstore_constants
import enstore_plotter_module
import histogram

# Note: This module is referenced by the "plotter_main" module.

WEB_SUB_DIRECTORY = enstore_constants.FILES_RW_PLOTS_SUBDIR
# Note: Above constant is referenced by "enstore_make_plot_page" module.
TIME_CONDITION = "CURRENT_TIMESTAMP - interval '1 month'"

class FilesRWPlotterModule(enstore_plotter_module.EnstorePlotterModule):
    """Plot number of files read and written per mount versus date, stacked
       by storage group, individually for each unique drive type."""

    plot_accumulative = False

    def book(self, frame):
        """Create destination directory for plots, as needed."""

        cron_dict = frame.get_configuration_client().get('crons', {})
        self.html_dir = cron_dict.get('html_dir', '')
        self.plot_dir = os.path.join(self.html_dir,
                                     enstore_constants.PLOTS_SUBDIR)
        if not os.path.exists(self.plot_dir):
            os.makedirs(self.plot_dir)
        self.web_dir = os.path.join(self.html_dir, WEB_SUB_DIRECTORY)
        if not os.path.exists(self.web_dir):
            os.makedirs(self.web_dir)
        print('Plots sub-directory: {}'.format(self.web_dir))

    def fill(self, frame):
        """Read and store values for plots from the database into memory."""

        # Get database
        csc = frame.get_configuration_client()
        db_info = csc.get(enstore_constants.ACCOUNTING_SERVER)
        db_get = db_info.get
        db = dbaccess.DatabaseAccess(maxconnections=1,
                                     host=db_get('dbhost', 'localhost'),
                                     database=db_get('dbname', 'accounting'),
                                     port=db_get('dbport', 9900),
                                     user=db_get('dbuser', 'enstore'),
                                     )

        # Read from database
        db_query = ("select type as drive, storage_group, "
                    "date_trunc('day', finish) as date, "
                    "sum(reads)::float/count(state) as reads_per_dismount, "
                    "sum(writes)::float/count(state) as writes_per_dismount, "
                    "(sum(reads)+sum(writes))::float/count(state) "
                    " as reads_and_writes_per_dismount "
                    "from tape_mounts where "
                    "storage_group notnull and finish notnull "
                    "and finish > {0} and state='D' "
                    "group by drive, storage_group, date "
                    "order by drive, storage_group, date"
                    ).format(TIME_CONDITION)
        res = db.query_dictresult(db_query)

        # Restructure data into nested dict
        counts = {}
        for row in res:
            row = row.get
            counts.setdefault(row('drive'), {}) \
                  .setdefault(row('storage_group'), {}) \
                   [row('date')] = {'reads': row('reads_per_dismount'),
                                    'writes': row('writes_per_dismount'),
                                    'reads+writes':
                                        row('reads_and_writes_per_dismount')
                                    }

        db.close()
        self.counts = counts

    def plot(self):
        """Write plot files."""

        str_time_format = "%Y-%m-%d %H:%M:%S"

        now_time = time.time()
        Y, M, D, _h, _m, _s, wd, jd, dst = time.localtime(now_time)
        now_time = time.mktime((Y, M, D, 23, 59, 59, wd, jd, dst))
        now_time_str = time.strftime(str_time_format,
                                     time.localtime(now_time))

        start_time = now_time - 32 * 86400  # (32 days)
        Y, M, D, _h, _m, _s, wd, jd, dst = time.localtime(start_time)
        start_time = time.mktime((Y, M, D, 23, 59, 59, wd, jd, dst))
        start_time_str = time.strftime(str_time_format,
                                       time.localtime(start_time))

        #print('xrange: min={}; max={};'.format(start_time_str, now_time_str))

        plot_key_setting = 'set key outside width 2'
        # Note: "width 2" is used above to prevent a residual overlap of the
        # legend's labels and the histogram.

        set_xrange_cmds =  ('set xdata time',
                            'set timefmt "{}"'.format(str_time_format),
                            'set xrange ["{}":"{}"]'.format(start_time_str,
                                                            now_time_str))

        for action in ('reads', 'writes'): #, 'reads+writes'):

            ylabel = 'Average file {} per mount'.format(action)

            for drive, drive_dict in self.counts.iteritems():

                plot_name = '{}_{}'.format(drive, action)
                plot_title = ('Average file {} per mount by storage group '
                              'for {} drives.').format(action, drive)
                plotter = histogram.Plotter(plot_name, plot_title)
                plotter.add_command(plot_key_setting)
                for cmd in set_xrange_cmds:
                    plotter.add_command(cmd)

                hist_sum_name = 'h_' + plot_name
                hist_sum = histogram.Histogram1D(hist_sum_name,
                                                 hist_sum_name, 32,
                                                 float(start_time),
                                                 float(now_time))
                hist_sum.set_time_axis(True)

                if self.plot_accumulative:

                    iplot_name = 'accumulative_{}'.format(plot_name)
                    iplot_title = ('Accumulative average file {} per mount '
                                   'by storage group for {} drives.').format(
                                   action, drive)
                    iplotter = histogram.Plotter(iplot_name, iplot_title)
                    iplotter.add_command(plot_key_setting)
                    for cmd in set_xrange_cmds:
                        iplotter.add_command(cmd)

                    ihist_sum_name = 'acc_' + plot_name
                    ihist_sum = histogram.Histogram1D(ihist_sum_name,
                                                      ihist_sum_name, 32,
                                                      float(start_time),
                                                      float(now_time))
                    ihist_sum.set_time_axis(True)

                color = 0
                for sg, sg_dict in drive_dict.iteritems():

                    print('Processing: action={}; drive={}; storage_group={};'
                          .format(action, drive, sg))

                    color += 1

                    hist_name = plot_name + '_' + sg
                    hist = histogram.Histogram1D(hist_name, hist_name, 32,
                                                 float(start_time),
                                                 float(now_time))

                    for date, date_dict in sg_dict.iteritems():
                        date = time.mktime(time.strptime(date,
                                                         '%Y-%m-%d %H:%M:%S'))
                        value = date_dict[action]
                        hist.fill(date, value)

                    hist.set_time_axis(True)
                    hist.set_ylabel(ylabel)
                    hist.set_xlabel('Date (year-month-day)')
                    hist.set_line_color(color)
                    hist.set_line_width(20)
                    hist.set_marker_type('impulses')

                    hist_sum += hist
                    hist_sum_name = 'drive_{}'.format(hist_name)
                    hist_sum.set_name(hist_sum_name)
                    hist_sum.set_data_file_name(hist_sum_name)
                    hist_sum.set_marker_text(sg)
                    hist_sum.set_time_axis(True)
                    hist_sum.set_ylabel(ylabel)
                    hist_sum.set_marker_type('impulses')
                    hist_sum.set_line_color(color)
                    hist_sum.set_line_width(20)
                    plotter.add(hist_sum)

                    if self.plot_accumulative:

                        ihist = hist.integral()
                        ihist.set_marker_text(sg)
                        ihist.set_marker_type('impulses')
                        ihist.set_ylabel(ylabel)

                        ihist_sum += ihist
                        ihist_marker_text = ihist.get_marker_text()
                        ihist_sum_name = 'accumulated_{}'.format(
                                         ihist_marker_text)
                        ihist_sum.set_name(ihist_sum_name)
                        ihist_sum.set_data_file_name(ihist_sum_name)
                        ihist_sum.set_marker_text(ihist_marker_text)
                        ihist_sum.set_time_axis(True)
                        ihist_sum.set_ylabel(ihist.get_ylabel())
                        ihist_sum.set_marker_type(ihist.get_marker_type())
                        ihist_sum.set_line_color(color)
                        ihist_sum.set_line_width(20)
                        iplotter.add(ihist_sum)

                plotter.reshuffle()
                plotter.plot(directory=self.web_dir)
                if self.plot_accumulative:
                    iplotter.reshuffle()
                    iplotter.plot(directory=self.web_dir)