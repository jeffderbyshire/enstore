import time

# translate time.time output to a person readable format.
# strip off the day and reorganize things a little
def format_time(theTime, sep=" "):
    return time.strftime("%Y-%b-%d"+sep+"%H:%M:%S", time.localtime(theTime))

# strip off anything before the '/'
def strip_file_dir(str):
    ind = string.rfind(str, "/")
    if not ind == -1:
	str = str[(ind+1):]

