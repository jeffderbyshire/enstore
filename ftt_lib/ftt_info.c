#include <stdio.h>
#include "ftt_private.h"

char *
ftt_get_basename(ftt_descriptor d) {
    
    ENTERING("ftt_get_basename");
    PCKNULL("ftt_descriptor", d);

    return d->basename;
}

char **
ftt_list_all(ftt_descriptor d) {
    static char *table[64];
    int i,j;

    ENTERING("ftt_list_all");
    PCKNULL("ftt_descriptor", d);

    for( i = 0,j = 0; j < 64 && d->devinfo[i].device_name != 0; i++ ){
	if (d->devinfo[i].first) {
	    table[j++] = d->devinfo[i].device_name;
	}
    }
    table[j++] = 0;
    return table;
}

int
ftt_chall(ftt_descriptor d, int uid, int gid, int mode){
    char **pp;
    int res;
    int i;

    ENTERING("ftt_chall");
    CKNULL("ftt_descriptor", d);

    pp = ftt_list_all(d);
    for( i = 0; pp[i] != 0; i++){
	res = chmod(pp[i],mode);
	if( res < 0 ) return ftt_translate_error(d,FTT_OPN_CHALL,"ftt_chall",res,"chmod",1);
	res = chown(pp[i],uid,gid);
	if( res < 0 ) return ftt_translate_error(d,FTT_OPN_CHALL,"ftt_chall",res,"chown",1);
    }
    return 0;
}

char *
ftt_avail_mode(ftt_descriptor d, int density, int mode, int blocksize){
    int i;

    ENTERING("ftt_avail_mode");
    PCKNULL("ftt_descriptor", d);
    
    for( i = 0; d->devinfo[i].device_name != 0; i++ ){
	if( d->devinfo[i].density == density &&
		    d->devinfo[i].mode == mode &&
		    (d->devinfo[i].fixed == 0) == (blocksize == 0)) {
	    return d->devinfo[i].device_name;
	}
    }
    ftt_eprintf("\tThe combination mode %d density %d blocksize %d is not\n\
	avaliable on device %s", mode, density, blocksize, d->basename);
    ftt_errno = FTT_ENODEV;
    return 0;
}

char *
ftt_get_mode(ftt_descriptor d, int *density, int* mode, int *blocksize){

    ENTERING("ftt_get_mode");
    PCKNULL("ftt_descriptor", d);

    density &&  (*density = d->devinfo[d->which_is_default].density);
    mode &&     (*mode = d->devinfo[d->which_is_default].mode);
    blocksize &&(*blocksize = d->devinfo[d->which_is_default].fixed ? 
		    d->default_blocksize : 0);
    return d->devinfo[d->which_is_default].device_name;
}
char *
ftt_set_mode(ftt_descriptor d, int density, int mode, int blocksize) {
    int i;

    ENTERING("ftt_set_mode");
    PCKNULL("ftt_descriptor", d);
    
    ftt_close_dev(d);
    for( i = 0; d->devinfo[i].device_name != 0; i++ ){
	if (d->devinfo[i].density == density &&
		    d->devinfo[i].mode == mode &&
		    (d->devinfo[i].fixed == 0) == (blocksize == 0) && 
		    d->devinfo[i].rewind == 0) {
	    d->which_is_default = i;
	    d->default_blocksize = blocksize;
	    return d->devinfo[i].device_name;
	}
    }
    ftt_eprintf("\tThe combination mode %d density %d blocksize %d is not\n\
	avaliable on device %s", mode, density, blocksize, d->basename);
    ftt_errno = FTT_ENODEV;
    return 0;
}

int 
ftt_get_mode_dev(ftt_descriptor d, char *devname, int *density, 
			int *mode, int *blocksize, int *rewind) {
    int i;

    ENTERING("ftt_get_mode_dev");
    CKNULL("ftt_descriptor", d);
    
    for( i = 0; d->devinfo[i].device_name != 0; i++ ){
	if (0 == strcmp(d->devinfo[i].device_name, devname)) {
	    density &&  (*density = d->devinfo[i].density);
	    mode &&     (*mode = d->devinfo[i].mode);
	    blocksize && (*blocksize =  d->devinfo[i].fixed);
	    rewind &&   (*rewind = d->devinfo[i].rewind);
	    return 0;
	}
    }
    ftt_eprintf("ftt_get_mode_dev was called  on device name %s\n\
	which was not found in the ftt tables for basename %s\n",
	devname, d->basename);
    ftt_errno = FTT_ENODEV;
    return -1;
}

int 
ftt_set_mode_dev(ftt_descriptor d, char *devname, int blocksize, int force) {
    int i;

    ENTERING("ftt_set_mode_dev");
    CKNULL("ftt_descriptor", d);
    CKNULL("device name", devname);
    
    for( i = 0; d->devinfo[i].device_name != 0; i++ ){
	if (0 == strcmp(d->devinfo[i].device_name, devname)) {
	    d->which_is_default = i;
	    d->default_blocksize = blocksize;
	    return 0;
	}
    }
    if (force) { 
	/* not found in table, but force bit was set... */

	/* so add it to the table */
	d->devinfo[i].device_name = devname;
	d->which_is_default = i;

	/* and we know/set nothing ... */
	d->devinfo[i].mode = -1;
	d->devinfo[i].density = -1;
	d->devinfo[i].fixed = -1;
	d->default_blocksize = blocksize;

	return 0;
    }
    ftt_eprintf("ftt_set_mode_dev was called  on device name %s\n\
	which was not found in the ftt tables for basename %s\n\
	and the force bit was not set.\n",
	devname, d->basename);
    ftt_errno = FTT_ENODEV;
    return -1;
}
