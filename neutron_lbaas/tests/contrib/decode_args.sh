#!/bin/bash

# This file is meant to be sourced by the other hooks

# Legacy values for $1 and $2:
# $1 - lbaasv2, lbaasv1 (lbaasversion)
# $2 - scenario, minimal, api, healthmonitor, listener, loadbalancer, member, pool (lbaastest)

# Args being phased in:
# $1 - same
# $2 - test-driver, with any missing -driver being "octavia"
#    scenario-octavia
#    minimal-octavia
#    api-namespace
#    api-{thirdparty}
#    healthmonitor-octavia
#    listener-octavia
#    loadbalancer-octavia
#    member-octavia
#    pool-octavia



lbaasversion="$1"
lbaastest="$2"
lbaasenv=$(echo "$lbaastest" | perl -ne '/^(.*)-([^-]+)$/ && print "$1";')
if [ -z "$lbaasenv" ]; then
    lbaasenv=$lbaastest
fi
lbaasdriver=$(echo "$lbaastest" | perl -ne '/^(.*)-([^-]+)$/ && print "$2";')
if [ -z "$lbaasdriver" ]; then
    lbaasdriver='octavia'
fi


