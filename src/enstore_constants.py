# this file contains constants used in several enstore modules

NETWORKFILE = "active_monitor.html"

FILE_PREFIX = "enplot_"
BPD = "bpd"
XFER = "xfer"
MLAT = "mlat"
MPH = "mph"
MPD = "mpd_total"
LOG = ".log"
LOG_PREFIX = "LOG-"

# used by the inquisitor plot command
MPH_FILE = "%s%s"%(FILE_PREFIX, MPH)
MPD_FILE = "%s%s"%(FILE_PREFIX, MPD)
MLAT_FILE = "%s%s"%(FILE_PREFIX, MLAT)
BPD_FILE = "%s%s"%(FILE_PREFIX, BPD)
BPD_FILE_R = "%s_r"%(BPD_FILE,)
BPD_FILE_W = "%s_w"%(BPD_FILE,)
XFER_FILE = "%s%s"%(FILE_PREFIX, XFER)
XFERLOG_FILE = "%s%s"%(XFER_FILE, LOG)

JPG = ".jpg"
PS = ".ps"
STAMP = "_stamp"

PID = "pid"
UID = "uid"
SOURCE = "source"
ALARM = "alarm"
ANYALARMS = "alarms"
URL = "url"

ALIVE_INTERVAL = "alive_interval"
DEFAULT_ALIVE_INTERVAL = "default_alive_interval"
CONFIG_SERVER_ALIVE_INTERVAL = 30 # there is none in config file

# server names used in enstore_up_down
LOGS = "Logger"
ALARMS = "Alarm Server"
CONFIGS = "Configuration Server"
FILEC = "File Clerk"
INQ = "Inquisitor"
VOLC = "Volume Clerk"

# server names used in config file
LOG_SERVER = "log_server"
ALARM_SERVER = "alarm_server"
FILE_CLERK = "file_clerk"
VOLUME_CLERK = "volume_clerk"
INQUISITOR = "inquisitor"
CONFIG_SERVER = "config_server"  # included for use by inquisitor
WWW_SERVER = "www_server"

OUTAGEFILE = "enstore_outage.py"
SAAGHTMLFILE = "enstore_saag.html"
BASENODE = "base_node"
UP = 0
WARNING = 2
DOWN = 1
SEEN_DOWN = 4
NOSCHEDOUT = -1
OFFLINE = 1
ENSTORE = "enstore"
NETWORK = "network"
TIME = "time"
UNKNOWN = "UNKNOWN TIME"

# dictionary keys for the system status information
STATUS = "status"
SUSPECT_VOLS = "suspect"
REJECT_REASON = "reject_reason"
TOTALPXFERS = "total_pend_xfers"
READPXFERS = "read_pend_xfers"
WRITEPXFERS = "write_pend_xfers"
TOTALONXFERS = "total_ong_xfers"
READONXFERS = "read_ong_xfers"
WRITEONXFERS = "write_ong_xfers"
PENDING = "pending"
WORK = "work"
MOVER = "mover"
MOVERS = "movers"
ID = "id"
PORT = "port"
CURRENT = "current"
BASE = "base"
DELTA = "delta"
AGETIME = "agetime"
FILE = "file"
BYTES = "bytes"
MODIFICATION = "mod"
NODE = "node"
SUBMITTED = "submitted"
DEQUEUED = "dequeued"
VOLUME_FAMILY = "volume_family"
FILE_FAMILY = "file_family"
FILE_FAMILY_WIDTH = "ff_width"
DEVICE = "device"
EOD_COOKIE = "eod_cookie"
LOCATION_COOKIE = "location_cookie"
COMPLETED = "completed"
FAILED = "failed"
CUR_READ = "cur_read"
CUR_WRITE = "cur_write"
STATE = "state"
FILES = "files"
VOLUME = "volume"
LAST_READ = "last_read"
LAST_WRITE = "last_write"
WRITE = "write"
READ = "read"
LMSTATE = "lmstate"

NO_INFO = "------"
NO_WORK = "No work at movers"
NO_PENDING = "No pending work"

LIBRARY_MANAGER = "library_manager"
MOVER = "mover"
MEDIA_CHANGER = "media_changer"
GENERIC_SERVERS = [ ALARM_SERVER, CONFIG_SERVER, FILE_CLERK, INQUISITOR,
		    LOG_SERVER, VOLUME_CLERK]
