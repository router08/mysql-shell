/*
 * Copyright (c) 2017, Oracle and/or its affiliates. All rights reserved.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; version 2 of the
 * License.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
 * 02110-1301  USA
 */

#include <stdexcept>
#include "mysqlshdk/libs/db/column.h"
#include "mysqlshdk/libs/db/charset.h"

namespace mysqlshdk {
namespace db {

std::string to_string(Type type) {
  switch (type) {
    case Type::Null:
      return "Null";
    case Type::String:
      return "String";
    case Type::Integer:
      return "Integer";
    case Type::UInteger:
      return "UInteger";
    case Type::Float:
      return "Float";
    case Type::Double:
      return "Double";
    case Type::Decimal:
      return "Decimal";
    case Type::Bytes:
      return "Bytes";
    case Type::Geometry:
      return "Geometry";
    case Type::Json:
      return "Json";
    case Type::DateTime:
      return "DateTime";
    case Type::Date:
      return "Date";
    case Type::Time:
      return "Time";
    case Type::Bit:
      return "Bit";
    case Type::Enum:
      return "Enum";
    case Type::Set:
      return "Set";
  }
  throw std::logic_error("Unknown type");
}

Column::Column(const std::string& schema, const std::string& table_name,
               const std::string& table_label, const std::string& column_name,
               const std::string& column_label, uint32_t length, int fractional,
               Type type, uint32_t collation_id, bool unsigned_, bool zerofill,
               bool binary)
    : _schema(schema),
      _table_name(table_name),
      _table_label(table_label),
      _column_name(column_name),
      _column_label(column_label),
      _collation_id(collation_id),
      _length(length),
      _fractional(fractional),
      _type(type),
      _unsigned(unsigned_),
      _zerofill(zerofill),
      _binary(binary) {
}

std::string Column::get_collation_name() const {
  return charset::collation_name_from_collation_id(_collation_id);
}

std::string Column::get_charset_name() const {
  return charset::charset_name_from_collation_id(_collation_id);
}

}  // namespace db
}  // namespace mysqlshdk
