#
# Copyright (c) 2016, 2017, Oracle and/or its affiliates. All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
#

"""This file contains the functionality to create a sandbox of MySQL servers.
"""

from __future__ import print_function
import errno
import getpass
import logging
import os
import time
import shutil
import subprocess

from mysql_gadgets.common import tools, server
from mysql_gadgets.common.constants import PATH_ENV_VAR, QUOTE_CHAR
from mysql_gadgets.common.config_parser import (MySQLOptionsParser,
                                                option_list_to_dictionary)
from mysql_gadgets.common.logger import CustomLevelLogger
from mysql_gadgets import exceptions, MIN_MYSQL_VERSION, MAX_MYSQL_VERSION

# get module logger
logging.setLoggerClass(CustomLevelLogger)
_LOGGER = logging.getLogger(__name__)

_CREATE_SANDBOX_CMD = ("{quote}{mysqld_path}{quote} --defaults-file={quote}"
                       "{config_file}{quote} --initialize-insecure")
_START_SERVER_CMD = ("{quote}{mysqld_path}{quote} --defaults-file={quote}"
                     "{config_file}{quote}")
_STOP_SERVER_CMD = ("{quote}{mysqladmin_path}{quote} --defaults-file="
                    "{quote}{config_file}{quote} shutdown -p")
_CREATE_RSA_SSL_FILES_CMD = ("{quote}{mysql_ssl_rsa_setup_path}{quote} "
                             "--datadir={quote}{datadir}{quote}")
_WIN_SCRIPT = "echo \"{message}\" & {content}\n"
_UNIX_SCRIPT = "#!/bin/sh\n\necho '{message}'; {content}\n"

# Timeout to wait for mysqld to start listening to connections
SANDBOX_TIMEOUT = 30
_MAX_RMTREE_RETRIES = 5
DEFAULT_SANDBOX_DIR = "~/mysql-sandboxes"

_LOCKFILE_NAME = "lockfile"
_SERVER_READY_LOG_MESSAGES = ("mysqld: ready for connections.",
                              "mysqld.exe: ready for connections.")

# Sandbox commands
SANDBOX = "sandbox"
SANDBOX_START = "start"
SANDBOX_STOP = "stop"
SANDBOX_KILL = "kill"
SANDBOX_CREATE = "create"
SANDBOX_DELETE = "delete"

# Error messages
_ERROR_OVERRIDE_PORT = ("Overriding the port value is not supported. Please "
                        "use the --port option to specify a different port "
                        "when creating the sandbox instance.")
_ERROR_CREATE_DIR = ("Unable to create {dir} directory '{dir_path}': "
                     "{error}")
_ERROR_NOT_CREATED = ("Cannot start MySQL sandbox for the given port because "
                      "it does not exist. Please use the '{0} {1}' command "
                      "first to create it.".format(SANDBOX, SANDBOX_CREATE))
_ERROR_VERSION_NOT_SUPPORTED = ("Provided mysqld executable '{0}' has a non "
                                "supported version: '{1}'. MySQL version must "
                                "be >= '{2}' and < '{3}'.")
_ERROR_CANNOT_FIND_TOOL = ("Could not find {exec_name} executable. "
                           "Make sure it is on {path_var_name}.")


def _create_start_script(script_name, script_path, mysqld, config_file):
    """Create a script file to start the Sandbox instance.

    :param script_name: Name of the script without the extension.
    :type script_name: str
    :param script_path: absolute path to the directory were the script will be
                        created.
    :type script_path: str
    :param mysqld: absolute path to the mysqld executable.
    :type mysqld: str
    :param config_file: absolute path to the configuration file to be used by
                        the sandbox.
    :type config_file: str
    :return: Path of the created script
    :rtype: str
    """
    start_path = os.path.join(script_path, script_name)

    if os.name == "nt":
        script_contents = _WIN_SCRIPT.format(
            message="Starting MySQL sandbox",
            # prefix 'START "" /b' is used to run command on the background
            content="START \"\" /b " + _START_SERVER_CMD)
        # add windows script extension
        start_path += ".bat"
    else:
        script_contents = _UNIX_SCRIPT.format(
            message="Starting MySQL sandbox",
            # suffix " &" is used to run command on the background
            content=_START_SERVER_CMD + " &")
        # add unix script extension
        start_path += ".sh"

    _LOGGER.debug("Creating start script on '%s'", start_path)
    try:
        with open(start_path, "w") as f:
            f.write(script_contents.format(quote=QUOTE_CHAR,
                                           mysqld_path=mysqld,
                                           config_file=config_file))
    except Exception as err:
        raise exceptions.GadgetError("Unable to create start script for "
                                     "sandbox instance", cause=err)
    _LOGGER.debug("Start script '%s' successfully created.", start_path)

    if os.name == "posix":
        # No need to set exec permissions on windows, also python can't do it.
        _LOGGER.debug("Changing permissions of start script to 700")
        os.chmod(start_path, 0o700)
        _LOGGER.debug("Permissions changed successfully.")
    return start_path


def _create_stop_script(script_name, script_path, mysqladmin, config_file):
    """Create a script file to stop the Sandbox instance.

    :param script_name: Name of the script without the extension.
    :type script_name: str
    :param script_path: absolute path to the directory were the script will be
                        created.
    :type script_path: str
    :param mysqladmin: absolute path to the mysqladmin executable.
    :type mysqladmin: str
    :param config_file: absolute path to the configuration file to be used by
                        the sandbox.
    :type config_file: str
    :return: Path of the created script
    :rtype: str
    """
    stop_path = os.path.join(script_path, script_name)
    stop_msg = ("Stopping MySQL sandbox using mysqladmin shutdown... "
                "Root password is required.")
    if os.name == "nt":
        script_contents = _WIN_SCRIPT.format(
            message=stop_msg,
            content=_STOP_SERVER_CMD)
        # add windows script extension
        stop_path += ".bat"
    else:
        script_contents = _UNIX_SCRIPT.format(
            message=stop_msg,
            content=_STOP_SERVER_CMD)
        # add unix script extension
        stop_path += ".sh"

    _LOGGER.debug("Creating stop script on '%s'", stop_path)
    try:
        with open(stop_path, "w") as f:
            f.write(script_contents.format(quote=QUOTE_CHAR,
                                           mysqladmin_path=mysqladmin,
                                           config_file=config_file))
    except Exception as err:
        raise exceptions.GadgetError("Unable to create stop script for "
                                     "sandbox instance", cause=err)
    _LOGGER.debug("Stop script '%s' successfully created.", stop_path)

    if os.name == "posix":
        # No need to set exec permissions on windows, also python can't do it.
        _LOGGER.debug("Changing permissions of stop script to 700")
        os.chmod(stop_path, 0o700)
        _LOGGER.debug("Permissions changed successfully.")
    return stop_path


def _find_basedir(mysqld_path):
    """Try to find the basedir of a server using the path of the mysqld exec.

    :param mysqld_path: Path of the mysqld executable
    :type mysqld_path: str
    :return: the path of the basedir if we can find it
    :rtype: str
    :raises: GadgetError if unable to find the basedir
    """
    _LOGGER.debug("Trying to find basedir for mysqld executable '%s'",
                  mysqld_path)
    # get the real path, any symbolic links
    mysqld_path = os.path.realpath(mysqld_path)
    # base directory were we will start searching. Usually executables are in
    # a bin folder
    base = os.path.abspath(os.path.join(mysqld_path, os.pardir,
                                        os.pardir))
    if os.path.isdir(base):
        _LOGGER.debug("Guessing basedir is at '%s'", base)
        return base
    else:
        raise exceptions.GadgetError("Could not find basedir for mysqld "
                                     "executable '{0}'".format(mysqld_path))


def _get_sandbox_dirs(**kwargs):
    """ Calculates the absolute sandbox paths from the kwargs dict.

    Returns the absolute path for the sandbox_base_dir and for the
    sandbox_dir from the kwargs dict provided.
    :param kwargs:      Keyword arguments:
                        sandbox_base_dir: base path for the created MySQL
                                          sandbox instances. Default is
                                          DEFAULT_SANDBOX_DIR.
                        port: The port where the sandbox will listen for
                              MySQL connections.
    :type kwargs:       dict

    :raises GadgetError: If the port is not specified.

    :returns: A tuple with the absolute path for the sandbox_base_dir as the
              first element and the absolute path for the sandbox as the second
              element.
    :rtype: tuple
    """
    # get mandatory values
    try:
        port = int(kwargs["port"])
    except KeyError:
        raise exceptions.GadgetError("It is mandatory to specify a port.")
    # Get default values for optional variables
    sandbox_base_dir = os.path.normpath(os.path.expanduser(kwargs.get(
        "sandbox_base_dir", DEFAULT_SANDBOX_DIR)))

    # Convert sandbox_base_dir to an absolute path if it is not already one.
    sandbox_base_dir = tools.get_abs_path(sandbox_base_dir, os.getcwd())

    return sandbox_base_dir, os.path.join(sandbox_base_dir, str(port))


def _set_secure_file_priv(opt_override_dict, sandbox_dir):
    """Verify and update the secure_file_priv value.

    This methods checks if the secure_file_priv has been given with the --opt
    option, and in such case it creates the directory if it does not exists.
    If the value for secure_file_priv is not a full path (only a folder name)
    then a folder with the given name will be created inside the sandbox
    directory.

    Otherwise, if no secure_file_priv is given with the --opt, by default the
    secure_file_priv is overwritten and set to the 'mysql-files' folder inside
    the sandbox directory.

    :param opt_override_dict: The options provided with the --opt option to
                              add/update the configuration file.
    :type opt_override_dict: dict
    :param sandbox_dir: The path used by this sandbox (including the port).
    :type sandbox_dir: string

    :raise GadgetError: If the directory for the secure_file_priv can not be
                        created.
    """
    # Retrieve the secure_file_priv in case is provided.
    secure_file_priv = opt_override_dict.get('secure_file_priv', None)

    if secure_file_priv is None:
        # No value set for secure_file_priv, overwrite the default value.
        secure_file_priv = os.path.join(sandbox_dir, "mysql-files")
        # Check if secure_file_priv exists:
        if not os.path.isdir(secure_file_priv):
            # Try to create it if it does not exist
            try:
                os.makedirs(secure_file_priv)
            except OSError as err:
                raise exceptions.GadgetError(
                    _ERROR_CREATE_DIR.format(dir="secure-file-priv",
                                             dir_path=secure_file_priv,
                                             error=str(err)))

        # Update dictionary of options to overwrite the configuration file.
        opt_override_dict['secure_file_priv'] = \
            secure_file_priv.replace("\\", "/")
    else:
        # Check if the directory for secure_file_priv exists and create it
        # if need, otherwise nothing need to be done.
        secure_file_priv = os.path.normpath(os.path.expanduser(
            secure_file_priv))
        if not os.path.isdir(secure_file_priv):
            # Try to create it if it does not exist
            try:
                # if not a full path, create it in sandbox_dir
                tail, head = os.path.split(secure_file_priv)
                if not tail:
                    secure_file_priv = os.path.join(sandbox_dir,
                                                    head)
                if not os.path.isdir(secure_file_priv):
                    os.makedirs(secure_file_priv)
            except OSError as err:
                raise exceptions.GadgetError(
                    _ERROR_CREATE_DIR.format(dir="secure-file-priv",
                                             dir_path=secure_file_priv,
                                             error=str(err)))

            # Update dictionary of options to overwrite the configuration file.
            opt_override_dict["secure_file_priv"] = \
                secure_file_priv.replace("\\", "/")


def sandbox_exists(**kwargs):
    """Checks if a MySQL sandbox already exists.
    Returns true in case it exists and False otherwise.
    :param kwargs:      Keyword arguments:
                        port: The port where the sandbox will listen for
                               MySQL connections.
                        sandbox_base_dir: base path for the created MySQL
                                          sandbox instances. Default is
                                          DEFAULT_SANDBOX_DIR.
    :type kwargs:       dict
    :return: True if sandbox exists and False otherwise.
    :rtype: bool
    """
    # Get sandbox paths
    _, sandbox_dir = _get_sandbox_dirs(**kwargs)

    return os.path.isdir(sandbox_dir) and os.listdir(sandbox_dir)


# pylint: disable=R0915, R0914
def create_sandbox(**kwargs):
    """Create a new MySQL sandbox.
    :param kwargs:   Keyword arguments:
                     port: The port where the sandbox will listen for
                            MySQL connections.
                     passwd: password to be used for the root account in the
                             MySQL sandbox.
                     basedir: the directory that will be used as the basedir
                              of the MySQL sandbox instance.
                     mysqlx_port: the port where the sandbox will listen
                                  for the X-Protocol connections. Default
                                  value is <port>*10.
                     sandbox_base_dir: base path for the created MySQL
                                       sandbox instances. Default is
                                       DEFAULT_SANDBOX_DIR.
                     mysqld_path: Path to the mysqld executable. By default
                                  it will search the PATH of the system.
                     mysqladmin_path: Path to the mysqladmin executable. By
                                      default it will search the PATH of the
                                      system.
                     mysql_ssl_rsa_setup_path: Path to the mysql_ssl_rsa_setup
                                               executable. By default it will
                                               search the PATH of the system.
                     server_id: Server-id value of the MySQL sandbox
                                instance. By default a random id is used.
                     opt: list of additional values to save under the
                          [mysqld] section of the option file.
                     timeout: timeout in seconds to wait for the sandbox
                              instance to start listening for connections.
                     ignore_ssl_error: If false (default) the sandbox must be
                               created with support for SSL throwing an error
                               if SSL support cannot be added. If true no error
                               will be issued if SSL support cannot be provided
                               and SSL support will be skipped.
    :type kwargs:    dict
    """
    # get mandatory values
    try:
        port = int(kwargs["port"])
    except KeyError:
        raise exceptions.GadgetError("It is mandatory to specify a port.")
    password = kwargs.get("passwd")

    ignore_ssl_error = kwargs.get("ignore_ssl_error", False)

    # Get default values for optional variables
    timeout = kwargs.get("timeout", SANDBOX_TIMEOUT)

    mysqlx_port = int(kwargs.get("mysqlx_port", port * 10))
    # Verify if mysqlx port is valid.
    if (mysqlx_port < 1024 or mysqlx_port > 65535) and \
       "mysqlx_port" not in kwargs.keys():
        raise exceptions.GadgetError(
            "Invalid X port '{0}', it must be >= 1024 and <= 65535. "
            "Use a lower value for 'port' to generate a valid X port "
            "(by default, portx = port * 10), or use the 'portx' "
            "option to specify a custom value.".format(mysqlx_port))

    _, sandbox_dir = _get_sandbox_dirs(**kwargs)
    # Check if sandbox_dir is empty
    if os.path.isdir(sandbox_dir) and os.listdir(sandbox_dir):
        raise exceptions.GadgetError("The sandbox dir '{0}' is not empty."
                                     "".format(sandbox_dir))
    # If no value is provided for mysqld, by default search value on PATH
    mysqld_path = kwargs.get("mysqld_path",
                             tools.get_tool_path(None, "mysqld",
                                                 search_path=True,
                                                 required=False))
    if not mysqld_path:
        raise exceptions.GadgetError(_ERROR_CANNOT_FIND_TOOL.format(
            exec_name="mysqld", path_var_name=PATH_ENV_VAR))

    # If no value is provided for mysqladmin, by default search value on PATH
    mysqladmin_path = kwargs.get("mysqladmin_path",
                                 tools.get_tool_path(None, "mysqladmin",
                                                     search_path=True,
                                                     required=False))
    if not mysqladmin_path:
        raise exceptions.GadgetError(_ERROR_CANNOT_FIND_TOOL.format(
            exec_name="mysqladmin", path_var_name=PATH_ENV_VAR))

    # If no value is provided for mysql_ssl_rsa_setup, by default search value
    # on PATH
    mysql_ssl_rsa_setup_path = kwargs.get(
        "mysql_ssl_rsa_setup_path", tools.get_tool_path(
            None, "mysql_ssl_rsa_setup", search_path=True, required=False))

    if not mysql_ssl_rsa_setup_path and not ignore_ssl_error:
        raise exceptions.GadgetError(
            _ERROR_CANNOT_FIND_TOOL.format(exec_name="mysql_ssl_rsa_setup",
                                           path_var_name=PATH_ENV_VAR))

    # Checking if mysql, mysqladmin and mysql_ssl_rsa_setup meet requirements
    if not tools.is_executable(mysqld_path):
        raise exceptions.GadgetError(
            "Provided mysqld '{0}' is not a valid executable."
            "".format(mysqld_path))
    if not tools.is_executable(mysqladmin_path):
        raise exceptions.GadgetError(
            "Provided mysqladmin '{0}' is not a valid executable."
            "".format(mysqladmin_path))
    if not tools.is_executable(mysql_ssl_rsa_setup_path) and not \
            ignore_ssl_error:
        raise exceptions.GadgetError(
            "Provided mysql_ssl_rsa_setup '{0}' is not a valid executable."
            "".format(mysql_ssl_rsa_setup_path))

    mysqld_ver, version_str = server.get_mysqld_version(mysqld_path)
    if not MIN_MYSQL_VERSION <= mysqld_ver < MAX_MYSQL_VERSION:
        raise exceptions.GadgetError(
            _ERROR_VERSION_NOT_SUPPORTED.format(
                mysqld_path, version_str,
                '.'.join(str(i) for i in MIN_MYSQL_VERSION),
                '.'.join(str(i) for i in MAX_MYSQL_VERSION)))

    basedir = kwargs.get("basedir", None)
    if basedir is None:
        # If no value was provided, try to guess it from mysqld
        try:
            basedir = _find_basedir(mysqld_path)
        except exceptions.GadgetError:
            raise exceptions.GadgetError(
                "Unable to find the basedir for mysqld executable '{0}'. "
                "Please use the --basedir option to specify it."
                "".format(mysqld_path))

    # By default a random ID value.
    server_id = kwargs.get("server_id", server.generate_server_id())

    # Get list of options to override
    mysqld_opts = kwargs.get("opt", [])
    opt_override_dict = option_list_to_dictionary(mysqld_opts)

    # Datadir
    datadir = os.path.join(sandbox_dir, "sandboxdata")

    # pid file_path
    pidf_path = os.path.join(sandbox_dir, "{0}.pid".format(port))

    # Initialize new mysql sandbox
    # pylint: disable=E1101
    _LOGGER.step("Initializing new MySQL sandbox on '%s'.", sandbox_dir)
    # Check if sandbox_dir exists:
    if not os.path.isdir(sandbox_dir):
        # Try to create it if it does not exist
        try:
            os.makedirs(sandbox_dir)
        except OSError as err:
            raise exceptions.GadgetError(
                _ERROR_CREATE_DIR.format(dir="sandbox", dir_path=sandbox_dir,
                                         error=str(err)))

    # Update opt_override_dict with value used for secure_file_priv.
    _set_secure_file_priv(opt_override_dict, sandbox_dir)
    _LOGGER.debug("Option secure_file_priv will be set with value: %s",
                  opt_override_dict['secure_file_priv'])

    # Create option file dictionary
    # MySQL prefers Unix stile paths, so convert all paths to unix style
    opt_dict = {"mysqld": {
        "port": port,
        "loose_mysqlx_port": mysqlx_port,
        "server_id": server_id,
        "socket": os.path.join(sandbox_dir, "mysqld.sock").replace("\\", "/"),
        "loose_mysqlx_socket": os.path.join(sandbox_dir,
                                            "mysqlx.sock").replace("\\", "/"),
        "basedir": basedir.replace("\\", "/"),
        "datadir": datadir.replace("\\", "/"),
        "log_syslog": "OFF",  # Disable syslog to avoid issue on Windows.
        "report_port": port,
        "log_error": os.path.join(datadir, "error.log").replace("\\", "/"),
        "plugin_load": "mysqlx.so" if os.name == "posix" else "mysqlx.dll",
        "relay_log_info_repository": "TABLE",
        "binlog_checksum": "NONE",
        "master_info_repository": "TABLE",
        "gtid_mode": "ON",
        "log_slave_updates": "ON",
        "transaction_write_set_extraction": "XXHASH64",
        "binlog_format": "ROW",
        "log_bin": None,
        "enforce_gtid_consistency": "ON",
        "pid_file": pidf_path.replace("\\", '/'),
        # CSV cannot be disabled as myslqldump forcefully clones slow_log
        # and general_log tables on the clone operation.
        # MyISAM cannot be disabled as some tables on the mysql schema still
        # use it and the clone operation needs to recreate those tables
        # on the destination to make sure they are empty before filling them
        # with data (there is no option on mysqldump to truncate tables).
        "disabled_storage_engines": "BLACKHOLE,FEDERATED,ARCHIVE",
    }, "client": {
        "port": port,
        "user": "root",
        "protocol": "TCP",
    }}
    if opt_override_dict:
        # If port is one of the options to override raise exception
        _LOGGER.debug("Adding/Overriding option file values.")
        if "port" in opt_override_dict:
            raise exceptions.GadgetError(_ERROR_OVERRIDE_PORT)
        # override mysqld dict with options received from cmd line
        opt_dict["mysqld"].update(opt_override_dict)
    # Create option file
    optf_path = tools.create_option_file(opt_dict, "my.cnf", sandbox_dir)

    # If on Linux, create a temporary copy of the mysqld binary to avoid
    # possible AppArmor or SELinux issues.
    # Note: Creating a symbolic link will not solve the problem.
    if os.name != "nt":
        local_mysqld_path = os.path.join(sandbox_dir, "mysqld")
        try:
            _LOGGER.debug("Copying mysqld binary '%s' to '%s'", mysqld_path,
                          sandbox_dir)
            shutil.copy(mysqld_path, local_mysqld_path)
        except (IOError, shutil.Error) as err:
            raise exceptions.GadgetError(
                "Unable to copy mysqld binary '{0}' to '{1}': '{2}'."
                "".format(mysqld_path, sandbox_dir, str(err)))
    else:
        local_mysqld_path = mysqld_path

    # Get the command string
    create_cmd = _CREATE_SANDBOX_CMD.format(
        quote=QUOTE_CHAR, mysqld_path=local_mysqld_path,
        config_file=os.path.normpath(optf_path))

    # If we are running the script as root , the --user=root option is needed
    if os.name == "posix" and getpass.getuser() == "root":
        _LOGGER.warning("Creating a sandbox as root is not recommended.")
        create_cmd = "{0} --user=root".format(create_cmd)

    init_proc = tools.run_subprocess(create_cmd, shell=False)
    init_proc.wait()
    if init_proc.returncode != 0:
        raise exceptions.GadgetError(
            "Error initializing MySQL sandbox '{0}'. Initialize process "
            "failed with return code '{1}'.".format(port,
                                                    init_proc.returncode))

    # Change root password if one was provided
    # start the server
    if password:
        _LOGGER.info("Changing root password")
        if tools.is_listening("localhost", port):
            # there is already something running on the port that the sandbox
            # will use as such we cannot spawn the server to change the root
            # password.
            # lets remove the sandbox dir
            try:
                _LOGGER.debug("removing MySQL sandbox dir '%s'.", sandbox_dir)
                shutil.rmtree(sandbox_dir)
            finally:
                raise exceptions.GadgetError(
                    "Unable to start the MySQL sandbox in order to change the "
                    "root password. Port '{0}' on which the sandbox runs was "
                    "already in use.".format(port))

        start_cmd = _START_SERVER_CMD.format(
            quote=QUOTE_CHAR, mysqld_path=local_mysqld_path,
            config_file=os.path.normpath(optf_path))

        # If we are running the script as root , the --user=root option is
        # needed
        if os.name == "posix" and getpass.getuser() == "root":
            start_cmd = "{0} --user=root".format(start_cmd)

        _LOGGER.debug("Launching mysqld to change the root password")
        server_proc = tools.run_subprocess(start_cmd)
        # wait until server is listening on the given port
        i = 0
        _LOGGER.debug("Waiting for MySQL sandbox to start listening for "
                      "connections on port '%i'", port)
        while i < timeout:
            if not tools.is_listening("localhost", port):
                time.sleep(1)
                i += 1
            else:
                # port is listening, break out of loop
                _LOGGER.debug("MySQL sandbox is listening for connections on "
                              "port '%i'", port)
                break
        else:
            # timeout occurred, send signal to terminate process
            try:
                server_proc.terminate()
            except Exception as err:
                raise exceptions.GadgetError(
                    "Timeout waiting for mysqld process with pid '{0}' used "
                    "to change root password to start and we got error '{1} "
                    "while trying to terminate it. You might need to "
                    "terminate it manually.".format(server_proc.pid, str(err))
                )
            else:
                # server was successfully terminated
                raise exceptions.GadgetError(
                    "Timeout waiting for mysqld process with pid '{0}' used "
                    "to change root password to start.".format(server_proc.pid)
                )

        # server is now listening, connect to it and change root password
        s = server.Server({"conn_info": "root@localhost:{0}".format(port)})
        try:
            s.connect()
        except exceptions.GadgetServerError as err:
            # Check if server process has finished
            start_ret_code = server_proc.poll()
            if start_ret_code is None:
                # server_proc is still running
                raise exceptions.GadgetError(
                    "Cannot change root password, unable to connect to "
                    "sandbox server: {0}".format(str(err)))
            else:
                # server_proc has ended unexpectedly, some error occurred
                raise exceptions.GadgetError(
                    "Cannot change root password. Server stopped unexpectedly "
                    "with return code '{0}'. Check error log file '{1}'."
                    "".format(start_ret_code,
                              os.path.join(datadir, "error.log")))
        # change password of root account
        query = "ALTER USER 'root'@'localhost' IDENTIFIED BY '{0}'"
        s.toggle_binlog(action="disable")
        s.exec_query(query.format(password),
                     query_to_log=query.format("******"))
        s.toggle_binlog(action="enable")
        s.disconnect()
        _LOGGER.info("Password changed.")
        _LOGGER.debug("Root password changed, stopping mysqld.")
        try:
            # terminate server proc
            server_proc.terminate()
        except Exception as err:
            raise exceptions.GadgetError(
                "Unable to terminate the mysqld process with "
                "pid '{0}' that was started to change the root password: "
                "'{1}'. You might need to terminate it manually.".format(
                    server_proc.pid, str(err)))

        server_proc.wait()
        _LOGGER.debug("mysqld stopped.")

    _LOGGER.debug("Creating SSL/RSA files.")
    # Create SSL/RSA Files if they don't exist using the mysql_ssl_rsa_setup.
    if (os.path.isfile(os.path.join(datadir, "ca.pem")) or
            os.path.isfile(os.path.join(datadir, "server-cert.pem")) or
            os.path.isfile(os.path.join(datadir, "server-key.pem"))):
        _LOGGER.debug("SSL/RSA files already exist.")
    else:
        # MySQL servers have the capability of automatically generating
        # missing SSL and RSA files at startup, for MySQL distributions
        # compiled using OpenSSL. For MySQL distributions using YaSSL this can
        # be done manually using the mysql_ssl_rsa_setup utility however it
        # requires the openssl command to be available.
        rsa_ssl_cmd = _CREATE_RSA_SSL_FILES_CMD.format(
            quote=QUOTE_CHAR,
            mysql_ssl_rsa_setup_path=mysql_ssl_rsa_setup_path,
            datadir=datadir)
        create_ssl_rsa_files_proc = tools.run_subprocess(
            rsa_ssl_cmd, shell=False, stderr=subprocess.PIPE)
        _, stderr = create_ssl_rsa_files_proc.communicate()
        # if the return code is not 0, an error occurred. Raise an exception
        # and show it if the ignore_ssl_error flag was not used.
        if create_ssl_rsa_files_proc.returncode and not ignore_ssl_error:
            raise exceptions.GadgetError(
                "Unable to create SSL/RSA files. mysql_ssl_rsa_setup exited "
                "with error code '{0}' and message: '{1}'. You can use the "
                "option to ignore SSL errors to skip the use of SSL.".format(
                    create_ssl_rsa_files_proc.returncode, stderr.strip()))
        elif not create_ssl_rsa_files_proc.returncode:
            # if the process ran without any errors
            _LOGGER.debug("SSL/RSA files created.")

    # create start script
    _LOGGER.debug("Creating start script for sandbox.")
    start_path = _create_start_script("start", sandbox_dir, local_mysqld_path,
                                      optf_path)
    _LOGGER.debug("Start script created.")

    # Create stop script
    _LOGGER.debug("Creating stop script for sandbox.")
    stop_path = _create_stop_script("stop", sandbox_dir, mysqladmin_path,
                                    optf_path)
    _LOGGER.debug("Stop script created.")
    print("You can use '{0}' and '{1}' to start and stop the instance.".format(
        os.path.normpath(start_path), os.path.normpath(stop_path)))


def start_sandbox(**kwargs):
    """Starts a MySQL sandbox.

    Start the server instance of an existing MySQL sandbox.
    Note: the sandbox must be created first, otherwise an error is issued.

    :param kwargs:      Keyword arguments:
                        port: The port where the sandbox will listen for
                               MySQL connections.
                        sandbox_base_dir: base path for the created MySQL
                                          sandbox instances. Default is
                                          DEFAULT_SANDBOX_DIR.
                        mysqld_path: Path to the mysqld executable. By default
                                     it will search the PATH of the system.
                        opt: list of additional values to save under the
                             [mysqld] section of the option file.
                        timeout: timeout in seconds to wait for the sandbox
                                 instance to start listening for connections.
    :type kwargs:       dict

    :raises GadgetError: If the MySQL sandbox to start does not exist, for the
                         given port and sandbox_base_dir.
    """
    # If sandbox dir does not exist (not created) then raise an error.
    if not sandbox_exists(**kwargs):
        raise exceptions.GadgetError(_ERROR_NOT_CREATED)

    # Get mandatory values
    try:
        port = int(kwargs["port"])
    except KeyError:
        raise exceptions.GadgetError("It is mandatory to specify a port.")

    # Get default values for optional variables
    timeout = kwargs.get("timeout", SANDBOX_TIMEOUT)

    # Get list of options to override
    mysqld_opts = kwargs.get("opt", [])
    opt_override_dict = option_list_to_dictionary(mysqld_opts)

    _, sandbox_dir = _get_sandbox_dirs(**kwargs)
    mysqld_path = kwargs.get("mysqld_path", None)

    if os.name == "nt":
        # On non non posix systems if no value is provided for mysqld, by
        # default search the $PATH.
        if not mysqld_path:
            mysqld_path = tools.get_tool_path(None, "mysqld", search_path=True,
                                              required=False)
    else:
        # On posix systems, if no value is provided for mysqld, by default
        # search for the mysqld binary inside the sandbox dir. If not found
        # search the $PATH.
        if not mysqld_path:
            mysqld_path = os.path.join(sandbox_dir, "mysqld")
            if not os.path.isfile(mysqld_path):
                _LOGGER.warning("Could not find a copy of the mysqld "
                                "executable in '%s'. Start operation might "
                                "fail if AppArmor or SELinux are blocking "
                                "the mysqld access to the sandbox directory.",
                                sandbox_dir)
                mysqld_path = tools.get_tool_path(None, "mysqld",
                                                  search_path=True,
                                                  required=False)
    if not mysqld_path:
        raise exceptions.GadgetError(_ERROR_CANNOT_FIND_TOOL.format(
            exec_name="mysqld", path_var_name=PATH_ENV_VAR))

    # Checking if mysqld meets requirements
    if not tools.is_executable(mysqld_path):
        raise exceptions.GadgetError(
            "Provided mysqld '{0}' is not a valid executable."
            "".format(mysqld_path))

    mysqld_ver, version_str = server.get_mysqld_version(mysqld_path)
    if not MIN_MYSQL_VERSION <= mysqld_ver < MAX_MYSQL_VERSION:
        raise exceptions.GadgetError(_ERROR_VERSION_NOT_SUPPORTED.format(
            mysqld_path, version_str,
            '.'.join(str(i)for i in MIN_MYSQL_VERSION),
            '.'.join(str(i) for i in MAX_MYSQL_VERSION)))

    # option_file path
    optf_path = os.path.join(sandbox_dir, "my.cnf")

    # Update opt_override_dict with value for secure_file_priv.
    _set_secure_file_priv(opt_override_dict, sandbox_dir)
    _LOGGER.debug("Option secure_file_priv will be set with value: %s",
                  opt_override_dict['secure_file_priv'])

    # If sandbox already existed but option values were provided manually
    # add them to the option file
    if opt_override_dict:
        _LOGGER.debug("Adding/Overriding option file values.")
        # If port is one of the options to override raise exception
        if "port" in opt_override_dict:
            raise exceptions.GadgetError(_ERROR_OVERRIDE_PORT)
        mysql_opt_parser = MySQLOptionsParser(optf_path)
        for opt, val in opt_override_dict.items():
            mysql_opt_parser.set("mysqld", opt, val)
        mysql_opt_parser.write()

    # Initialize mysql sandbox
    # pylint: disable=E1101
    _LOGGER.step("Initializing MySQL sandbox on '%s'.", sandbox_dir)

    _LOGGER.info("Starting MySQL sandbox on port '%i'", port)
    # since the script starts mysqld server on background there is no simple
    # way to know if it started correctly, we will at least try to make sure
    # the port is not in use.
    if tools.is_listening("localhost", port):
        raise exceptions.GadgetError(
            "Unable to start MySQL sandbox because port '{0}' is already in "
            "use.".format(port))
    # also check if mysqlx_port is in use
    if mysql_opt_parser.has_option("mysqld", "mysqlx_port"):
        # First we check for option without the loose prefix. If it exists
        # it means it was manually overridden by the user and it has precedence
        # over the loose-prefix one.
        mysqlx_port = mysql_opt_parser.get("mysqld", "mysqlx_port")
    elif mysql_opt_parser.has_option("mysqld", "loose_mysqlx_port"):
        mysqlx_port = mysql_opt_parser.get("mysqld", "loose_mysqlx_port")
    else:
        # if no mysqlx_port was specified, then there is no need to do any
        # validation.
        mysqlx_port = None

    if mysqlx_port is not None:
        if tools.is_listening("localhost", int(mysqlx_port)):
            raise exceptions.GadgetError(
                "Unable to start MySQL sandbox because port '{0}' for the X"
                " protocol is already in use.".format(mysqlx_port))

    # Try to create lock file. If we're unable to do it, it means another
    # sandbox process is already running, so we raise an exception.
    flags = os.O_CREAT | os.O_EXCL | os.O_RDONLY
    lock_file_path = os.path.normpath(os.path.join(sandbox_dir,
                                                   _LOCKFILE_NAME))
    try:
        file_handle = os.open(lock_file_path, flags)
        os.close(file_handle)

        start_cmd = _START_SERVER_CMD.format(
            quote=QUOTE_CHAR,
            mysqld_path=mysqld_path,
            config_file=os.path.normpath(optf_path))

        # If we are running the script as root , the --user=root option
        # is needed
        if os.name == "posix" and getpass.getuser() == "root":
            _LOGGER.warning(
                "Starting a sandbox as root is not recommended.")
            start_cmd = "{0} --user=root".format(start_cmd)

        error_log_path = os.path.normpath(
            mysql_opt_parser.get("mysqld", "log_error"))
        if os.path.isfile(error_log_path):
            # Find out last position of error log, before starting the process
            # since the error log persists several sessions.
            error_log_end_pos = os.path.getsize(error_log_path)
        else:
            # if error_log didn't exist, start reading at the beginning of the
            # file
            error_log_end_pos = 0

        server_proc = tools.run_subprocess(start_cmd, shell=False)
        started_at = time.time()
        started_ok = False
        _LOGGER.debug("Waiting for MySQL sandbox to start listening for "
                      "connections on port '%i'", port)

        # Wait for the log file to be created by the server
        # in case it does not exist.
        i = 0
        while i < timeout:
            if not os.path.isfile(error_log_path):
                # Wait for the log file to be created by the server.
                time.sleep(1)
                i += 1
            else:
                # Log file created by the server and available.
                break
        else:
            raise exceptions.GadgetError(
                "Timeout waiting for the MySQL log error file to be "
                "available: '{0}'. Please check configuration for 'log_error' "
                "in '{1}' file and that the log file is accessible."
                "".format(error_log_path, optf_path))

        with open(error_log_path, 'r') as f:
            # jump to current session position
            f.seek(error_log_end_pos)
            # Check that server has started correctly:
            while time.time() - started_at < timeout:
                # save last read position (start of line)
                last_pos = f.tell()
                line = f.readline()
                if not line:
                    if not started_ok:
                        # if nothing to read, wait a bit
                        time.sleep(1)
                        continue
                    else:
                        # Started ok and nothing else to read, exit loop.
                        break
                if "\n" not in line:
                    # if we didn't read a whole line, go back to saved position
                    f.seek(last_pos)
                    continue
                if not started_ok:
                    # if we didn't find the ready_message yet, keep looking
                    # for it.
                    for server_ready_msg in _SERVER_READY_LOG_MESSAGES:
                        if server_ready_msg in line:
                            _LOGGER.debug(
                                "MySQL sandbox is listening for "
                                "connections on port '%i'", port)
                            started_ok = True
                            break
                if "[ERROR] Aborting\n" in line:
                    # critical error, server won't start but will shutdown
                    # on its own.
                    raise exceptions.GadgetError(
                        "Unable to start server on port '{0}'. For more "
                        "information, check error log '{1}'".format(
                            port, error_log_path))

                if "[ERROR]" in line:
                    _LOGGER.warning(
                        "Error found during server startup: "
                        "'%s'", line.strip())

            if not started_ok:
                # timeout occurred, send signal to terminate process
                try:
                    server_proc.terminate()
                except Exception as err:
                    raise exceptions.GadgetError(
                        "Timeout waiting for sandbox mysqld process with "
                        "pid '{0}' to start and we got error '{1}' while "
                        "trying to terminate it. You might need to "
                        "terminate it manually."
                        "".format(server_proc.pid, str(err)))
                else:
                    # server was successfully terminated
                    raise exceptions.GadgetError(
                        "Timeout waiting for sandbox mysqld process with "
                        "pid '{0}' to start. For more information, check "
                        "error log '{1}'.".format(server_proc.pid,
                                                  error_log_path))

        _LOGGER.info("MySQL sandbox running on port '%i' with process ID: "
                     "'%i'", port, server_proc.pid)
    except OSError as err:
        if err.errno == errno.EEXIST:  # Failed as the file already exists.
            raise exceptions.GadgetError(
                "Unable to lock sandbox directory. Another sandbox "
                "must be using it.")
        else:  # Something unexpected went wrong so re-raise the exception.
            raise exceptions.GadgetError("Unexpected error: {0}".format(
                str(err)))
    finally:
        try:
            _LOGGER.debug("Removing lock file '%s'", lock_file_path)
            os.remove(lock_file_path)
            _LOGGER.debug("Lock file removed")
        except OSError as err:
            if err.errno == errno.ENOENT:
                # file does not exist, ignore error
                pass
            else:
                raise exceptions.GadgetError(
                    "Unable to remove lock file '{0}': {1}".format(
                        lock_file_path, str(err)))


def stop_sandbox(**kwargs):
    """Stop an existing MySQL sandbox.
    :param kwargs:      Keyword arguments:
                        port: The port where the sandbox is listening for
                               MySQL connections.
                        sandbox_base_dir: base path for the created MySQL
                                          sandbox instances. Default is
                                          DEFAULT_SANDBOX_DIR.
    :type kwargs:       dict
    """
    # get mandatory values
    try:
        port = int(kwargs["port"])
    except KeyError:
        raise exceptions.GadgetError("It is mandatory to specify a port.")

    password = kwargs.get("passwd")

    # Get default values for optional variables
    timeout = kwargs.get("timeout", SANDBOX_TIMEOUT)
    _, sandbox_dir = _get_sandbox_dirs(**kwargs)
    # pid file path
    pidf_path = os.path.join(sandbox_dir, "{0}.pid".format(port))

    # Check if the pid file exists and if the port on which it is running is
    # still listening, meaning the sandbox is running.
    # pylint: disable=E1101
    _LOGGER.step("Stopping MySQL sandbox on '%s'.", sandbox_dir)
    # if a pid file still exists
    if os.path.exists(pidf_path):
        _LOGGER.debug("Found pid file '%s'", pidf_path)
        # and a server listening on the port we specified
        if tools.is_listening("localhost", port):
            _LOGGER.debug("Found server listening on port '%i'", port)
            with open(pidf_path) as f:
                pid = int(f.readline().strip())
                _LOGGER.debug("Got pid '%i' from pid file '%s'", pid,
                              pidf_path)
            _LOGGER.debug("Executing SHUTDOWN SQL command on server with "
                          "PID '%i'", pid)
            # Send shutdown signal
            conn_dict = {"user": "root",
                         "host": "localhost",
                         "port": port,
                         "passwd": password}
            s = server.Server({"conn_info": conn_dict})
            try:
                s.connect()
            except exceptions.GadgetServerError as err:
                raise exceptions.GadgetError(
                    "Unable to connect to MySQL sandbox {0} to send the "
                    "SHUTDOWN request: '{1}'".format(str(s), str(err)))
            try:
                s.exec_query("SHUTDOWN")
            except exceptions.GadgetQueryError:
                # ignore query timeout or connection lost errors.
                pass
            # Wait for server to stop (listening on port).
            i = 0
            _LOGGER.debug("Waiting for MySQL sandbox on port '%i' to stop.",
                          port)
            while i < timeout:
                if tools.is_listening("localhost", port):
                    time.sleep(1)
                    i += 1
                else:
                    # port is listening, break out of loop
                    _LOGGER.debug(
                        "MySQL sandbox on port '%i' stopped.", port)
                    break
            else:
                # Timeout occurred, issue an error
                raise exceptions.GadgetError(
                    "Timeout waiting for sandbox mysqld process with pid "
                    "'{0}' to stop. You might need to terminate it manually "
                    "or use the '{1} {2}' command.".format(pid, SANDBOX,
                                                           SANDBOX_KILL))
            # Server was stopped
            _LOGGER.info("MySQL sandbox was stopped on port '%i' with process "
                         "ID: '%i'.", port, pid)

            # remove pid file
            try:
                _LOGGER.debug("Removing pid file '%s'", pidf_path)
                os.unlink(pidf_path)
            except OSError as err:
                _LOGGER.warning("Unable to remove pid file: '%s'", str(err))
        else:
            # there is a process listening on the specified port, but there is
            # no pid file so emmit a warning and do nothing
            _LOGGER.warning("There is no MySQL sandbox listening on port %i, "
                            "but a pid file was still found. Removing it.")
            try:
                os.unlink(pidf_path)
            except OSError as err:
                _LOGGER.warning("Unable to remove pid file: '%s'", str(err))
    else:
        # no pid file was found
        raise exceptions.GadgetError("Unable to find pid file. Stop "
                                     "operation will not proceed.")


def kill_sandbox(**kwargs):
    """Stop an existing MySQL sandbox.
    :param kwargs:      Keyword arguments:
                        port: The port where the sandbox is listening for
                               MySQL connections.
                        sandbox_base_dir: base path for the created MySQL
                                          sandbox instances. Default is
                                          DEFAULT_SANDBOX_DIR.
    :type kwargs:       dict
    """
    # get mandatory values
    try:
        port = int(kwargs["port"])
    except KeyError:
        raise exceptions.GadgetError("It is mandatory to specify a port.")

    # Get default values for optional variables
    _, sandbox_dir = _get_sandbox_dirs(**kwargs)
    # pif file path
    pidf_path = os.path.join(sandbox_dir, "{0}.pid".format(port))

    # Check if the pid file exists and if the port on which it is running is
    # still listening, meaning the sandbox is running.
    # pylint: disable=E1101
    _LOGGER.step("Killing MySQL sandbox on '%s'.", sandbox_dir)
    # if a pid file still exists
    if os.path.exists(pidf_path):
        _LOGGER.debug("Found pid file '%s'", pidf_path)
        # and a server listening on the port we specified
        if tools.is_listening("localhost", port):
            _LOGGER.debug("Found server listening on port '%i'", port)
            with open(pidf_path) as f:
                pid = int(f.readline().strip())
                _LOGGER.debug("Got pid '%i' from pid file '%s'", pid,
                              pidf_path)
            _LOGGER.debug("Sending kill signal to process '%i'", pid)
            # kill process
            tools.stop_process_with_pid(pid, force=True)
            # remove pid file
            try:
                _LOGGER.debug("Removing pid file '%s'", pidf_path)
                os.unlink(pidf_path)
            except OSError as err:
                _LOGGER.warning("Unable to remove pid file: '%s'", str(err))
        else:
            # there is a process listening on the specified port, but there is
            # no pid file so emmit a warning and do nothing
            _LOGGER.warning("There is no MySQL sandbox listening on port %i, "
                            "but a pid file was still found. Removing it.")
            try:
                os.unlink(pidf_path)
            except OSError as err:
                _LOGGER.warning("Unable to remove pid file: '%s'", str(err))
    else:
        # no pid file was found
        raise exceptions.GadgetError("Unable to find pid file. Kill "
                                     "operation will not proceed.")


def delete_sandbox(**kwargs):
    """Deletes the folder of a MySQL sandbox.
    :param kwargs:      Keyword arguments:
                        port: The port where the sandbox is listening for
                               MySQL connections.
                        sandbox_base_dir: base path for the created MySQL
                                          sandbox instances. Default is
                                          DEFAULT_SANDBOX_DIR.
    :type kwargs:       dict
    """

    # Callback function to ignore the file not found errors
    # On when rmtree is called
    def on_delete_sandbox_error(func, path, exc_info):
        # It will ignore file not found errors on delete operations
        type_, value, traceback = exc_info

        # if it is not a non existing file/folder (errno= 2) re raise exception
        if value.errno != 2:
            if value is not None:
                exc = type_(value)
            else:
                exc = type_
            if sys.version_info[0] == 3:
                if exc.__traceback__ is not traceback:
                    raise exc.with_traceback(traceback)
            raise exc
        else:
            # Log ignored exception raised when attempting to delete
            # non existing file/folder
            _LOGGER.debug("Ignored exception raised when trying to "
                          "delete non-existing file/folder: '%s'", path)

    # get mandatory values
    try:
        port = int(kwargs["port"])
    except KeyError:
        raise exceptions.GadgetError("It is mandatory to specify a port.")

    # Get default values for optional variables
    _, sandbox_dir = _get_sandbox_dirs(**kwargs)
    # pif file path
    pidf_path = os.path.join(sandbox_dir, "{0}.pid".format(port))

    # Check if the pid file exists, meaning the sandbox is running and if the
    # port on which it is running is still listening.
    # pylint: disable=E1101
    _LOGGER.step("Deleting MySQL sandbox on '%s'.", sandbox_dir)
    # if a pid file still exists
    if os.path.exists(pidf_path):
        _LOGGER.debug("Found pid file '%s'", pidf_path)
        # and a server listening on the port we specified, we cannot destroy it
        if tools.is_listening("localhost", port):
            _LOGGER.debug("Found server listening on port '%i'", port)
            raise exceptions.GadgetError(
                "Unable to delete sandbox folder: the MySQL sandbox instance "
                "on port '{0}' is running, please stop it to be able to "
                "delete it.".format(port))
        else:
            _LOGGER.warning("A pid file was found but there is no MySQL "
                            "sandbox listening on port '%i'. Sandbox will "
                            "still be deleted.", port)
            # When deleting the sandbox, some files might still be in use as
            # the server might be shutting down. To account for this, we try
            # several times to delete the sandbox dir with increasing timeout
            # times. If we still fails, an exception is thrown.
            err = None
            for i in range(1, _MAX_RMTREE_RETRIES + 1):
                try:
                    shutil.rmtree(sandbox_dir, onerror=on_delete_sandbox_error)
                    break
                except OSError as err:
                    _LOGGER.warning("Unable to delete MySQL sandbox folder "
                                    "'%s'. Retrying after '%d' seconds. '%d' "
                                    "retries left.", sandbox_dir, i,
                                    _MAX_RMTREE_RETRIES - i)
                    time.sleep(i)
            else:
                # Failed to successfully remove the sandbox folder.
                raise exceptions.GadgetError(
                    "Unable to delete MySQL sandbox folder '{0}': '{1}'"
                    "".format(sandbox_dir, str(err)))

    else:
        # no pid file was found so we can safely delete
        try:
            shutil.rmtree(sandbox_dir, onerror=on_delete_sandbox_error)
        except Exception as err:
            raise exceptions.GadgetError(
                "Unable to delete MySQL sandbox folder '{0}': '{1}'"
                "".format(sandbox_dir, str(err)))