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
        elif [[ ${OFFLINE} == False ]]; then
            install_package haproxy
        fi
    fi
    if is_fedora || is_suse; then
        install_package haproxy
    fi
}

function neutron_lbaas_configure_common {
    cp $NEUTRON_LBAAS_DIR/etc/neutron_lbaas.conf.sample $NEUTRON_LBAAS_CONF
    cp $NEUTRON_LBAAS_DIR/etc/services_lbaas.conf.sample $SERVICES_LBAAS_CONF

    inicomment $NEUTRON_LBAAS_CONF service_providers service_provider
    iniadd $NEUTRON_LBAAS_CONF service_providers service_provider $NEUTRON_LBAAS_SERVICE_PROVIDERV2

    neutron_server_config_add $NEUTRON_LBAAS_CONF
    neutron_service_plugin_class_add $LBAASV2_PLUGIN

    # Ensure config is set up properly for authentication neutron-lbaas
    iniset $NEUTRON_LBAAS_CONF service_auth auth_url $OS_AUTH_URL$AUTH_ENDPOINT
    iniset $NEUTRON_LBAAS_CONF service_auth admin_tenant_name $ADMIN_TENANT_NAME
    iniset $NEUTRON_LBAAS_CONF service_auth admin_user $ADMIN_USER
    iniset $NEUTRON_LBAAS_CONF service_auth admin_password $ADMIN_PASSWORD
    iniset $NEUTRON_LBAAS_CONF service_auth auth_version $AUTH_VERSION

    # Ensure config is set up properly for authentication neutron
    iniset $NEUTRON_CONF service_auth auth_url $OS_AUTH_URL$AUTH_ENDPOINT
    iniset $NEUTRON_CONF service_auth admin_tenant_name $ADMIN_TENANT_NAME
    iniset $NEUTRON_CONF service_auth admin_user $ADMIN_USER
    iniset $NEUTRON_CONF service_auth admin_password $ADMIN_PASSWORD
    iniset $NEUTRON_CONF service_auth auth_version $AUTH_VERSION

    neutron_deploy_rootwrap_filters $NEUTRON_LBAAS_DIR

    $NEUTRON_BIN_DIR/neutron-db-manage --subproject neutron-lbaas --config-file $NEUTRON_CONF --config-file /$Q_PLUGIN_CONF_FILE upgrade head
}

function neutron_lbaas_configure_agent {
    if [ -z "$1" ]; then
        mkdir -p $LBAAS_AGENT_CONF_PATH
    fi
    conf=${1:-$LBAAS_AGENT_CONF_FILENAME}
    cp $NEUTRON_LBAAS_DIR/etc/lbaas_agent.ini.sample $conf

    if is_neutron_legacy_enabled; then
        # ovs_use_veth needs to be set before the plugin configuration
        # occurs to allow plugins to override the setting.
        iniset $conf DEFAULT ovs_use_veth $Q_OVS_USE_VETH
    fi

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

    if is_neutron_legacy_enabled; then
        LBAAS_VERSION="q-lbaasv2"
    else
        LBAAS_VERSION="neutron-lbaasv2"
    fi
    AGENT_LBAAS_BINARY=${AGENT_LBAASV2_BINARY}
    # Octavia doesn't need the LBaaS V2 service running.  If Octavia is the
    # only provider then don't run the process.
    if [[ "$NEUTRON_LBAAS_SERVICE_PROVIDERV2" == "$NEUTRON_LBAAS_SERVICE_PROVIDERV2_OCTAVIA" ]]; then
        is_run_process=False
    fi

    if [[ "$is_run_process" == "True" ]] ; then
        run_process $LBAAS_VERSION "$AGENT_LBAAS_BINARY --config-file $NEUTRON_CONF --config-file $NEUTRON_LBAAS_CONF --config-file=$LBAAS_AGENT_CONF_FILENAME"
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

    if ! is_service_enabled q-svc neutron-api; then
        die "The neutron-api/q-svc service must be enabled to use $LBAAS_ANY"
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
