"""
Repository: turns application actions into parameterized SQL.

Example flow (see README "From a click to the database"):
  user submits "New passenger" form
    -> app.py  create(entity='passengers')
    -> entities.parse_form()   validates and converts the input
    -> repository.insert()     builds  INSERT INTO passenger (...) VALUES (%s, ...)
    -> db.execute()            PyMySQL sends SQL + values separately to MySQL
"""
from db import execute, query, query_one, scalar, transaction

PAGE_SIZE = 50


def where_keys(entity):
    return " AND ".join(f"{k} = %s" for k in entity.keys)


def list_rows(entity, search="", filter_value="", page=1):
    sql, params, conditions = entity.list_sql, [], []
    if search:
        conditions.append("(" + " OR ".join(f"{c} LIKE %s" for c in entity.search_cols) + ")")
        params += [f"%{search}%"] * len(entity.search_cols)
    if filter_value and entity.filter:
        conditions.append(f"{entity.filter[0]} = %s")
        params.append(filter_value)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    total = scalar(f"SELECT COUNT(*) FROM ({sql}) AS t", params)
    sql += f" ORDER BY {entity.order_by} LIMIT %s OFFSET %s"
    rows = query(sql, params + [PAGE_SIZE, (page - 1) * PAGE_SIZE])
    return rows, total


def get_row(entity, keyvals):
    return query_one(f"SELECT * FROM {entity.table} WHERE {where_keys(entity)}",
                     [keyvals[k] for k in entity.keys])


def insert(entity, values, cursor=None):
    cols = [c for c, v in values.items() if v is not None]  # NULL -> let DB defaults apply
    sql = (f"INSERT INTO {entity.table} ({', '.join(cols)}) "
           f"VALUES ({', '.join(['%s'] * len(cols))})")
    params = [values[c] for c in cols]
    if cursor:  # inside a transaction
        cursor.execute(sql, params)
        return cursor.lastrowid
    return execute(sql, params)[0]


def update(entity, keyvals, values):
    sets = ", ".join(f"{c} = %s" for c in values)
    sql = f"UPDATE {entity.table} SET {sets} WHERE {where_keys(entity)}"
    return execute(sql, list(values.values()) + [keyvals[k] for k in entity.keys])[1]


def delete(entity, keyvals):
    return execute(f"DELETE FROM {entity.table} WHERE {where_keys(entity)}",
                   [keyvals[k] for k in entity.keys])[1]


def blocking_dependents(entity, keyvals):
    """Return friendly reasons why a row cannot be deleted (empty list = safe)."""
    reasons = []
    key = keyvals[entity.keys[0]]
    for message, sql in entity.dependents:
        count = scalar(sql, [key] * sql.count("%s"))
        if count:
            reasons.append(f"{count} {message}")
    return reasons


# ---------------------------------------------------------------------------
# Reservation-specific operations
# ---------------------------------------------------------------------------
def reservation_detail(reservation_id):
    header = query_one(
        "SELECT r.*, p.first_name, p.second_name, p.last_name, p.email_address, p.phone_number, "
        "a.agent_name FROM reservation r "
        "JOIN passenger p ON p.passenger_id = r.passenger_id "
        "LEFT JOIN booking_agent a ON a.agent_id = r.agent_id WHERE r.reservation_id = %s",
        (reservation_id,))
    if not header:
        return None
    # Payments and legs are read in SEPARATE queries so totals are not inflated
    payments = query(
        "SELECT pm.*, (SELECT COUNT(*) FROM reservation_payment x WHERE x.payment_id = pm.payment_id) AS shared_count "
        "FROM reservation_payment rp JOIN payment pm ON pm.payment_id = rp.payment_id "
        "WHERE rp.reservation_id = %s ORDER BY pm.payment_date", (reservation_id,))
    legs = query(
        "SELECT l.*, s.airline_code, s.departure_datetime_utc AS scheduled_departure_utc, "
        "s.arrival_datetime_utc AS scheduled_arrival_utc FROM reservation_leg rl "
        "JOIN flight_leg l ON l.leg_id = rl.leg_id JOIN flight_schedule s ON s.flight_number = l.flight_number "
        "WHERE rl.reservation_id = %s ORDER BY COALESCE(l.actual_departure_utc, s.departure_datetime_utc)",
        (reservation_id,))
    total_paid = sum(p["payment_amount"] for p in payments if p["payment_status_code"] == "PAID")
    return {"r": header, "payments": payments, "legs": legs, "total_paid": total_paid}


def create_reservation_with_legs(values, leg_ids):
    """One transaction: insert reservation + its first legs (all or nothing)."""
    from entities import ENTITIES
    with transaction() as cur:
        new_id = insert(ENTITIES["reservations"], values, cursor=cur)
        for leg_id in leg_ids:
            cur.execute("INSERT INTO reservation_leg (reservation_id, leg_id) VALUES (%s, %s)", (new_id, leg_id))
    return new_id


def link_exists(table, other_col, reservation_id, other_id):
    return scalar(f"SELECT COUNT(*) FROM {table} WHERE reservation_id = %s AND {other_col} = %s",
                  (reservation_id, other_id))


def add_link(table, other_col, reservation_id, other_id):
    execute(f"INSERT INTO {table} (reservation_id, {other_col}) VALUES (%s, %s)", (reservation_id, other_id))


def remove_link(table, other_col, reservation_id, other_id):
    """Deletes ONLY the link row - the payment / leg itself stays."""
    return execute(f"DELETE FROM {table} WHERE reservation_id = %s AND {other_col} = %s",
                   (reservation_id, other_id))[1]


def create_payment_and_link(values, reservation_ids):
    """One transaction: new payment + links to one or more reservations."""
    from entities import ENTITIES
    with transaction() as cur:
        payment_id = insert(ENTITIES["payments"], values, cursor=cur)
        for rid in reservation_ids:
            cur.execute("INSERT INTO reservation_payment (reservation_id, payment_id) VALUES (%s, %s)",
                        (rid, payment_id))
    return payment_id
