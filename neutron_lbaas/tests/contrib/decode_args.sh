#!/bin/bash

# This file is meant to be sourced by the other hooks

# Legacy values for $1, $2 and $3:
# $1 - dsvm-functional, tempest (testtype)
# $2 - lbaasv2 (lbaasversion)
# $3 - scenario, minimal, api, healthmonitor, listener, loadbalancer, member, pool (lbaastest)

# Args being phased in:
# $1 - same
# $2 - same
# $3 - test-driver, with any missing -driver being "octavia"
#    scenario-octavia
#    minimal-octavia
#    api-namespace
#    api-{thirdparty}
#    healthmonitor-octavia
#    listener-octavia
#    loadbalancer-octavia
#    member-octavia
#    pool-octavia




testtype="$1"
lbaasversion="$2"
lbaastest="$3"

case $testtype in
    "dsvm-functional")
        testenv=$testtype
        ;;

    "tempest")
        lbaasenv=$(echo "$lbaastest" | perl -ne '/^(.*)-([^-]+)$/ && print "$1";')
        if [ -z "$lbaasenv" ]; then
            lbaasenv=$lbaastest
        fi
        lbaasdriver=$(echo "$lbaastest" | perl -ne '/^(.*)-([^-]+)$/ && print "$2";')
        if [ -z "$lbaasdriver" ]; then
            lbaasdriver='octavia'
        fi

        testenv=${lbaastest:-"apiv2"}

        if [ "$lbaasversion" = "lbaasv2" ]; then
            case "$lbaasenv" in
                "api"|"healthmonitor"|"listener"|"loadbalancer"|"member"|"minimal"|"pool")
                    testenv="apiv2"
                    ;;
                "scenario")
                    testenv="scenario"
                    ;;
                *)
                    echo "Unrecognized env $lbaasenv".
                    exit 1
                    ;;
            esac
        fi
        ;;
esac
