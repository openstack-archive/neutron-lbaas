# function definitions for neutron-lbaas devstack plugin

function neutron_lbaas_install {
    setup_develop $NEUTRON_LBAAS_DIR
    neutron_agent_lbaas_install_agent_packages
}

function neutron_agent_lbaas_install_agent_packages {
    if is_ubuntu; then
        sudo add-apt-repository ppa:vbernat/haproxy-1.5 -y
        sudo apt-get update
    fi
    if is_ubuntu || is_fedora || is_suse; then
        install_package haproxy
    fi
}

function neutron_lbaas_configure_common {
    if is_service_enabled $LBAAS_V1 && is_service_enabled $LBAAS_V2; then
        die $LINENO "Do not enable both Version 1 and Version 2 of LBaaS."
    fi

    cp $NEUTRON_LBAAS_DIR/etc/neutron_lbaas.conf $NEUTRON_LBAAS_CONF

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

    _neutron_deploy_rootwrap_filters $NEUTRON_LBAAS_DIR

    $NEUTRON_BIN_DIR/neutron-db-manage --service lbaas --config-file $NEUTRON_CONF --config-file /$Q_PLUGIN_CONF_FILE upgrade head
}

function neutron_lbaas_configure_agent {
    mkdir -p $LBAAS_AGENT_CONF_PATH
    cp $NEUTRON_LBAAS_DIR/etc/lbaas_agent.ini $LBAAS_AGENT_CONF_FILENAME

    # ovs_use_veth needs to be set before the plugin configuration
    # occurs to allow plugins to override the setting.
    iniset $LBAAS_AGENT_CONF_FILENAME DEFAULT ovs_use_veth $Q_OVS_USE_VETH

    neutron_plugin_setup_interface_driver $LBAAS_AGENT_CONF_FILENAME

    if is_fedora; then
        iniset $LBAAS_AGENT_CONF_FILENAME DEFAULT user_group "nobody"
        iniset $LBAAS_AGENT_CONF_FILENAME haproxy user_group "nobody"
    fi
}

function neutron_lbaas_start {
    if is_service_enabled $LBAAS_V1; then
        LBAAS_VERSION="q-lbaas"
        AGENT_LBAAS_BINARY=${AGENT_LBAASV1_BINARY}
    else
        LBAAS_VERSION="q-lbaasv2"
        AGENT_LBAAS_BINARY=${AGENT_LBAASV2_BINARY}
    fi

    run_process $LBAAS_VERSION "python $AGENT_LBAAS_BINARY --config-file $NEUTRON_CONF --config-file $NEUTRON_LBAAS_CONF --config-file=$LBAAS_AGENT_CONF_FILENAME"
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
