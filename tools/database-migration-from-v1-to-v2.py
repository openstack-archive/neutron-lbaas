# Copyright 2016 Hewlett Packard Enterprise Development Company LP
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
This script will migrate the database neutron-lbaas from v1 to v2.

Example usage:

To manually test migration from v1 to v2 with devstack:

 - Create 2 nova instances on private network
 - Add secgroup rule to allow ssh etc
 - SSH into nova instance and run this if you want a very simple web server
 - Create lb pool1 on private subnet
 - Create 2 lb members on pool1
 - Create lb vip load balancing pool1 and vip address on private-subnet
 - Create a Healthmonitor and associated it with  pool1
 - Direct to /neutron-lbaas/neutron_lbaas/db/migration
 - Create a revision file
 - Edit the created file and fill the content properly with this file
 - Run alembic upgrade head
 - Stop v1 neutron service and v1 lbaas agent
 - Change Neutron.conf and Neutron_lbaas.conf to v2
 - Restart v2 neutron service and v2 lbaas agent
 - Run the migration upgrade code
 - Check the database table to confirm the migration is all set

"""

# revision identifiers, used by Alembic.
# revision = depdens on the db migration version #
down_revision = None
branch_labels = None
depends_on = None

listener_protocols = sa.Enum("HTTP", "HTTPS", "TCP",
                             name="listener_protocolsv2")
pool_protocols = sa.Enum("HTTP", "HTTPS", "TCP",
                         name="pool_protocolsv2")
sesssionpersistences_type = sa.Enum("SOURCE_IP", "HTTP_COOKIE", "APP_COOKIE",
                                    name="sesssionpersistences_typev2")
lb_algorithms = sa.Enum("ROUND_ROBIN", "LEAST_CONNECTIONS", "SOURCE_IP",
                        name="lb_algorithmsv2")
pools_type = sa.Enum("PING", "TCP", "HTTP", "HTTPS",
                     name="pools_typev2")
healthmonitors_type = sa.Enum("PING", "TCP", "HTTP", "HTTPS",
                              name="healthmonitors_typev2")

lbaas_pools = sa.Table('lbaas_pools',
                       sa.MetaData(),
                       sa.Column('id', sa.Integer()),
                       sa.Column('tenant_id', sa.String(255), nullable=True),
                       sa.Column('name', sa.String(255), nullable=True),
                       sa.Column('description', sa.String(255), nullable=True),
                       sa.Column('protocol', pool_protocols, nullable=False),
                       sa.Column('lb_algorithm', lb_algorithms, nullable=False),
                       sa.Column('healthmonitor_id', sa.String(36),
                                 nullable=True),
                       sa.Column('provisioning_status', sa.String(16),
                                 nullable=False),
                       sa.Column('operating_status', sa.String(16),
                                 nullable=False),
                       sa.Column('admin_state_up', sa.Boolean(),
                                 nullable=False),
                       sa.PrimaryKeyConstraint(u'id'),
                       sa.UniqueConstraint(u'healthmonitor_id'),
                       sa.ForeignKeyConstraint([u'healthmonitor_id'],
                                               [u'lbaas_healthmonitors.id'])

                       )

lbaas_healthmonitors = sa.Table('lbaas_healthmonitors',
                                sa.MetaData(),
                                sa.Column('id', sa.Integer()),
                                sa.Column('tenant_id', sa.String(255),
                                          nullable=True),
                                sa.Column('type', healthmonitors_type,
                                          nullable=False),
                                sa.Column('delay', sa.Integer(),
                                          nullable=False),
                                sa.Column('timeout', sa.Integer(),
                                          nullable=False),
                                sa.Column('max_retries', sa.Integer(),
                                          nullable=False),
                                sa.Column('http_method', sa.String(16),
                                          nullable=True),
                                sa.Column('url_path', sa.String(255),
                                          nullable=True),
                                sa.Column('expected_codes', sa.String(64),
                                          nullable=True),
                                sa.Column('provisioning_status', sa.String(64),
                                          nullable=True),
                                sa.Column('admin_state_up', sa.Boolean(),
                                          nullable=False),
                                sa.PrimaryKeyConstraint(u'id')
                                )

lbaas_members = sa.Table('lbaas_members',
                         sa.MetaData(),
                         sa.Column(u'tenant_id', sa.String(255), nullable=True),
                         sa.Column(u'id', sa.String(36), nullable=False),
                         sa.Column(u'pool_id', sa.String(36), nullable=False),
                         sa.Column(u'subnet_id', sa.String(36), nullable=True),
                         sa.Column(u'address', sa.String(64), nullable=False),
                         sa.Column(u'protocol_port', sa.Integer(),
                                   nullable=False),
                         sa.Column(u'weight', sa.Integer(), nullable=True),
                         sa.Column(u'provisioning_status', sa.String(36), nullable=False),
		         sa.Column(u'operating_status', sa.String(36), nullable=False),
                         sa.Column(u'admin_state_up', sa.Boolean(),
                                   nullable=False),
                         sa.PrimaryKeyConstraint(u'id'),
                         sa.ForeignKeyConstraint([u'pool_id'],
                                                 [u'lbaas_pools.id']),
                         sa.UniqueConstraint(u'pool_id', u'address',
                                             u'protocol_port',
                                             name=u'uniq_pool_address_port_v2')
                         )

lbaas_loadbalancers = sa.Table('lbaas_loadbalancers',
                               sa.MetaData(),
                               sa.Column(u'tenant_id', sa.String(255), nullable=True),
                               sa.Column(u'id', sa.String(36), nullable=False),
                               sa.Column(u'name', sa.String(255), nullable=True),
                               sa.Column(u'description', sa.String(255), nullable=True),
                               sa.Column(u'vip_port_id', sa.String(36), nullable=True),
                               sa.Column(u'vip_subnet_id', sa.String(36), nullable=False),
                               sa.Column(u'vip_address', sa.String(36), nullable=True),
                               sa.Column(u'admin_state_up', sa.Boolean(), nullable=False),
                               sa.Column(u'provisioning_status', sa.String(36), nullable=False),
                               sa.Column(u'operating_status', sa.String(36), nullable=False),
                               sa.ForeignKeyConstraint([u'vip_port_id'], [u'ports.id'],name=u'fk_lbaas_loadbalancers_ports_id'),
                               sa.PrimaryKeyConstraint(u'id')
                               )

lbaas_sessionpersistences = sa.Table('lbaas_sessionpersistences',
                                     sa.MetaData(),
                                     sa.Column(u'pool_id', sa.String(36),
                                               nullable=False),
                                     sa.Column(u'type',
                                               sesssionpersistences_type,
                                               nullable=False),
                                     sa.Column(u'cookie_name', sa.String(1024),
                                               nullable=True),
                                     sa.ForeignKeyConstraint([u'pool_id'], [
                                         u'lbaas_pools.id']),
                                     sa.PrimaryKeyConstraint(u'pool_id')
                                     )
lbaas_loadbalanceragentbindings = sa.Table('lbaas_loadbalanceragentbindings',
                                           sa.MetaData(),
                                           sa.Column(u'loadbalancer_id',
                                                     sa.String(36),
                                                     nullable=False),
                                           sa.Column(u'agent_id', sa.String(36),
                                                     nullable=False),
                                           sa.ForeignKeyConstraint(
                                               [u'loadbalancer_id'],
                                               [u'lbaas_loadbalancers.id'],
                                               ondelete="CASCADE"),
                                           sa.ForeignKeyConstraint(
                                               [u'agent_id'], [u'agents.id'],
                                               ondelete="CASCADE"),
                                           sa.PrimaryKeyConstraint(
                                               u'loadbalancer_id')
                                           )
lbaas_loadbalancer_statistics = sa.Table('lbaas_loadbalancer_statistics',
                                         sa.MetaData(),
                                         sa.Column(u'loadbalancer_id',
                                                   sa.String(36),
                                                   nullable=False),
                                         sa.Column(u'bytes_in', sa.BigInteger(),
                                                   nullable=False),
                                         sa.Column(u'bytes_out',
                                                   sa.BigInteger(),
                                                   nullable=False),
                                         sa.Column(u'active_connections',
                                                   sa.BigInteger(),
                                                   nullable=False),
                                         sa.Column(u'total_connections',
                                                   sa.BigInteger(),
                                                   nullable=False),
                                         sa.PrimaryKeyConstraint(
                                             u'loadbalancer_id'),
                                         sa.ForeignKeyConstraint(
                                             [u'loadbalancer_id'],
                                             [u'lbaas_loadbalancers.id'])
                                         )

lbaas_listeners = sa.Table('lbaas_listeners',
                           sa.MetaData(),
                           sa.Column(u'tenant_id', sa.String(255),
                                     nullable=True),
                           sa.Column(u'id', sa.String(36), nullable=False),
                           sa.Column(u'name', sa.String(255), nullable=True),
                           sa.Column(u'description', sa.String(255),
                                     nullable=True),
                           sa.Column(u'protocol', listener_protocols,
                                     nullable=False),
                           sa.Column(u'protocol_port', sa.Integer(),
                                     nullable=False),
                           sa.Column(u'connection_limit', sa.Integer(),
                                     nullable=True),
                           sa.Column(u'loadbalancer_id', sa.String(36),
                                     nullable=True),
                           sa.Column(u'default_pool_id', sa.String(36),
                                     nullable=True),
                           sa.Column(u'status', sa.String(16), nullable=False),
                           sa.Column(u'admin_state_up', sa.Boolean(),
                                     nullable=False),
                           sa.Column(u'provisioning_status', sa.String(36),
                                     nullable=False),
                           sa.Column(u'operating_status', sa.String(36),
                                     nullable=False),
                           sa.Column(u'default_tls_container_id',
                                     sa.String(128), nullable=False),
                           sa.ForeignKeyConstraint([u'loadbalancer_id'],
                                                   [u'lbaas_loadbalancers.id']),
                           sa.ForeignKeyConstraint([u'default_pool_id'],
                                                   [u'lbaas_pools.id']),
                           sa.UniqueConstraint(u'default_pool_id'),
                           sa.UniqueConstraint(u'loadbalancer_id',
                                               u'protocol_port',
                                               name=u'uniq_loadbalancer_listener_port'),
                           sa.PrimaryKeyConstraint(u'id')
                           )

providerresourceassociations = sa.Table('providerresourceassociations',
                                         sa.MetaData(),
                                         sa.Column(u'provider_name',sa.String(255),nullable=False),
                                         sa.Column(u'resource_id',sa.String(36),nullable=False),
                                         sa.PrimaryKeyConstraint(u'provider_name',u'resource_id'),
                                         sa.UniqueConstraint(u'resource_id')
                                       )
def upgrade():
    connection = op.get_bind()
    # describe the part of the pools table we will query.
    pools = sa.sql.table('pools',
                         sa.sql.column('id', sa.String),
                         sa.sql.column('tenant_id', sa.String),
                         sa.sql.column('name', sa.String),
                         sa.sql.column('description', sa.String),
                         sa.sql.column('protocol', pool_protocols),
                         sa.sql.column('lb_method', lb_algorithms),
                         sa.sql.column('status', sa.String),
                         sa.sql.column('vip_id', sa.String),
                         sa.sql.column('subnet_id', sa.String),
                         sa.sql.column('admin_state_up', sa.Boolean)
                         )
    # describe the part of the healthmonitors table we will query.
    healthmonitors = sa.sql.table('healthmonitors',
                                  sa.sql.column('id', sa.String),
                                  sa.sql.column('tenant_id', sa.String),
                                  sa.sql.column('type', healthmonitors_type),
                                  sa.sql.column('delay', sa.Integer),
                                  sa.sql.column('timeout', sa.Integer),
                                  sa.sql.column('max_retries', sa.Integer),
                                  sa.sql.column('http_method', sa.String),
                                  sa.sql.column('url_path', sa.String),
                                  sa.sql.column('expected_codes', sa.String),
                                  sa.sql.column('admin_state_up', sa.Boolean)
                                  )
    # describe the part of the poolmonitorassociations table we will query.
    poolmonitorassociations = sa.sql.table('poolmonitorassociations',
                                           sa.sql.column('status', sa.String),
                                           sa.sql.column('pool_id', sa.String),
                                           sa.sql.column('monitor_id',
                                                         sa.String)
                                           )
    # describe the part of the members table we will query.
    members = sa.sql.table('members',
                           sa.sql.column('id', sa.String),
                           sa.sql.column('tenant_id', sa.String),
                           sa.sql.column('status', sa.String),
                           sa.sql.column('status_description', sa.String),
                           sa.sql.column('pool_id', sa.String),
                           sa.sql.column('address', sa.String),
                           sa.sql.column('protocol_port', sa.Integer),
                           sa.sql.column('weight', sa.Integer),
                           sa.sql.column('admin_state_up', sa.Boolean)
                           )
    # describe the part of the loadbalancer table we will query.
    vips = sa.sql.table('vips',
                        sa.sql.column('id', sa.String),
                        sa.sql.column('tenant_id', sa.String),
                        sa.sql.column('status', sa.String),
                        sa.sql.column('status_description', sa.String),
                        sa.sql.column('name', sa.String),
                        sa.sql.column('description', sa.String),
                        sa.sql.column('port_id', sa.String),
                        sa.sql.column('protocol_port', sa.Integer),
                        sa.sql.column('protocol', pool_protocols),
                        sa.sql.column('pool_id', sa.String),
                        sa.sql.column('admin_state_up', sa.Boolean),
                        sa.sql.column('connection_limit', sa.Integer)
                        )
    # describe the part of the ipallocations table we will query.
    ipallocations = sa.sql.table('ipallocations',
                                 sa.sql.column('port_id', sa.String),
                                 sa.sql.column('ip_address', sa.String),
                                 sa.sql.column('subnet_id', sa.String),
                                 sa.sql.column('network_id', sa.String),
                                 )

    # describe the part of the sessionpersistences table we will query.
    sessionpersistences = sa.sql.table('sessionpersistences',
                                       sa.sql.column('vip_id', sa.String),
                                       sa.sql.column('type',
                                                     sesssionpersistences_type),
                                       sa.sql.column('cookie_name', sa.String),
                                       )
    # describe the part of the poolstatisticss table we will query
    poolstatisticss = sa.sql.table('poolstatisticss',
                                   sa.sql.column('pool_id', sa.String),
                                   sa.sql.column('bytes_in', sa.BigInteger),
                                   sa.sql.column('bytes_out', sa.BigInteger),
                                   sa.sql.column('active_connections',
                                                 sa.BigInteger),
                                   sa.sql.column('total_connections',
                                                 sa.BigInteger)
                                   )
    sql_listeners = "select vips.tenant_id,vips.id,vips.name," \
                    "vips.description,vips.protocol,vips.protocol_port," \
                    "vips.connection_limit,lbaas_loadbalancers.id AS " \
                    "loadbalancer_id,vips.pool_id AS default_pool_id," \
                    "vips.admin_state_up," \
                    "lbaas_loadbalancers.provisioning_status AS " \
                    "provisioning_status,lbaas_loadbalancers.operating_status " \
                    "AS operating_status from vips join lbaas_loadbalancers " \
                    "on vips.port_id = lbaas_loadbalancers.vip_port_id where  provisioning_status='ACTIVE';"

    # check if we can migrate pools table or not, when its related
    # healthmonitors are more than two, we will not move and return msg.
    sql_validate_pool = "select count(tenant_id) from healthmonitors " \
                    "where tenant_id =(select tenant_id from pools)"
    result = connection.execute(sql_validate_pool)
    flag = True
    for row in result:
        if row[0] > 1:
            flag = False
            downgrade()
            break
    if flag:
        print("we can upgrade datatables for v2!")
        # Execute the query and insert the results into the
        # 'lb_healthmonitors'table.
        sqlstr_hm = "select healthmonitors.id,healthmonitors.tenant_id," \
                "healthmonitors.type,healthmonitors.delay, " \
                "healthmonitors.timeout,healthmonitors.max_retries, " \
                "healthmonitors.http_method,healthmonitors.url_path," \
                "healthmonitors.expected_codes," \
                "healthmonitors.admin_state_up," \
                "poolmonitorassociations.status AS provisioning_status " \
                "from healthmonitors join  poolmonitorassociations on " \
                "poolmonitorassociations.monitor_id = healthmonitors.id where poolmonitorassociations.status='ACTIVE' "

        r_hm = connection.execute(sqlstr_hm)
        for row in r_hm:
            connection.execute(lbaas_healthmonitors.insert().values(
                id=row.id,
                tenant_id=row.tenant_id,
                type=row.type,
                delay=row.delay,
                timeout=row.timeout,
                max_retries=row.max_retries,
                http_method=row.http_method,
                url_path=row.url_path,
                expected_codes=row.expected_codes,
                provisioning_status=row.provisioning_status,
                admin_state_up=row.admin_state_up)
            )
        r_hm.close()
        # move table pools
        sqlstr_pools = "select pools.id,pools.tenant_id,pools.name," \
                   "pools.description,pools.protocol," \
                   "pools.lb_method," \
                   "pools.status,pools.admin_state_up," \
                   "poolmonitorassociations.status AS " \
                   "provisioning_status," \
                   "poolmonitorassociations.monitor_id AS " \
                   "healthmonitor_id " \
                   "from pools join poolmonitorassociations on " \
                   "pools.id = poolmonitorassociations.pool_id where poolmonitorassociations.status='ACTIVE';"

        r_pool = connection.execute(sqlstr_pools)
        for row in r_pool:
            connection.execute(lbaas_pools.insert().values(
                id=row.id,
                tenant_id=row.tenant_id,
                name=row.name,
                description=row.description,
                protocol=row.protocol,
                lb_algorithm=row.lb_method,
                operating_status=row.status,
                provisioning_status=row.provisioning_status,
                healthmonitor_id=row.healthmonitor_id,
                admin_state_up=row.admin_state_up)
            )
        r_pool.close()
        # move table members
        sqlstr_members = "select members.id, members.tenant_id," \
                         "members.status as operating_status, members.pool_id," \
                         "pools.subnet_id AS subnet_id,members.address," \
                         "members.protocol_port,members.weight," \
                         "members.admin_state_up,lbaas_pools.provisioning_" \
                         "status AS provisioning_status from members join " \
                         "lbaas_pools on members.pool_id = lbaas_pools.id " \
                         "join pools on pools.id=lbaas_pools.id where  provisioning_status='ACTIVE';"
        r_member = connection.execute(sqlstr_members)
        for row in r_member:
            connection.execute(lbaas_members.insert().values(
                id=row.id,
                tenant_id=row.tenant_id,
                operating_status=row.operating_status,
                provisioning_status=row.provisioning_status,
                pool_id=row.pool_id,
                subnet_id=row.subnet_id,
                address=row.address,
                protocol_port=row.protocol_port,
                weight=row.weight,
                admin_state_up=row.admin_state_up)
            )
        r_member.close()
        # move table load balancers
        sql_lb = "select vips.tenant_id,vips.name, vips.description," \
                 "vips.port_id AS vip_port_id,pools.subnet_id AS " \
                 "vip_subnet_id," \
                 "ipallocations.ip_address AS vip_address,vips.status, " \
                 "vips.admin_state_up from vips join pools on " \
                 "vips.pool_id = pools.id join ipallocations on " \
                 "pools.subnet_id = ipallocations.subnet_id and " \
                 "vips.port_id = ipallocations.port_id"

        r_lb = connection.execute(sql_lb)
        for row in r_lb:
            connection.execute(lbaas_loadbalancers.insert().values(
                id=uuidutils.generate_uuid(),
                tenant_id=row.tenant_id,
                name=row.name,
                description=row.description,
                vip_port_id=row.vip_port_id,
                vip_subnet_id=row.vip_subnet_id,
                vip_address=row.vip_address,
                operating_status=row.status,
                provisioning_status='ONLINE',
                admin_state_up=row.admin_state_up)
            )
        r_lb.close()
        sql_haproxy = "select id from lbaas_loadbalancers"
        r_haproxy = connection.execute(sql_haproxy)
        for row in r_haproxy:
             connection.execute(providerresourceassociations.insert().values(
                provider_name='haproxy',
                resource_id=row.id)
            )
        r_haproxy.close()

        sql_sessionpersistences = "select vips.pool_id AS pool_id," \
                              "sessionpersistences.type," \
                              "sessionpersistences.cookie_name " \
                              "from sessionpersistences join vips on " \
                              "sessionpersistences.vip_id=vips.id"

        r_ss = connection.execute(sql_sessionpersistences)
        for row in r_ss:
            connection.execute(lbaas_sessionpersistences.insert().values(
                pool_id=row.pool_id,
                type=row.type,
                cookie_name=row.cookie_name)
            )
        r_ss.close()
        sql_listeners = "select vips.tenant_id,vips.id,vips.name," \
                        "vips.description,vips.protocol,vips.protocol_port," \
                        "vips.connection_limit,lbaas_loadbalancers.id AS " \
                        "loadbalancer_id,vips.pool_id AS default_pool_id," \
                        "vips.admin_state_up," \
                        "lbaas_loadbalancers.provisioning_status AS " \
                        "provisioning_status,lbaas_loadbalancers.operating_status " \
                        "AS operating_status from vips join lbaas_loadbalancers " \
                        "on vips.port_id = lbaas_loadbalancers.vip_port_id where  provisioning_status='ACTIVE';"

        r_listeners = connection.execute(sql_listeners)
        for row in r_listeners:
            connection.execute(lbaas_listeners.insert().values(
                tenant_id=row.tenant_id,
                id=row.id,
                name=row.name,
                description=row.description,
                protocol=row.protocol,
                protocol_port=row.protocol_port,
                connection_limit=row.connection_limit,
                loadbalancer_id=row.loadbalancer_id,
                default_pool_id=row.default_pool_id,
                admin_state_up=row.admin_state_up,
                provisioning_status=row.provisioning_status,
                operating_status=row.operating_status,
                default_tls_container_id=None)
            )
        r_listeners.close()
        sql_poolloadbalanceragentbindings = "select lbaas_listeners.loadbalancer_id AS " \
                                           "loadbalancer_id," \
                                        "poolloadbalanceragentbindings.agent_id" \
                                        " from poolloadbalanceragentbindings " \
                                        "join lbaas_listeners on " \
                                        "poolloadbalanceragentbindings.pool_id=lbaas_listeners.default_pool_id"
        r_poolbindings = connection.execute(sql_poolloadbalanceragentbindings)
        for row in r_poolbindings:
            connection.execute(lbaas_loadbalanceragentbindings.insert().values(
                loadbalancer_id=row.loadbalancer_id,
                agent_id=row.agent_id)
            )
        r_poolbindings.close()

        sql_poolstatisticss = "select lbaas_listeners.loadbalancer_id AS loadbalancer_id," \
                          "poolstatisticss.bytes_in," \
                          "poolstatisticss.bytes_out," \
                          "poolstatisticss.active_connections," \
                          "poolstatisticss.total_connections " \
                          "from poolstatisticss " \
                          "join lbaas_listeners on " \
                          "poolstatisticss.pool_id=lbaas_listeners.default_pool_id"

        r_poolstatisticss = connection.execute(sql_poolstatisticss)
        for row in r_poolstatisticss:
            connection.execute(lbaas_loadbalancer_statistics.insert().values(
                loadbalancer_id=row.loadbalancer_id,
                bytes_in=row.bytes_in,
                bytes_out=row.bytes_out,
                active_connections=row.active_connections,
                total_connections=row.total_connections)
            )
        r_poolstatisticss.close()
    else:
        print(
            "we cannot upgrade data tables due to multiple monitors linked with same pool")
        result.close()
        exit()
