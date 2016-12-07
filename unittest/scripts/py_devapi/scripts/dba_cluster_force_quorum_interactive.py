# Assumptions: smart deployment rountines available
#@ Initialization
localhost = "localhost"
deployed_here = reset_or_deploy_sandboxes()
uri1 = "%s:%s" % (localhost, __mysql_sandbox_port1)
uri2 = "%s:%s" % (localhost, __mysql_sandbox_port2)
uri3 = "%s:%s" % (localhost, __mysql_sandbox_port3)

shell.connect({'host': localhost, 'port': __mysql_sandbox_port1, 'user': 'root', 'password': 'root'})

#@<OUT> create cluster
if __have_ssl:
  cluster = dba.create_cluster('dev')
else:
  cluster = dba.create_cluster('dev', {'memberSsl':False})

cluster.status();

#@ Add instance 2
if __have_ssl:
  cluster.add_instance({'host':localhost, 'port': __mysql_sandbox_port2, 'password':'root'})
else:
  cluster.add_instance({'host':localhost, 'port': __mysql_sandbox_port2, 'password':'root', 'memberSsl':False})

# Waiting for the second added instance to become online
wait_slave_state(cluster, uri2, "ONLINE")

#@ Add instance 3
if __have_ssl:
  cluster.add_instance({'host':localhost, 'port': __mysql_sandbox_port3, 'password':'root'})
else:
  cluster.add_instance({'host':localhost, 'port': __mysql_sandbox_port3, 'password':'root', 'memberSsl':False})

# Waiting for the third added instance to become online
wait_slave_state(cluster, uri3, "ONLINE")

# Kill instance 2
if __sandbox_dir:
  dba.kill_sandbox_instance(__mysql_sandbox_port2, {'sandboxDir':__sandbox_dir})
else:
  dba.kill_sandbox_instance(__mysql_sandbox_port2)

# Waiting for the second added instance to become unreachable
wait_slave_state(cluster, uri2, "UNREACHABLE")

# Kill instance 3
if __sandbox_dir:
  dba.kill_sandbox_instance(__mysql_sandbox_port3, {'sandboxDir':__sandbox_dir})
else:
  dba.kill_sandbox_instance(__mysql_sandbox_port3)

# Waiting for the third added instance to become unreachable
wait_slave_state(cluster, uri3, "UNREACHABLE")

# Start instance 2
if __sandbox_dir:
  dba.start_sandbox_instance(__mysql_sandbox_port2, {'sandboxDir':__sandbox_dir})
else:
  dba.start_sandbox_instance(__mysql_sandbox_port2)

# Start instance 3
if __sandbox_dir:
  dba.start_sandbox_instance(__mysql_sandbox_port3, {'sandboxDir':__sandbox_dir})
else:
  dba.start_sandbox_instance(__mysql_sandbox_port3)

#@<OUT> Cluster status
cluster.status();

#@ Cluster.force_quorum_using_partition_of errors
cluster.force_quorum_using_partition_of();
cluster.force_quorum_using_partition_of(1);
cluster.force_quorum_using_partition_of("");
cluster.force_quorum_using_partition_of(1, "");

#@ Cluster.force_quorum_using_partition_of error interactive
if __have_ssl:
  cluster.force_quorum_using_partition_of({'host':localhost, 'port': __mysql_sandbox_port2});
else:
  cluster.force_quorum_using_partition_of({'host':localhost, 'port': __mysql_sandbox_port2, 'memberSsl':False});

#@<OUT> Cluster.force_quorum_using_partition_of success
if __have_ssl:
  cluster.force_quorum_using_partition_of({'host':localhost, 'port': __mysql_sandbox_port1});
else:
  cluster.force_quorum_using_partition_of({'host':localhost, 'port': __mysql_sandbox_port1, 'memberSsl':False})

#@<OUT> Cluster status after force quorum
cluster.status();

#@ Rejoin instance 2
if __have_ssl:
  cluster.rejoin_instance({'host':localhost, 'port': __mysql_sandbox_port2, 'password':'root'})
else:
  cluster.rejoin_instance({'host':localhost, 'port': __mysql_sandbox_port2, 'password':'root', 'memberSsl':False})

# Waiting for the second rejoined instance to become online
wait_slave_state(cluster, uri2, "ONLINE");

#@ Rejoin instance 3
if __have_ssl:
  cluster.rejoin_instance({'host':localhost, 'port': __mysql_sandbox_port3, 'password':'root'})
else:
  cluster.rejoin_instance({'host':localhost, 'port': __mysql_sandbox_port3, 'password':'root', 'memberSsl':False})

# Waiting for the third rejoined instance to become online
wait_slave_state(cluster, uri3, "ONLINE");

#@<OUT> Cluster status after rejoins
cluster.status();

session.close();

#@ Finalization
# Will delete the sandboxes ONLY if this test was executed standalone
if (deployed_here):
  cleanup_sandboxes(True)
else:
  reset_or_deploy_sandboxes()