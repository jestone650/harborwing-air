"""
HarborWing Air - synthetic data generator (Python + Faker)
File: database/seed.py

What it does
  1. Runs schema.sql  -> drops and recreates the `harborwing` database (RESET).
  2. Generates fictional data with a FIXED SEED (same data every run).
  3. Inserts parents before children, using only existing key values.
  4. Prints the row count of every table.

Usage
  python seed.py                      # reset + seed the MySQL database
  python seed.py --sql-out seed_data.sql   # ALSO write the INSERTs to a .sql file
  python seed.py --dry-run            # only generate + validate, no database needed

Connection settings come from environment variables or a .env file
(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD).  See .env.example.
"""

import argparse
import datetime as dt
import os
import random
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from faker import Faker

SEED = 2026                                  # change -> different (but repeatable) data
REFERENCE_NOW = dt.datetime(2026, 10, 14, 0, 0)  # fixed "today" so runs are repeatable
CAL_START, CAL_END = dt.date(2025, 1, 1), dt.date(2027, 12, 31)
HERE = Path(__file__).resolve().parent

random.seed(SEED)
Faker.seed(SEED)
fake = Faker("en_US")

TABLE_ORDER = [  # parent tables first, children last
    "airline", "aircraft_type", "calendar_date", "airport", "booking_agent",
    "passenger", "flight_schedule", "flight_leg", "flight_cost",
    "reservation", "payment", "reservation_payment", "reservation_leg",
]

COLUMNS = {
    "airline": ["airline_code", "airline_name", "is_demo_data"],
    "aircraft_type": ["aircraft_type_code", "aircraft_description", "seat_capacity", "is_demo_data"],
    "calendar_date": ["day_date", "day_of_month", "is_business_day"],
    "airport": ["airport_code", "airport_name", "airport_location", "other_details"],
    "booking_agent": ["agent_id", "agent_name", "agent_details"],
    "passenger": ["passenger_id", "first_name", "second_name", "last_name", "phone_number",
                  "email_address", "address_line_1", "address_line_2", "city",
                  "state_province_county", "country", "other_details"],
    "flight_schedule": ["flight_number", "airline_code", "usual_aircraft_type_code",
                        "origin_airport_code", "destination_airport_code",
                        "departure_datetime_utc", "arrival_datetime_utc"],
    "flight_leg": ["leg_id", "flight_number", "origin_airport_code", "destination_airport_code",
                   "actual_departure_utc", "actual_arrival_utc"],
    "flight_cost": ["flight_number", "aircraft_type_code", "valid_from_date",
                    "valid_to_date", "cost_amount"],
    "reservation": ["reservation_id", "passenger_id", "agent_id", "reservation_status_code",
                    "ticket_type_code", "travel_class_code", "created_at_utc", "number_in_party"],
    "payment": ["payment_id", "payment_status_code", "payment_date", "payment_amount"],
    "reservation_payment": ["reservation_id", "payment_id"],
    "reservation_leg": ["reservation_id", "leg_id"],
}


def rand_datetime(start, end):
    """Random datetime between start and end, rounded to 5 minutes."""
    seconds = int((end - start).total_seconds())
    value = start + dt.timedelta(seconds=random.randint(0, seconds))
    return value.replace(minute=value.minute - value.minute % 5, second=0)


def money(value):
    return Decimal(value).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Generators (pure Python - no database needed)
# ---------------------------------------------------------------------------
def gen_airlines():
    rows = [("HW", "HarborWing Air", False)]  # the main (fictional) airline
    codes = {"HW"}
    names = {"HarborWing Air"}
    suffixes = ["Air", "Airways", "Aviation", "Skylines", "Wings", "Island Hopper"]
    while len(rows) < 50:
        code = random.choice("ABCDEFGHJKLMNPRSTUVWXYZ") + random.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")
        name = f"{fake.last_name()} {random.choice(suffixes)} (DEMO)"
        if code in codes or name in names:
            continue
        codes.add(code)
        names.add(name)
        rows.append((code, name, True))
    return rows


def gen_aircraft_types():
    makers = ["Skyline", "Aerowing", "Coastjet", "Islander", "Gullstream", "Tidewing"]
    rows = []
    for n in range(1, 51):
        maker = random.choice(makers)
        model = f"{random.choice(['T', 'Q', 'J', 'S'])}{random.randint(10, 99)}"
        seats = random.choice([9, 19, 48, 70, 78, 120, 150, 180, 220])
        rows.append((f"DM{n:03d}", f"DEMO aircraft - {maker} {model}", seats, True))
    return rows


def gen_calendar():
    holidays = {(1, 1), (4, 9), (5, 1), (6, 12), (8, 21), (11, 30), (12, 25), (12, 30)}  # fictional list
    rows, day = [], CAL_START
    while day <= CAL_END:
        business = day.weekday() < 5 and (day.month, day.day) not in holidays
        rows.append((day, day.day, business))
        day += dt.timedelta(days=1)
    return rows


def gen_airports(count=60):
    suffixes = ["Harbor Airport", "Coastal Airfield", "Island Airstrip", "Bay Airport", "Seaport Airfield"]
    rows, codes, names = [], set(), set()
    while len(rows) < count:
        code = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3))
        city = fake.city()
        name = f"{city} {random.choice(suffixes)}"
        if code in codes or name in names:
            continue
        codes.add(code)
        names.add(name)
        location = f"{city}, {fake.state()}, Fictional Coast"
        details = random.choice([None, "Single runway", "Seaplane dock available",
                                 "Daylight operations only", "Ferry connection to islands"])
        rows.append((code, name, location, details))
    return rows


def gen_agents(count=60):
    rows = []
    for agent_id in range(1, count + 1):
        name = f"{fake.unique.company()} Travel"[:120]
        details = None if random.random() < 0.25 else f"Contact {fake.name()} - {fake.phone_number()}"
        rows.append((agent_id, name, details))
    return rows


def gen_passengers(count=200):
    rows = []
    for pid in range(1, count + 1):
        first, last = fake.first_name(), fake.last_name()
        second = fake.first_name() if random.random() < 0.4 else None
        email = f"{first}.{last}.{pid}@example.com".lower()  # example.com = never a real inbox
        rows.append((
            pid, first, second, last, fake.phone_number()[:30], email,
            fake.street_address(),
            fake.secondary_address() if random.random() < 0.3 else None,
            fake.city(), fake.state(), "Fictional Coast",
            random.choice([None, None, "Prefers aisle seat", "Frequent flyer", "Needs wheelchair assistance at gate"]),
        ))
    return rows


def gen_schedules(airports, airlines, aircraft, count=80):
    codes = [a[0] for a in airports]
    hubs = codes[:6]  # a few hubs make connecting journeys possible
    partner_airlines = [a[0] for a in airlines if a[0] != "HW"]
    aircraft_codes = [a[0] for a in aircraft]
    rows, numbers = [], set()
    while len(rows) < count:
        if random.random() < 0.8:
            airline = "HW"
            number = f"HW{random.randint(100, 999)}"
        else:
            airline = random.choice(partner_airlines)
            number = f"{airline}{random.randint(1000, 9999)}"
        if number in numbers:
            continue
        if random.random() < 0.7:  # hub route
            hub, spoke = random.choice(hubs), random.choice(codes)
            origin, dest = (hub, spoke) if random.random() < 0.5 else (spoke, hub)
        else:
            origin, dest = random.sample(codes, 2)
        if origin == dest:
            continue
        numbers.add(number)
        dep = rand_datetime(dt.datetime(2026, 1, 5), dt.datetime(2026, 3, 31))
        arr = dep + dt.timedelta(minutes=random.randint(35, 240))
        rows.append((number, airline, random.choice(aircraft_codes), origin, dest, dep, arr))
    return rows


def gen_legs(schedules, count=320):
    rows, leg_id = [], 0
    while len(rows) < count:
        for number, _, _, origin, dest, dep, arr in schedules:
            if len(rows) >= count:
                break
            # a leg = one weekly operation of the schedule (some past, some future)
            operated = dep + dt.timedelta(days=7 * random.randint(0, 55))
            leg_id += 1
            if operated < REFERENCE_NOW:  # flight has operated -> actual times known
                actual_dep = operated + dt.timedelta(minutes=random.randint(-5, 90))
                actual_arr = actual_dep + (arr - dep) + dt.timedelta(minutes=random.randint(-10, 30))
                if actual_arr <= actual_dep:
                    actual_arr = actual_dep + dt.timedelta(minutes=30)
            else:  # future flight -> actual times unknown
                actual_dep = actual_arr = None
            rows.append((leg_id, number, origin, dest, actual_dep, actual_arr))
    return rows


def gen_costs(schedules, aircraft):
    rows, aircraft_codes = [], [a[0] for a in aircraft]
    for number, _, usual, *_ in schedules:
        types = [usual]
        if random.random() < 0.4:
            types.append(random.choice([c for c in aircraft_codes if c != usual]))
        for ac in types:
            start = CAL_START + dt.timedelta(days=random.randint(0, 60))
            base = random.randint(40_000, 400_000)
            for _ in range(random.randint(1, 3)):  # consecutive, NON-overlapping periods
                end = min(start + dt.timedelta(days=random.randint(90, 300)), CAL_END)
                rows.append((number, ac, start, end, money(base)))
                base = int(base * random.uniform(1.02, 1.12))  # costs go up over time
                start = end + dt.timedelta(days=1)
                if start > CAL_END:
                    break
    return rows


def gen_reservations(passengers, agents, legs, count=300):
    """Returns (reservations, reservation_leg links)."""
    legs_by_origin = defaultdict(list)
    for leg in legs:
        legs_by_origin[leg[2]].append(leg)
    reservations, links = [], set()
    for rid in range(1, count + 1):
        n_legs = random.choices([1, 2, 3, 4], weights=[35, 40, 15, 10])[0]
        chosen = [random.choice(legs)]
        while len(chosen) < n_legs:  # try to build a connecting journey
            options = [l for l in legs_by_origin[chosen[-1][3]] if l not in chosen]
            chosen.append(random.choice(options) if options else
                          random.choice([l for l in legs if l not in chosen]))
        if n_legs == 1:
            ticket = "ONEWAY"
        elif n_legs == 2 and chosen[1][3] == chosen[0][2]:
            ticket = "RETURN"
        else:
            ticket = "MULTI"
        agent = random.choice(agents)[0] if random.random() < 0.45 else None  # direct vs agent
        created = rand_datetime(dt.datetime(2025, 6, 1), dt.datetime(2026, 10, 13))
        reservations.append((
            rid, random.choice(passengers)[0], agent,
            random.choices(["CONF", "PEND", "CANC", "COMP"], weights=[50, 15, 10, 25])[0],
            ticket,
            random.choices(["ECON", "PREM", "BUS", "FIRST"], weights=[65, 15, 15, 5])[0],
            created,
            random.choices([1, 2, 3, 4, 5, 6], weights=[40, 25, 12, 12, 6, 5])[0],
        ))
        for leg in chosen:
            links.add((rid, leg[0]))
    return reservations, sorted(links)


def gen_payments(reservations, reservation_legs):
    """Returns (payments, reservation_payment links). Includes split and shared payments."""
    class_factor = {"ECON": 1.0, "PREM": 1.5, "BUS": 2.5, "FIRST": 4.0}
    legs_per_res = defaultdict(int)
    for rid, _ in reservation_legs:
        legs_per_res[rid] += 1
    payments, links, pid = [], set(), 0

    def new_payment(amount, created):
        nonlocal pid
        pid += 1
        pay_date = min((created + dt.timedelta(days=random.randint(0, 30))).date(), REFERENCE_NOW.date())
        status = random.choices(["PAID", "PEND", "REFD", "FAIL"], weights=[70, 15, 8, 7])[0]
        payments.append((pid, status, pay_date, money(max(amount, 1))))
        return pid

    for rid, _, _, _, _, cls, created, party in reservations:
        total = legs_per_res[rid] * random.randint(1500, 9000) * class_factor[cls] * party
        n_pay = random.choices([0, 1, 2, 3], weights=[10, 60, 20, 10])[0]  # several payments
        for _ in range(n_pay):
            links.add((rid, new_payment(total / n_pay, created)))

    # Shared payments: one payment covering several reservations of the same passenger
    by_passenger = defaultdict(list)
    for r in reservations:
        by_passenger[r[1]].append(r)
    groups = [rs for rs in by_passenger.values() if len(rs) >= 2]
    random.shuffle(groups)
    for group in groups[:40]:
        covered = random.sample(group, min(len(group), random.randint(2, 3)))
        pay = new_payment(random.randint(3000, 30000), max(r[6] for r in covered))
        for r in covered:
            links.add((r[0], pay))
    return payments, sorted(links)


def generate():
    data = {}
    data["airline"] = gen_airlines()
    data["aircraft_type"] = gen_aircraft_types()
    data["calendar_date"] = gen_calendar()
    data["airport"] = gen_airports()
    data["booking_agent"] = gen_agents()
    data["passenger"] = gen_passengers()
    data["flight_schedule"] = gen_schedules(data["airport"], data["airline"], data["aircraft_type"])
    data["flight_leg"] = gen_legs(data["flight_schedule"])
    data["flight_cost"] = gen_costs(data["flight_schedule"], data["aircraft_type"])
    data["reservation"], data["reservation_leg"] = gen_reservations(
        data["passenger"], data["booking_agent"], data["flight_leg"])
    data["payment"], data["reservation_payment"] = gen_payments(
        data["reservation"], data["reservation_leg"])
    return data


def validate(data):
    """Self-checks that mirror the business rules (runs before inserting)."""
    for table in TABLE_ORDER:
        assert len(data[table]) >= 50, f"{table} has fewer than 50 rows"
    assert len(set(data["reservation_leg"])) == len(data["reservation_leg"])
    assert len(set(data["reservation_payment"])) == len(data["reservation_payment"])
    assert all(r[3] != r[4] for r in data["flight_schedule"])
    assert all(r[2] != r[3] for r in data["flight_leg"])
    assert all(p[3] > 0 for p in data["payment"])
    assert all(r[7] > 0 for r in data["reservation"])
    cal = {r[0] for r in data["calendar_date"]}
    keys = set()
    for f, a, start, end, cost in data["flight_cost"]:
        assert start in cal and end in cal and end >= start and cost >= 0
        assert (f, a, start) not in keys
        keys.add((f, a, start))
    # required scenarios
    res_pay = defaultdict(int); pay_res = defaultdict(int); res_leg = defaultdict(int)
    for r, p in data["reservation_payment"]:
        res_pay[r] += 1; pay_res[p] += 1
    for r, _ in data["reservation_leg"]:
        res_leg[r] += 1
    assert any(v > 1 for v in res_pay.values()), "need reservations with several payments"
    assert any(v > 1 for v in pay_res.values()), "need payments shared by several reservations"
    assert any(v > 1 for v in res_leg.values()), "need reservations with several legs"
    assert any(r[2] is None for r in data["reservation"]) and any(r[2] for r in data["reservation"])


# ---------------------------------------------------------------------------
# Output: MySQL database and/or .sql file
# ---------------------------------------------------------------------------
def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, dt.datetime):
        return f"'{value:%Y-%m-%d %H:%M:%S}'"
    if isinstance(value, dt.date):
        return f"'{value:%Y-%m-%d}'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def write_sql_file(data, path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"-- Generated by seed.py (seed={SEED}). Run schema.sql first.\nUSE harborwing;\n")
        for table in TABLE_ORDER:
            cols = ", ".join(COLUMNS[table])
            for i in range(0, len(data[table]), 200):
                chunk = data[table][i:i + 200]
                values = ",\n  ".join("(" + ", ".join(sql_literal(v) for v in row) + ")" for row in chunk)
                fh.write(f"INSERT INTO {table} ({cols}) VALUES\n  {values};\n")
    print(f"Wrote {path}")


def load_settings():
    try:
        from dotenv import load_dotenv
        load_dotenv(HERE / ".env")
    except ImportError:
        pass
    password = os.getenv("DB_PASSWORD")
    if password is None:
        import getpass
        password = getpass.getpass("MySQL password: ")
    return dict(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "3306")),
                user=os.getenv("DB_USER", "root"), password=password)


def run_schema(cursor):
    text = (HERE / "schema.sql").read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    for statement in text.split(";"):
        if statement.strip():
            cursor.execute(statement)


def insert_into_mysql(data):
    import pymysql
    conn = pymysql.connect(**load_settings(), charset="utf8mb4", autocommit=False)
    try:
        with conn.cursor() as cur:
            print("Resetting database (schema.sql) ...")
            run_schema(cur)
            for table in TABLE_ORDER:
                cols = COLUMNS[table]
                sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
                cur.executemany(sql, data[table])  # parameterized
            conn.commit()  # all-or-nothing
            print("\nRow counts:")
            for table in TABLE_ORDER:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"  {table:<22}{cur.fetchone()[0]:>6}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Reset and seed the HarborWing database.")
    parser.add_argument("--sql-out", help="also write the INSERT statements to this .sql file")
    parser.add_argument("--dry-run", action="store_true", help="generate and validate only")
    args = parser.parse_args()

    data = generate()
    validate(data)
    print("Generated rows:", {t: len(data[t]) for t in TABLE_ORDER})
    if args.sql_out:
        write_sql_file(data, args.sql_out)
    if not args.dry_run:
        insert_into_mysql(data)
        print("\nDone. Database `harborwing` is ready.")


if __name__ == "__main__":
    sys.exit(main())
