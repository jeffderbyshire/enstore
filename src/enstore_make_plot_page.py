import os
import string

import enstore_plots
import enstore_html
import enstore_files
import generic_client

TMP = ".tmp"

# find all the files under the current directory that are jpg files.
# (*.jpg). then create a smaller version of each file (if it does not 
# exist) with the name *_stamp.jpg, to serve as a stamp file on 
# the web page and create a ps file (if it does not exist) with the
# name *.ps.
def find_jpg_files((jpgs, stamps, pss, input_dir), dirname, names):
    (tjpgs, tstamps, tpss) = enstore_plots.find_files(names)
    dir = string.split(dirname, input_dir)[-1]
    # when we add the found file to the list of files, we need to add the
    # directory that it was found in to the name
    for file in tjpgs:
        jpgs.append("%s/%s"%(dir, file))
    for file in tstamps:
        stamps.append("%s/%s"%(dir, file))
    for file in tpss:
        pss.append("%s/%s"%(dir, file))

def do_the_walk(input_dir):
    # walk the directory tree structure and return a list of all jpg, stamp
    # and ps files
    jpgs = []
    stamps = []
    pss = []
    # make sure the input directory contains the ending / in it
    if input_dir[-1] != "/":
        input_dir = "%s/"%(input_dir,)
    os.path.walk(input_dir, find_jpg_files, (jpgs, stamps, pss, input_dir))
    jpgs.sort()
    stamps.sort()
    pss.sort()
    return (jpgs, stamps, pss)

class PlotPageInterface(generic_client.GenericClientInterface):

    def __init__(self, flag=1, opts=[]):
	# fill in the defaults for the possible options
        self.do_parse = flag
	self.description = "Graphical representation of the exit status of Enstore cron jobs."
	self.title = "Enstore Cron Processes Output"
	self.title_gif = "en_cron_pics.gif"
	self.dir = "/fnal/ups/prd/www_pages/enstore"
	self.input_dir = "%s/CRONS"%(self.dir,)
	self.html_file = "%s/cron_pics.html"%(self.dir,)
	generic_client.GenericClientInterface.__init__(self)

    def options(self):
	return self.help_options() +\
	       ["input_dir=", "description=", "title=",
		"html_file=", "title_gif="]

def do_work(intf):
    # this is where the work is really done
    # get the list of stamps and jpg files
    (jpgs, stamps, pss) = do_the_walk(intf.input_dir)
    print jpgs
    print "---------------------------------"
    print stamps
    print "---------------------------------"
    print pss
    print "---------------------------------"

    html_page = enstore_html.EnPlotPage(intf.title, intf.title_gif, 
					intf.description)
    html_page.body(jpgs, stamps, pss)
    # open the temporary html file and output the html text to it
    tmp_html_file = "%s%s"%(intf.html_file, TMP)
    html_file = enstore_files.EnFile(tmp_html_file)
    html_file.open()
    html_file.write(html_page)
    html_file.close()
    os.rename(tmp_html_file, intf.html_file)

if __name__ == "__main__" :

    intf = PlotPageInterface()

    do_work(intf)
