
DROP SCHEMA IF EXISTS all_features;
CREATE SCHEMA all_features;
USE all_features;


-- Users

/* TODO 
CREATE USER `new
line`@localhost;
CREATE USER `'foo'@bar'`@localhost;
CREATE USER `foo``bar`@localhost;
CREATE USER `foo``bar`@'''foo.com';
CREATE USER ''''@'''';
CREATE USER ''@localhost;
*/

-- Tables
/* TODO
CREATE TABLE `new
line` (`a
column`  INT PRIMARY KEY);

CREATE TABLE `foo``bar(` (
    `col``umn` INT PRIMARY KEY
);

CREATE TABLE ```` (
    ```` INT PRIMARY KEY
);

CREATE TABLE `'"` (
    `'"` INT PRIMARY KEY
);

CREATE TABLE table1 (
    a INT,
    b INT,
    PRIMARY KEY (a,b)
);
INSERT INTO table1 VALUES (1,1), (1,2), (2,1), (3,1), (3,2), (3,3), (2,2), (2,3);

CREATE TABLE table2 (
    a VARCHAR(10),
    b VARCHAR(10),
    PRIMARY KEY (a,b)
);
INSERT INTO table2 VALUES ('one','one'), ('one','two'), ('two','one'), ('three','one'), ('three','two'), ('three','three'), ('two','two'), ('two','three');
*/
-- Generated Columns

CREATE TABLE gctable1 (
    a INT PRIMARY KEY,
    b INT GENERATED ALWAYS AS (sqrt(a)) VIRTUAL
);

-- Constraints

-- Foreign Keys

-- Attributes (auto_increment)

-- Partitions

-- Triggers

/* TODO
CREATE TRIGGER `new
line` DO SELECT 1;

CREATE TRIGGER `foo``bar(` DO SELECT 1;

CREATE TRIGGER ```` DO SELECT 1;

CREATE TRIGGER `'"` DO SELECT 1;
*/

-- Views

/* TODO
CREATE VIEW `new
line` AS SELECT 1;

CREATE VIEW `foo``bar(` AS SELECT 1;

CREATE VIEW ```` AS SELECT 1;

CREATE VIEW `'"` AS SELECT 1;
*/

-- Procedures

/* TODO
CREATE PROCEDURE `new
line`() BEGIN END;

CREATE PROCEDURE `foo``bar(`() BEGIN END;

CREATE PROCEDURE ````() BEGIN END;

CREATE PROCEDURE `'"`() BEGIN END;
*/

-- Functions

/* TODO
CREATE FUNCTION `new
line`() RETURNS INT RETURN 0;

CREATE FUNCTION `foo``bar(`() RETURNS INT RETURN 0;

CREATE FUNCTION ````() RETURNS INT RETURN 0;

CREATE FUNCTION `'"`() RETURNS INT RETURN 0;
*/

-- Events

/* TODO
CREATE EVENT `new
line`() BEGIN END;

CREATE EVENT `foo``bar(`() BEGIN END;

CREATE EVENT ````() BEGIN END;

CREATE EVENT `'"`() BEGIN END;
*/

-- Charsets

CREATE TABLE latin1_charset (
    id int primary key auto_increment,
    latin varchar(200)
) CHARACTER SET latin1;

INSERT INTO latin1_charset VALUES (DEFAULT, unhex('4a61636172e9'));
INSERT INTO latin1_charset VALUES (DEFAULT, unhex('44656c66ed6e'));
INSERT INTO latin1_charset VALUES (DEFAULT, 'Lagarto');
INSERT INTO latin1_charset VALUES (DEFAULT, unhex('4d61e7e3'));

CREATE TABLE sjis_charset (
    id int primary key auto_increment,
    japanese varchar(200) 
) CHARACTER SET sjis;

INSERT INTO sjis_charset VALUES (DEFAULT, unhex('82ed82c9'));
INSERT INTO sjis_charset VALUES (DEFAULT, unhex('8343838b834a'));
INSERT INTO sjis_charset VALUES (DEFAULT, unhex('e592e58e'));
INSERT INTO sjis_charset VALUES (DEFAULT, unhex('838a83938353'));

CREATE TABLE unicode_charset (
    id int primary key auto_increment,
    anything varchar(200)
) CHARACTER SET utf8mb4;

INSERT INTO unicode_charset VALUES (DEFAULT, _utf8mb4'🐊');
INSERT INTO unicode_charset VALUES (DEFAULT, _utf8mb4'🐬');
INSERT INTO unicode_charset VALUES (DEFAULT, _utf8mb4'🦎');
INSERT INTO unicode_charset VALUES (DEFAULT, _utf8mb4'🍎');


CREATE TABLE mixed_charset (
    id int primary key auto_increment,
    latin varchar(200) CHARACTER SET latin1,
    japanese varchar(200) CHARACTER SET sjis,
    anything varchar(200) CHARACTER SET utf8mb4,
    picture blob
);

INSERT INTO mixed_charset VALUES (DEFAULT, unhex('4a61636172e9'), unhex('82ed82c9'), _utf8mb4'🐊', unhex('7397553f03b849167ec78ab87eed8063'));
INSERT INTO mixed_charset VALUES (DEFAULT, unhex('44656c66ed6e'), unhex('8343838b834a'), _utf8mb4'🐬', unhex('36cdf8b887a5cffc78dcd5c08991b993'));
INSERT INTO mixed_charset VALUES (DEFAULT, 'Lagarto', unhex('e592e58e'), _utf8mb4'🦎', unhex('5046a43fd3f8184be864359e3d5c9bda'));
INSERT INTO mixed_charset VALUES (DEFAULT, unhex('4d61e7e3'), unhex('838a83938353'), _utf8mb4'🍎', unhex('1f3870be274f6c49b3e31a0c6728957f'));
