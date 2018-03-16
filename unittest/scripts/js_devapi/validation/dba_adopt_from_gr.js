//@ Initialization
||

//@ Create cluster
||

//@ Adding instance to cluster
||

//@ Drop Metadata
||

//@ Check cluster status after drop metadata schema
||Cluster.status: This function is not available through a session to an instance belonging to an unmanaged replication group (RuntimeError)

//@ Create cluster adopting from GR
||

//@<OUT> Check cluster status
{
    "clusterName": "testCluster",
    "defaultReplicaSet": {
        "name": "default",
        "primary": "<<<real_hostname>>>:<<<__mysql_sandbox_port1>>>",
        "ssl": "<<<__ssl_mode>>>",
        "status": "OK_NO_TOLERANCE",
        "statusText": "Cluster is NOT tolerant to any failures.",
        "topology": {
            "<<<real_hostname>>>:<<<__mysql_sandbox_port1>>>": {
                "address": "<<<real_hostname>>>:<<<__mysql_sandbox_port1>>>",
                "mode": "R/W",
                "readReplicas": {},
                "role": "HA",
                "status": "ONLINE"
            },
            "<<<real_hostname>>>:<<<__mysql_sandbox_port2>>>": {
                "address": "<<<real_hostname>>>:<<<__mysql_sandbox_port2>>>",
                "mode": "R/O",
                "readReplicas": {},
                "role": "HA",
                "status": "ONLINE"
            }
        }
    },
    "groupInformationSourceMember": "mysql://root@<<<real_hostname>>>:<<<__mysql_sandbox_port1>>>"
}

//@ Finalization
||
