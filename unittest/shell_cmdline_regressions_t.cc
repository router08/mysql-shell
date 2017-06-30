/* Copyright (c) 2017, Oracle and/or its affiliates. All rights reserved.

 This program is free software; you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation; version 2 of the License.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA */

#include <string>
#include "unittest/test_utils/command_line_test.h"
#include "utils/utils_file.h"

namespace tests {

TEST_F(Command_line_test, bug24912358) {

  // Tests with X Protocol Session
  {
    std::string uri = "--uri=" + _uri;
    execute({_mysqlsh, uri.c_str(), "--sql", "-e", "select -127 << 1.1", NULL});
    MY_EXPECT_MULTILINE_OUTPUT("select -127 << 1.1", multiline({
      "+----------------------+",
      "| -127 << 1.1          |",
      "+----------------------+",
      "| 18446744073709551362 |",
      "+----------------------+"
    }), _output);
  }

  {
    std::string uri = "--uri=" + _uri;
    execute({_mysqlsh, uri.c_str(), "--sql", "-e", "select -127 << -1.1", NULL});
    MY_EXPECT_MULTILINE_OUTPUT("select -127 << 1.1", multiline({
      "+--------------+",
      "| -127 << -1.1 |",
      "+--------------+",
      "|            0 |",
      "+--------------+"}), _output);
  }

  // Tests with Classic Session
  {
    std::string uri = "--uri=" + _mysql_uri;
    execute({_mysqlsh, uri.c_str(), "--sql", "-e", "select -127 << 1.1", NULL});
    MY_EXPECT_MULTILINE_OUTPUT("select -127 << 1.1", multiline({
      "+----------------------+",
      "| -127 << 1.1          |",
      "+----------------------+",
      "| 18446744073709551362 |",
      "+----------------------+"}), _output);
  }

  {
    std::string uri = "--uri=" + _mysql_uri;
    execute({_mysqlsh, uri.c_str(), "--sql", "-e", "select -127 << -1.1", NULL});
    MY_EXPECT_MULTILINE_OUTPUT("select -127 << 1.1", multiline({
      "+--------------+",
      "| -127 << -1.1 |",
      "+--------------+",
      "|            0 |",
      "+--------------+"}), _output);
  }
};

TEST_F(Command_line_test, bug23508428) {
  // Test if the xplugin is installed using enableXProtocol in the --dba option
  std::string uri = "--uri=" + _mysql_uri;

  execute({ _mysqlsh, uri.c_str(), "--sqlc", "-e", "uninstall plugin mysqlx;", NULL });

  execute({_mysqlsh, uri.c_str(), "--classic", "--dba","enableXProtocol", NULL});
  MY_EXPECT_CMD_OUTPUT_CONTAINS("enableXProtocol: Installing plugin mysqlx...");
  MY_EXPECT_CMD_OUTPUT_CONTAINS("enableXProtocol: done");

  execute({ _mysqlsh, uri.c_str(), "--interactive=full", "-e", "session.runSql('SELECT COUNT(*) FROM information_schema.plugins WHERE PLUGIN_NAME=\"mysqlx\"').fetchOne()", NULL});
  MY_EXPECT_CMD_OUTPUT_CONTAINS("[");
  MY_EXPECT_CMD_OUTPUT_CONTAINS("    1");
  MY_EXPECT_CMD_OUTPUT_CONTAINS("]");

  execute({_mysqlsh, uri.c_str(), "--classic", "--dba","enableXProtocol", NULL});
  MY_EXPECT_CMD_OUTPUT_CONTAINS("enableXProtocol: X Protocol plugin is already enabled and listening for connections on port " + _port);
}

}
