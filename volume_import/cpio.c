/* $Id  
  Wrap file data in cpio odc format
*/

/* Functions in this module:
   cpio_start(filename, buf, bufsize)
   cpio_next_block(buf, blocksize)
   cpio_get_checksums(&checksums)
        checksums is [sanity_size, sanity_checksum, full_size, full_checksum]
*/

/* Note - this code is NOT reentrant/thread-safe.  There can
   only be one CPIO operation going on at a time.  Also it only
   works for regular files (no directories, FIFOs etc) 
*/

#include "volume_import.h"

#define CPIO_MAGIC 070707

static char cpio_header[76+MAX_PATH_LEN+1];
static int cpio_header_len;

static char *cpio_filename=NULL;
static int cpio_pos=0; /*Pos into the generated archive*/
static unsigned int checksum, early_checksum, early_checksum_len;
static unsigned int file_len;
static unsigned int file_bytes_left;
static int cpio_fd = -1;

static char *cpio_trailer = "\
070707000000000000000000000000000000000001\
0000000000000000000001300000000000TRAILER!!!";

static int cpio_trailer_len = 87; /*String above, +1 for terminator*/



void
bytecopy(char *to, char *from, int n){
    while (n-->0)*to++=*from++;
}

#define min(a,b)((a)<(b)?(a):(b))

#ifdef TESTING
char *progname;
#endif


/* Return  0 on success, -1 on error */
int
cpio_start(char *filename){
    struct stat sbuf;
    
    if (stat(filename,&sbuf)){
	fprintf(stderr, "%s: ", progname);
	perror(filename);
	return -1;
    }

    cpio_filename = filename;
    file_bytes_left = file_len = sbuf.st_size;

    cpio_fd = open(cpio_filename, 0);
    if (cpio_fd<0){
	fprintf(stderr, "%s: ", progname);
	perror(filename);
	return -1;
    }
    
    /*Make the header*/
    sprintf(cpio_header,
	    "%06o%06o%06o%06o%06o%06o%06o%06o%011o%06o%011o%s",
	    CPIO_MAGIC,
	    (unsigned int)sbuf.st_dev,
	    (unsigned int)sbuf.st_ino,
	    (unsigned int)sbuf.st_mode,
	    (unsigned int)sbuf.st_uid,
	    (unsigned int)sbuf.st_gid,
	    (unsigned int)sbuf.st_nlink,
	    (unsigned int)sbuf.st_rdev,
	    (unsigned int)sbuf.st_mtime,
	    strlen(cpio_filename)+1,
	    (unsigned int)sbuf.st_size,
	    cpio_filename);

#ifdef DEBUG
    printf("%s\n",cpio_header);
#endif
    cpio_header_len = strlen(cpio_header)+1;
    checksum = early_checksum = early_checksum_len = 0;
    cpio_pos = 0;
    return 0;
}

/*Returns 0 on success, -1 on error*/
static int
cpio_read_file(char *buf, int nbytes){
    int nread;

    if (nbytes<=0)
	return 0;
    if (nbytes>file_bytes_left){
	fprintf(stderr,
		"%s: read: requesting %d bytes from file %s, only %d bytes left\n",
		progname, nbytes, cpio_filename, file_bytes_left);
	nbytes=file_bytes_left;
    }
    nread = read(cpio_fd, buf, nbytes);
    if (nread<0){
	fprintf(stderr, "%s: read:", progname);
	perror(cpio_filename);
	return -1;
    } else if (nread != nbytes){
	fprintf(stderr,
		"%s: read: requested %d bytes from file %s, read %d bytes\n",
		progname, nbytes, cpio_filename, nread);
    }
    file_bytes_left -= nread;
    return 0;
}
	
    
	

int 
cpio_next_block(char *buf, int buf_len){
    
    int nbytes=0;
    int buf_pos = 0;
    int trailer_pos = 0;

    if (cpio_pos<cpio_header_len){  
	/* In the header */
	nbytes = min(buf_len, cpio_header_len-cpio_pos);
	bytecopy(buf+buf_pos, cpio_header+cpio_pos, nbytes);
	cpio_pos += nbytes;
	buf_pos += nbytes;
    }
    
    if (file_bytes_left && buf_pos < buf_len){
	/* Room for some file data */
	nbytes = min(buf_len-buf_pos, file_bytes_left);
	if (cpio_read_file(buf+buf_pos, nbytes))
	    return -1;
	buf_pos += nbytes;
	cpio_pos += nbytes;
    }
    
    if (!file_bytes_left && buf_pos < buf_len){
	/* Room for some trailer data */
	trailer_pos = cpio_pos-(cpio_header_len+file_len);
	nbytes = min(buf_len-buf_pos,  cpio_trailer_len-trailer_pos);
	bytecopy(buf+buf_pos, cpio_trailer+trailer_pos, nbytes);
	buf_pos+=nbytes;
	cpio_pos += nbytes;
    }
    return buf_pos;
}






	

/***

    cpio odc format
    
    Offset             Field Name           Length          Notes
    0                        c_magic               6                     070707
    6                        c_dev                    6
    12                     c_ino                     6
    18                     c_mode                6
    24                     c_uid                     6
    30                     c_gid                     6 
    36                     c_nlink                  6
    42                     c_rdev                   6
    48                     c_mtime             11
    59                     c_namesize        6         count includes terminating NUL in pathname
    65                     c_filesize          11         must be 0 for FIFOs and directories
    76                     filename 

***/


#ifdef TESTING

int
main(int argc, char **argv){
    int n;
    int buf_len;
    char *buf;
    
    progname=argv[0];
    buf_len=atoi(argv[1]);
    buf = (char*)malloc(buf_len);
    cpio_start(argv[2]);
    while ((n=cpio_next_block(buf,buf_len))>0){
	write(1,buf,n);
    }
    return 0;
}

#endif
