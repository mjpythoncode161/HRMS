"""
Management command: import_mysql_dump
--------------------------------------
Reads u673831287_hrms_final.sql (MySQL/MariaDB dump), converts it to
SQLite-compatible SQL, creates the unmanaged custom tables, inserts all data,
and finally creates Django auth.User accounts so employees can log in.

Usage:
    python manage.py import_mysql_dump
"""

import os
import re
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


# ---------------------------------------------------------------------------
# MySQL → SQLite type mapping
# ---------------------------------------------------------------------------
TYPE_MAP = [
    (re.compile(r"\btinyint\s*\(\s*\d+\s*\)", re.I), "INTEGER"),
    (re.compile(r"\bint\s*\(\s*\d+\s*\)", re.I), "INTEGER"),
    (re.compile(r"\bbigint\s*\(\s*\d+\s*\)", re.I), "INTEGER"),
    (re.compile(r"\bsmallint\s*\(\s*\d+\s*\)", re.I), "INTEGER"),
    (re.compile(r"\bmediumint\s*\(\s*\d+\s*\)", re.I), "INTEGER"),
    (re.compile(r"\bvarchar\s*\(\s*\d+\s*\)", re.I), "TEXT"),
    (re.compile(r"\bchar\s*\(\s*\d+\s*\)", re.I), "TEXT"),
    (re.compile(r"\bdecimal\s*\(\s*\d+\s*,\s*\d+\s*\)", re.I), "REAL"),
    (re.compile(r"\bdouble\s*(?:\(\s*\d+\s*,\s*\d+\s*\))?", re.I), "REAL"),
    (re.compile(r"\bfloat\s*(?:\(\s*\d+\s*,\s*\d+\s*\))?", re.I), "REAL"),
    (re.compile(r"\btimestamp", re.I), "TEXT"),
    (re.compile(r"\bdatetime", re.I), "TEXT"),
    (re.compile(r"\bdate\b", re.I), "TEXT"),
    (re.compile(r"\btime\b", re.I), "TEXT"),
    (re.compile(r"\bmediumtext\b", re.I), "TEXT"),
    (re.compile(r"\blongtext\b", re.I), "TEXT"),
    (re.compile(r"\btext\b", re.I), "TEXT"),
    (re.compile(r"\benum\s*\([^)]+\)", re.I), "TEXT"),
    (re.compile(r"\bset\s*\([^)]+\)", re.I), "TEXT"),
]


def convert_type(col_def):
    for pattern, replacement in TYPE_MAP:
        col_def = pattern.sub(replacement, col_def)
    return col_def


def convert_create_table(statement, primary_keys):
    """Convert a MySQL CREATE TABLE statement to SQLite-compatible SQL."""
    # Extract table name
    m = re.match(r"CREATE\s+TABLE\s+`(\w+)`\s*\(", statement, re.I | re.S)
    if not m:
        return None
    table_name = m.group(1)
    pk_col = primary_keys.get(table_name, "id")

    # Get body between outer ( )
    # Find the matching closing paren
    paren_start = statement.index("(")
    depth = 0
    body_end = paren_start
    for i, ch in enumerate(statement[paren_start:], paren_start):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                body_end = i
                break

    body = statement[paren_start + 1 : body_end]

    # Split body into lines, filter out KEY/INDEX declarations
    lines = body.split("\n")
    new_lines = []
    for line in lines:
        stripped = line.strip().rstrip(",")
        # Skip MySQL-specific index lines
        if re.match(r"(?:UNIQUE\s+)?KEY\b", stripped, re.I):
            continue
        if re.match(r"(?:PRIMARY|UNIQUE|FULLTEXT|SPATIAL)\s+KEY\b", stripped, re.I):
            continue
        if re.match(r"INDEX\b", stripped, re.I):
            continue
        if not stripped:
            continue

        # Remove COMMENT '...'
        stripped = re.sub(r"\s+COMMENT\s+'[^']*'", "", stripped, flags=re.I)

        # This is a column definition line
        # Check if it's the primary key column → make it INTEGER PRIMARY KEY AUTOINCREMENT
        col_name_m = re.match(r"`(\w+)`", stripped)
        if col_name_m:
            col_name = col_name_m.group(1)
            if col_name == pk_col:
                stripped = f"`{col_name}` INTEGER PRIMARY KEY AUTOINCREMENT"
            else:
                # Convert types
                stripped = convert_type(stripped)
                # Remove unsigned
                stripped = re.sub(r"\bUNSIGNED\b", "", stripped, flags=re.I)
                # Remove 'current_timestamp()' default → CURRENT_TIMESTAMP
                stripped = re.sub(
                    r"current_timestamp\(\)",
                    "CURRENT_TIMESTAMP",
                    stripped,
                    flags=re.I,
                )

        new_lines.append("  " + stripped)

    body_sql = ",\n".join(new_lines)
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n{body_sql}\n);'


def clean_insert(statement):
    """
    Clean a MySQL INSERT statement so it works in SQLite:
    - Use INSERT OR REPLACE to make inserts idempotent
    - Fix '0000-00-00' invalid dates → '1970-01-01' (placeholder, avoids NOT NULL failures)
    - Fix '0000-00-00 00:00:00' → NULL
    """
    # Make idempotent: replace INSERT INTO → INSERT OR REPLACE INTO
    statement = re.sub(
        r"\bINSERT\s+INTO\b", "INSERT OR REPLACE INTO", statement, flags=re.I
    )
    statement = re.sub(r"'0000-00-00 00:00:00'", "NULL", statement)
    # Replace invalid zero-date with a recognisable placeholder date
    statement = re.sub(r"'0000-00-00'", "'1970-01-01'", statement)
    return statement


def parse_sql_dump(sql_content):
    """
    Parse the MySQL dump into:
      - primary_keys: { table_name: pk_column }
      - create_stmts: [ raw CREATE TABLE statement, ... ]
      - insert_stmts: [ raw INSERT statement, ... ]
      - unique_keys:  { table_name: [col, col, ...] }
    """
    primary_keys = {}
    unique_keys = {}
    create_stmts = []
    insert_stmts = []

    # ---- Pass 1: collect primary keys and unique keys from ALTER TABLE ----
    # Matches multi-line ALTER TABLE block ending with ;
    for m in re.finditer(r"ALTER\s+TABLE\s+`(\w+)`(.*?);", sql_content, re.I | re.S):
        table_name = m.group(1)
        body = m.group(2)
        # Primary key
        pk_m = re.search(r"ADD\s+PRIMARY\s+KEY\s*\(`(\w+)`\)", body, re.I)
        if pk_m:
            primary_keys[table_name] = pk_m.group(1)
        # Unique keys
        for uk_m in re.finditer(r"ADD\s+UNIQUE\s+KEY\s+\w+\s*\(`(\w+)`\)", body, re.I):
            unique_keys.setdefault(table_name, []).append(uk_m.group(1))

    # ---- Pass 2: extract CREATE TABLE and INSERT statements ----
    # Remove MySQL header directives and comments
    lines = sql_content.splitlines()
    clean_lines = []
    for line in lines:
        # Skip MySQL-specific directives
        if re.match(
            r"\s*(SET\s+(SQL_MODE|time_zone|NAMES)|START\s+TRANSACTION|COMMIT|LOCK\s+TABLES|UNLOCK\s+TABLES)",
            line,
            re.I,
        ):
            continue
        if re.match(r"\s*/\*!", line):
            continue
        clean_lines.append(line)

    cleaned = "\n".join(clean_lines)

    # Extract all statements (split by ;)
    # Use a simple state machine to handle ; inside strings
    stmts = []
    current = []
    in_string = False
    string_char = None
    i = 0
    while i < len(cleaned):
        ch = cleaned[i]
        if in_string:
            current.append(ch)
            if ch == "\\" and i + 1 < len(cleaned):
                current.append(cleaned[i + 1])
                i += 2
                continue
            elif ch == string_char:
                in_string = False
        else:
            if ch in ("'", '"'):
                in_string = True
                string_char = ch
                current.append(ch)
            elif ch == "-" and i + 1 < len(cleaned) and cleaned[i + 1] == "-":
                # Line comment – skip to end of line
                while i < len(cleaned) and cleaned[i] != "\n":
                    i += 1
                continue
            elif ch == ";":
                stmt = "".join(current).strip()
                if stmt:
                    stmts.append(stmt)
                current = []
                i += 1
                continue
            else:
                current.append(ch)
        i += 1
    # Last statement without ;
    stmt = "".join(current).strip()
    if stmt:
        stmts.append(stmt)

    for stmt in stmts:
        stmt_stripped = stmt.strip()
        if re.match(r"CREATE\s+TABLE", stmt_stripped, re.I):
            create_stmts.append(stmt_stripped)
        elif re.match(r"INSERT\s+INTO", stmt_stripped, re.I):
            insert_stmts.append(stmt_stripped)

    return primary_keys, unique_keys, create_stmts, insert_stmts


class Command(BaseCommand):
    help = (
        "Import data from the MySQL dump (u673831287_hrms_final.sql) into SQLite3. "
        "Run this once after switching the database backend to SQLite3."
    )

    def handle(self, *args, **options):
        sql_file = os.path.join(settings.BASE_DIR, "u673831287_hrms_final.sql")
        if not os.path.exists(sql_file):
            self.stderr.write(self.style.ERROR(f"SQL dump not found: {sql_file}"))
            return

        db_path = settings.DATABASES["default"]["NAME"]
        self.stdout.write(f"Reading MySQL dump: {sql_file}")
        self.stdout.write(f"Target SQLite3 database: {db_path}")

        with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
            sql_content = f.read()

        primary_keys, unique_keys, create_stmts, insert_stmts = parse_sql_dump(
            sql_content
        )
        self.stdout.write(
            f"Parsed: {len(create_stmts)} CREATE TABLE, {len(insert_stmts)} INSERT"
        )

        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = OFF")
        cur = conn.cursor()

        errors = []

        # ---- Create tables ----
        for raw_stmt in create_stmts:
            converted = convert_create_table(raw_stmt, primary_keys)
            if not converted:
                continue
            try:
                cur.execute(converted)
                # Extract table name for messaging
                m = re.search(r'CREATE TABLE IF NOT EXISTS "(\w+)"', converted)
                tbl = m.group(1) if m else "?"
                self.stdout.write(f"  CREATE TABLE {tbl} ... OK")
            except Exception as e:
                errors.append(f"CREATE: {e}\n{converted[:200]}")
                self.stderr.write(self.style.WARNING(f"  CREATE failed: {e}"))

        # ---- Create UNIQUE indexes from ALTER TABLE UNIQUE KEY ----
        for table, cols in unique_keys.items():
            for col in cols:
                idx_sql = (
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_{col}" '
                    f'ON "{table}" ("{col}")'
                )
                try:
                    cur.execute(idx_sql)
                except Exception as e:
                    # Might already exist or col may not exist — not critical
                    self.stderr.write(self.style.WARNING(f"  INDEX {table}.{col}: {e}"))

        # ---- Insert data ----
        for raw_stmt in insert_stmts:
            stmt = clean_insert(raw_stmt)
            try:
                cur.execute(stmt)
            except Exception as e:
                errors.append(f"INSERT: {e}\n{stmt[:200]}")
                self.stderr.write(self.style.WARNING(f"  INSERT failed: {e}"))

        conn.commit()
        conn.close()

        # ---- Create Django auth users from the `users` table ----
        self.stdout.write(
            "\nCreating Django auth users from imported `users` table ..."
        )
        self._create_auth_users()

        if errors:
            self.stderr.write(
                self.style.WARNING(f"\n{len(errors)} error(s) occurred (see above).")
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll data imported successfully!"))

        self.stdout.write(
            self.style.SUCCESS(
                "\nDone. You can now start the server with: python manage.py runserver\n"
                "Login with the phone number as username.\n"
                "Default password for all migrated users = their phone number.\n"
                "Change passwords via: python manage.py changepassword <phone>"
            )
        )

    def _create_auth_users(self):
        """
        Read the newly imported `users` table from SQLite and create
        corresponding Django auth.User accounts (username = phone number).
        """
        db_path = settings.DATABASES["default"]["NAME"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, full_name, email, type, contact FROM users")
            users_rows = cur.fetchall()
        except Exception as e:
            self.stderr.write(self.style.WARNING(f"Could not read users table: {e}"))
            conn.close()
            return
        conn.close()

        # Ensure groups exist
        for grp in ["admin", "employee", "customer"]:
            Group.objects.get_or_create(name=grp)

        for row in users_rows:
            contact = (row["contact"] or "").strip()
            if not contact:
                continue
            full_name = (row["full_name"] or "").strip()
            email = (row["email"] or "").strip()
            user_type = row["type"]  # 1=Admin, 2=Customer/Employee

            first_name = full_name.split()[0] if full_name else ""
            last_name = (
                " ".join(full_name.split()[1:]) if len(full_name.split()) > 1 else ""
            )

            if User.objects.filter(username=contact).exists():
                self.stdout.write(f"  auth user {contact} already exists — skipped")
                continue

            is_super = user_type == 1
            django_user = User.objects.create_user(
                username=contact,
                email=email,
                password=contact,  # default password = phone number
                first_name=first_name,
                last_name=last_name,
                is_staff=is_super,
                is_superuser=is_super,
            )
            # Assign group
            if is_super:
                group, _ = Group.objects.get_or_create(name="admin")
            elif user_type == 2:
                group, _ = Group.objects.get_or_create(name="employee")
            else:
                group, _ = Group.objects.get_or_create(name="customer")
            django_user.groups.add(group)
            self.stdout.write(
                f"  Created auth user: {contact} ({full_name}) "
                f"[{'superuser' if is_super else 'user'}]"
            )
