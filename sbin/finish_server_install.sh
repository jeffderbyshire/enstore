#!/bin/sh
###############################################################################
#
# $Id$
#
###############################################################################
set -u  # force better programming and ability to use check for not set
. /usr/local/etc/setups.sh
setup enstore
echo "installing enstore_html"
rpm -U --force ftp://ssasrv1.fnal.gov/en/enstore_related/enstore_html-1.0-0.i386.rpm
echo "installing postgres"
rpm -U --force ftp://ssasrv1.fnal.gov/en/enstore_related/postgresql-libs-8.2.4-1PGDG.i686.rpm \
ftp://ssasrv1.fnal.gov/en/enstore_related/postgresql-8.2.4-1PGDG.i686.rpm \
ftp://ssasrv1.fnal.gov/en/enstore_related/postgresql-server-8.2.4-1PGDG.i686.rpm \
ftp://ssasrv1.fnal.gov/en/enstore_related/postgresql-devel-8.2.4-1PGDG.i686.rpm

echo "installing pnfs"
rpm -U --force ftp://ssasrv1.fnal.gov/en/enstore_related/pnfs-3.1.10-1f.i386.rpm
#also need to install here or via cgengine
# pnfs
# posgtres (may be this gets installed along with 
