# function definitions for neutron-lbaas devstack plugin

function neutron_lbaas_install {
    setup_develop $NEUTRON_LBAAS_DIR
    neutron_agent_lbaas_install_agent_packages
}

function neutron_agent_lbaas_install_agent_packages {
    if is_ubuntu; then
        if [[ ${OFFLINE} == False && ${os_CODENAME} =~ (trusty|precise) ]]; then
            # Check for specific version of Ubuntu that requires backports repository for haproxy 1.5.14 or greater
            BACKPORT="deb http://archive.ubuntu.com/ubuntu ${os_CODENAME}-backports main restricted universe multiverse"
            BACKPORT_EXISTS=$(grep ^ /etc/apt/sources.list /etc/apt/sources.list.d/* | grep "${BACKPORT}") || true
            if [[ -z "${BACKPORT_EXISTS}" ]]; then
                sudo add-apt-repository "${BACKPORT}" -y
            fi
            sudo apt-get update
            sudo apt-get install haproxy -t ${os_CODENAME}-backports
        fi
    fi
    if is_fedora || is_suse; then
        install_package haproxy
    fi
}

function neutron_lbaas_configure_common {
    if is_service_enabled $LBAAS_V1 && is_service_enabled $LBAAS_V2; then
        die $LINENO "Do not enable both Version 1 and Version 2 of LBaaS."
    fi

    cp $NEUTRON_LBAAS_DIR/etc/neutron_lbaas.conf.sample $NEUTRON_LBAAS_CONF

    if is_service_enabled $LBAAS_V1; then
        inicomment $NEUTRON_LBAAS_CONF service_providers service_provider
        iniadd $NEUTRON_LBAAS_CONF service_providers service_provider $NEUTRON_LBAAS_SERVICE_PROVIDERV1
    elif is_service_enabled $LBAAS_V2; then
        inicomment $NEUTRON_LBAAS_CONF service_providers service_provider
        iniadd $NEUTRON_LBAAS_CONF service_providers service_provider $NEUTRON_LBAAS_SERVICE_PROVIDERV2
    fi

    if is_service_enabled $LBAAS_V1; then
        _neutron_service_plugin_class_add $LBAASV1_PLUGIN
        iniset $NEUTRON_CONF DEFAULT service_plugins $Q_SERVICE_PLUGIN_CLASSES
    elif is_service_enabled $LBAAS_V2; then
        _neutron_service_plugin_class_add $LBAASV2_PLUGIN
        iniset $NEUTRON_CONF DEFAULT service_plugins $Q_SERVICE_PLUGIN_CLASSES
    fi

    # Ensure config is set up properly for authentication neutron-lbaas
    iniset $NEUTRON_LBAAS_CONF service_auth auth_url $AUTH_URL
    iniset $NEUTRON_LBAAS_CONF service_auth admin_tenant_name $ADMIN_TENANT_NAME
    iniset $NEUTRON_LBAAS_CONF service_auth admin_user $ADMIN_USER
    iniset $NEUTRON_LBAAS_CONF service_auth admin_password $ADMIN_PASSWORD
    iniset $NEUTRON_LBAAS_CONF service_auth auth_version $AUTH_VERSION

    # Ensure config is set up properly for authentication neutron
    iniset $NEUTRON_CONF service_auth auth_url $AUTH_URL
    iniset $NEUTRON_CONF service_auth admin_tenant_name $ADMIN_TENANT_NAME
    iniset $NEUTRON_CONF service_auth admin_user $ADMIN_USER
    iniset $NEUTRON_CONF service_auth admin_password $ADMIN_PASSWORD
    iniset $NEUTRON_CONF service_auth auth_version $AUTH_VERSION

    _neutron_deploy_rootwrap_filters $NEUTRON_LBAAS_DIR

    $NEUTRON_BIN_DIR/neutron-db-manage --subproject neutron-lbaas --config-file $NEUTRON_CONF --config-file /$Q_PLUGIN_CONF_FILE upgrade head
}

function neutron_lbaas_configure_agent {
    if [ -z "$1" ]; then
        mkdir -p $LBAAS_AGENT_CONF_PATH
    fi
    conf=${1:-$LBAAS_AGENT_CONF_FILENAME}
    cp $NEUTRON_LBAAS_DIR/etc/lbaas_agent.ini.sample $conf

    # ovs_use_veth needs to be set before the plugin configuration
    # occurs to allow plugins to override the setting.
    iniset $conf DEFAULT ovs_use_veth $Q_OVS_USE_VETH

    neutron_plugin_setup_interface_driver $conf

    if is_fedora; then
        iniset $conf DEFAULT user_group "nobody"
        iniset $conf haproxy user_group "nobody"
    fi
}

function neutron_lbaas_generate_config_files {
    # Uses oslo config generator to generate LBaaS sample configuration files
    (cd $NEUTRON_LBAAS_DIR && exec ./tools/generate_config_file_samples.sh)
}

function neutron_lbaas_start {
    local is_run_process=True

    if is_service_enabled $LBAAS_V1; then
        LBAAS_VERSION="q-lbaas"
        AGENT_LBAAS_BINARY=${AGENT_LBAASV1_BINARY}
    elif is_service_enabled $LBAAS_V2; then
        LBAAS_VERSION="q-lbaasv2"
        AGENT_LBAAS_BINARY=${AGENT_LBAASV2_BINARY}
        # Octavia doesn't need the LBaaS V2 service running.  If Octavia is the
        # only provider then don't run the process.
        if [[ "$NEUTRON_LBAAS_SERVICE_PROVIDERV2" == "$NEUTRON_LBAAS_SERVICE_PROVIDERV2_OCTAVIA" ]]; then
            is_run_process=False
        fi
    fi

    if [[ "$is_run_process" == "True" ]] ; then
        run_process $LBAAS_VERSION "python $AGENT_LBAAS_BINARY --config-file $NEUTRON_CONF --config-file $NEUTRON_LBAAS_CONF --config-file=$LBAAS_AGENT_CONF_FILENAME"
    fi
}

function neutron_lbaas_stop {
    pids=$(ps aux | awk '/haproxy/ { print $2 }')
    [ ! -z "$pids" ] && sudo kill $pids
}

function neutron_lbaas_cleanup {

    # delete all namespaces created by neutron-lbaas

    for ns in $(sudo ip netns list | grep -o -E '(qlbaas|nlbaas)-[0-9a-f-]*'); do
        sudo ip netns delete ${ns}
    done
}

# check for service enabled
if is_service_enabled $LBAAS_ANY; then

    if ! is_service_enabled q-svc; then
        die "The neutron q-svc service must be enabled to use $LBAAS_ANY"
    fi

    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        # Perform installation of service source
        echo_summary "Installing neutron-lbaas"
        neutron_lbaas_install

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        # Configure after the other layer 1 and 2 services have been configured
        echo_summary "Configuring neutron-lbaas"
        neutron_lbaas_generate_config_files
        neutron_lbaas_configure_common
        neutron_lbaas_configure_agent

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        # Initialize and start the LBaaS service
        echo_summary "Initializing neutron-lbaas"
        neutron_lbaas_start
    fi
fi

if [[ "$1" == "unstack" ]]; then
    # Shut down LBaaS services
    neutron_lbaas_stop
fi

if [[ "$1" == "clean" ]]; then
    # Remove state and transient data
    # Remember clean.sh first calls unstack.sh
    neutron_lbaas_cleanup
fi
