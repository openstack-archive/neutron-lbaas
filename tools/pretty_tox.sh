#! /bin/sh

TESTRARGS=$1
#This is for supporting tempest tests in tox as the neutron-lbaas tempest tests fail when run in parallel
CONCURRENCY=${OS_TESTR_CONCURRENCY:-}
if [ -n "$CONCURRENCY" ]
then
  CONCURRENCY="--concurrency=$CONCURRENCY"
fi

exec 3>&1
status=$(exec 4>&1 >&3; (python setup.py testr --slowest --testr-args="--subunit $TESTRARGS $CONCURRENCY"; echo $? >&4 ) | subunit-trace -f) && exit $status
