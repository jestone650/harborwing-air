"""
Entity definitions: which table each screen uses, its fields, how to
search it, what blocks a delete, and the validation rules.

Table and column names here are fixed by the developer (never typed by a
user), so they are safe to put into SQL text.  User VALUES always travel
as %s parameters.
"""
import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from db import query, scalar

RESERVATION_STATUS = [("PEND", "PEND - Pending"), ("CONF", "CONF - Confirmed"),
                      ("CANC", "CANC - Cancelled"), ("COMP", "COMP - Completed")]
TICKET_TYPES = [("ONEWAY", "ONEWAY - One way"), ("RETURN", "RETURN - Return"),
                ("MULTI", "MULTI - Multi-city")]
TRAVEL_CLASSES = [("ECON", "ECON - Economy"), ("PREM", "PREM - Premium economy"),
                  ("BUS", "BUS - Business"), ("FIRST", "FIRST - First")]
PAYMENT_STATUS = [("PEND", "PEND - Pending"), ("PAID", "PAID - Paid"),
                  ("REFD", "REFD - Refunded"), ("FAIL", "FAIL - Failed")]

# Option lists for drop-downs (value, label)
OPTION_SQL = {
    "passenger": "SELECT passenger_id AS v, CONCAT(passenger_id, ' - ', first_name, ' ', last_name) AS l "
                 "FROM passenger ORDER BY last_name, first_name",
    "agent": "SELECT agent_id AS v, CONCAT(agent_id, ' - ', agent_name) AS l FROM booking_agent ORDER BY agent_name",
    "airport": "SELECT airport_code AS v, CONCAT(airport_code, ' - ', airport_name) AS l FROM airport ORDER BY airport_code",
    "airline": "SELECT airline_code AS v, CONCAT(airline_code, ' - ', airline_name) AS l FROM airline ORDER BY airline_code",
    "aircraft": "SELECT aircraft_type_code AS v, CONCAT(aircraft_type_code, ' - ', aircraft_description) AS l "
                "FROM aircraft_type ORDER BY aircraft_type_code",
    "schedule": "SELECT flight_number AS v, CONCAT(flight_number, ' (', origin_airport_code, '->', "
                "destination_airport_code, ')') AS l FROM flight_schedule ORDER BY flight_number",
    "leg": "SELECT leg_id AS v, CONCAT('Leg ', leg_id, ' - ', flight_number, ' ', origin_airport_code, '->', "
           "destination_airport_code, ' ', COALESCE(DATE_FORMAT(actual_departure_utc, '%%Y-%%m-%%d %%H:%%i'), "
           "'not yet flown')) AS l FROM flight_leg ORDER BY leg_id",
    "payment": "SELECT payment_id AS v, CONCAT('Payment ', payment_id, ' - ', payment_status_code, ' ', "
               "payment_amount, ' on ', payment_date) AS l FROM payment ORDER BY payment_id DESC",
}


def options(name):
    return [(str(r["v"]), r["l"]) for r in query(OPTION_SQL[name])]


@dataclass
class Field:
    name: str
    label: str
    type: str = "text"        # text, textarea, email, int, money, date, datetime, choice, fk
    required: bool = True
    maxlen: int = None
    choices: list = None      # for type=choice
    fk: str = None            # key of OPTION_SQL for type=fk
    key: bool = False         # part of the primary key
    auto: bool = False        # AUTO_INCREMENT key (not typed by the user)
    upper: bool = False       # convert to upper case
    pattern: str = None       # regex the value must match
    help: str = ""


@dataclass
class Entity:
    name: str
    table: str
    title: str
    fields: list
    list_sql: str             # SELECT ... FROM ... (no WHERE / ORDER)
    search_cols: list
    order_by: str
    list_cols: list           # (column alias, header)
    dependents: list = field(default_factory=list)   # (message, COUNT sql)
    delete_note: str = ""
    filter: tuple = None      # (sql column, label, choices)
    check: object = None      # extra validation function(values, keyvals) -> [errors]

    @property
    def keys(self):
        return [f.name for f in self.fields if f.key]

    @property
    def editable(self):
        return [f for f in self.fields if not f.auto]


# ---------------------------------------------------------------------------
# Extra business-rule checks (run before the database sees the data)
# ---------------------------------------------------------------------------
def check_route(values, _keys):
    errors = []
    if values.get("origin_airport_code") and values.get("origin_airport_code") == values.get("destination_airport_code"):
        errors.append("Origin and destination airports must be different.")
    return errors


def check_schedule(values, keys):
    errors = check_route(values, keys)
    dep, arr = values.get("departure_datetime_utc"), values.get("arrival_datetime_utc")
    if dep and arr and arr <= dep:
        errors.append("Scheduled arrival must be after scheduled departure.")
    return errors


def check_leg(values, keys):
    errors = check_route(values, keys)
    dep, arr = values.get("actual_departure_utc"), values.get("actual_arrival_utc")
    if arr and not dep:
        errors.append("An actual arrival needs an actual departure.")
    if dep and arr and arr <= dep:
        errors.append("Actual arrival must be after actual departure.")
    return errors


def check_cost(values, keys):
    errors = []
    start, end = values.get("valid_from_date"), values.get("valid_to_date")
    if start and end and end < start:
        errors.append("Valid-to date must not be before valid-from date.")
    for label, day in (("Valid-from", start), ("Valid-to", end)):
        if day and not scalar("SELECT COUNT(*) FROM calendar_date WHERE day_date = %s", (day,)):
            errors.append(f"{label} date {day} is not in the calendar table (calendar covers 2025-2027).")
    if not errors and start and end:
        # overlap policy: periods for the same flight + aircraft type may not overlap
        params = [values["flight_number"], values["aircraft_type_code"], end, start]
        sql = ("SELECT COUNT(*) FROM flight_cost WHERE flight_number = %s AND aircraft_type_code = %s "
               "AND valid_from_date <= %s AND valid_to_date >= %s")
        if keys:  # editing: ignore the record itself
            sql += " AND NOT (flight_number = %s AND aircraft_type_code = %s AND valid_from_date = %s)"
            params += [keys["flight_number"], keys["aircraft_type_code"], keys["valid_from_date"]]
        if scalar(sql, params):
            errors.append("This validity period overlaps another cost period for the same flight and aircraft type.")
    return errors


# ---------------------------------------------------------------------------
# The eight CRUD entities
# ---------------------------------------------------------------------------
ENTITIES = {e.name: e for e in [
    Entity(
        name="passengers", table="passenger", title="Passengers",
        fields=[
            Field("passenger_id", "Passenger ID", "int", key=True, auto=True),
            Field("first_name", "First name", maxlen=60),
            Field("second_name", "Second name", required=False, maxlen=60),
            Field("last_name", "Last name", maxlen=60),
            Field("phone_number", "Phone number", maxlen=30, pattern=r"^[0-9+()\-. x]{7,30}$",
                  help="Digits, spaces and + ( ) - . only"),
            Field("email_address", "Email address", "email", maxlen=120),
            Field("address_line_1", "Address line 1", maxlen=120),
            Field("address_line_2", "Address line 2", required=False, maxlen=120),
            Field("city", "City", maxlen=80),
            Field("state_province_county", "State / province / county", required=False, maxlen=80),
            Field("country", "Country", maxlen=80),
            Field("other_details", "Other details", "textarea", required=False, maxlen=500),
        ],
        list_sql="SELECT passenger_id, first_name, last_name, email_address, phone_number, city, country FROM passenger",
        search_cols=["first_name", "last_name", "email_address", "phone_number", "city"],
        order_by="passenger_id DESC",
        list_cols=[("passenger_id", "ID"), ("first_name", "First"), ("last_name", "Last"),
                   ("email_address", "Email"), ("phone_number", "Phone"), ("city", "City")],
        dependents=[("reservation(s) belong to this passenger",
                     "SELECT COUNT(*) FROM reservation WHERE passenger_id = %s")],
    ),
    Entity(
        name="agents", table="booking_agent", title="Booking agents",
        fields=[
            Field("agent_id", "Agent ID", "int", key=True, auto=True),
            Field("agent_name", "Agent name", maxlen=120),
            Field("agent_details", "Details", "textarea", required=False, maxlen=500),
        ],
        list_sql="SELECT a.agent_id, a.agent_name, a.agent_details, "
                 "(SELECT COUNT(*) FROM reservation r WHERE r.agent_id = a.agent_id) AS reservations FROM booking_agent a",
        search_cols=["a.agent_name", "a.agent_details"],
        order_by="a.agent_id DESC",
        list_cols=[("agent_id", "ID"), ("agent_name", "Name"), ("agent_details", "Details"),
                   ("reservations", "Reservations")],
        delete_note="Deleting an agent keeps their reservations; they become direct bookings (agent set to NULL).",
    ),
    Entity(
        name="airports", table="airport", title="Airports",
        fields=[
            Field("airport_code", "Airport code", key=True, upper=True, pattern=r"^[A-Z]{3}$",
                  help="Exactly 3 letters, e.g. HWA"),
            Field("airport_name", "Airport name", maxlen=120),
            Field("airport_location", "Location", maxlen=160),
            Field("other_details", "Other details", "textarea", required=False, maxlen=500),
        ],
        list_sql="SELECT airport_code, airport_name, airport_location FROM airport",
        search_cols=["airport_code", "airport_name", "airport_location"],
        order_by="airport_code",
        list_cols=[("airport_code", "Code"), ("airport_name", "Name"), ("airport_location", "Location")],
        dependents=[
            ("flight schedule(s) use this airport",
             "SELECT COUNT(*) FROM flight_schedule WHERE origin_airport_code = %s OR destination_airport_code = %s"),
            ("flight leg(s) use this airport",
             "SELECT COUNT(*) FROM flight_leg WHERE origin_airport_code = %s OR destination_airport_code = %s"),
        ],
    ),
    Entity(
        name="schedules", table="flight_schedule", title="Flight schedules",
        fields=[
            Field("flight_number", "Flight number", key=True, upper=True, pattern=r"^[A-Z0-9]{3,10}$",
                  help="e.g. HW123"),
            Field("airline_code", "Airline", "fk", fk="airline"),
            Field("usual_aircraft_type_code", "Usual aircraft type", "fk", fk="aircraft"),
            Field("origin_airport_code", "Origin airport", "fk", fk="airport"),
            Field("destination_airport_code", "Destination airport", "fk", fk="airport"),
            Field("departure_datetime_utc", "Scheduled departure (UTC)", "datetime"),
            Field("arrival_datetime_utc", "Scheduled arrival (UTC)", "datetime"),
        ],
        list_sql="SELECT flight_number, airline_code, origin_airport_code, destination_airport_code, "
                 "departure_datetime_utc, arrival_datetime_utc, usual_aircraft_type_code FROM flight_schedule",
        search_cols=["flight_number", "origin_airport_code", "destination_airport_code", "airline_code"],
        order_by="flight_number",
        list_cols=[("flight_number", "Flight"), ("airline_code", "Airline"), ("origin_airport_code", "From"),
                   ("destination_airport_code", "To"), ("departure_datetime_utc", "Sched. dep (UTC)"),
                   ("arrival_datetime_utc", "Sched. arr (UTC)"), ("usual_aircraft_type_code", "Aircraft")],
        dependents=[("flight leg(s) belong to this schedule", "SELECT COUNT(*) FROM flight_leg WHERE flight_number = %s"),
                    ("cost record(s) belong to this schedule", "SELECT COUNT(*) FROM flight_cost WHERE flight_number = %s")],
        check=check_schedule,
    ),
    Entity(
        name="legs", table="flight_leg", title="Flight legs",
        fields=[
            Field("leg_id", "Leg ID", "int", key=True, auto=True),
            Field("flight_number", "Scheduled flight", "fk", fk="schedule"),
            Field("origin_airport_code", "Origin airport", "fk", fk="airport"),
            Field("destination_airport_code", "Destination airport", "fk", fk="airport"),
            Field("actual_departure_utc", "Actual departure (UTC)", "datetime", required=False,
                  help="Leave empty until the flight operates"),
            Field("actual_arrival_utc", "Actual arrival (UTC)", "datetime", required=False),
        ],
        list_sql="SELECT l.leg_id, l.flight_number, l.origin_airport_code, l.destination_airport_code, "
                 "s.departure_datetime_utc AS scheduled_departure_utc, l.actual_departure_utc, l.actual_arrival_utc "
                 "FROM flight_leg l JOIN flight_schedule s ON s.flight_number = l.flight_number",
        search_cols=["l.flight_number", "l.origin_airport_code", "l.destination_airport_code", "CAST(l.leg_id AS CHAR)"],
        order_by="l.leg_id DESC",
        list_cols=[("leg_id", "Leg"), ("flight_number", "Flight"), ("origin_airport_code", "From"),
                   ("destination_airport_code", "To"), ("scheduled_departure_utc", "Scheduled dep"),
                   ("actual_departure_utc", "Actual dep"), ("actual_arrival_utc", "Actual arr")],
        dependents=[("reservation(s) are linked to this leg - remove those links first",
                     "SELECT COUNT(*) FROM reservation_leg WHERE leg_id = %s")],
        check=check_leg,
    ),
    Entity(
        name="costs", table="flight_cost", title="Flight costs",
        fields=[
            Field("flight_number", "Scheduled flight", "fk", fk="schedule", key=True),
            Field("aircraft_type_code", "Aircraft type", "fk", fk="aircraft", key=True),
            Field("valid_from_date", "Valid from", "date", key=True),
            Field("valid_to_date", "Valid to", "date"),
            Field("cost_amount", "Cost amount", "money", help="0 or more"),
        ],
        list_sql="SELECT flight_number, aircraft_type_code, valid_from_date, valid_to_date, cost_amount FROM flight_cost",
        search_cols=["flight_number", "aircraft_type_code"],
        order_by="flight_number, aircraft_type_code, valid_from_date",
        list_cols=[("flight_number", "Flight"), ("aircraft_type_code", "Aircraft"), ("valid_from_date", "From"),
                   ("valid_to_date", "To"), ("cost_amount", "Cost")],
        check=check_cost,
    ),
    Entity(
        name="reservations", table="reservation", title="Reservations",
        fields=[
            Field("reservation_id", "Reservation ID", "int", key=True, auto=True),
            Field("passenger_id", "Main passenger", "fk", fk="passenger"),
            Field("agent_id", "Booking agent (empty = direct booking)", "fk", fk="agent", required=False),
            Field("reservation_status_code", "Status", "choice", choices=RESERVATION_STATUS),
            Field("ticket_type_code", "Ticket type", "choice", choices=TICKET_TYPES),
            Field("travel_class_code", "Travel class", "choice", choices=TRAVEL_CLASSES),
            Field("created_at_utc", "Created (UTC)", "datetime", required=False,
                  help="Leave empty to use the current UTC time"),
            Field("number_in_party", "Number in party", "int", help="Must be greater than 0"),
        ],
        list_sql="SELECT r.reservation_id, CONCAT(p.first_name, ' ', p.last_name) AS passenger, "
                 "COALESCE(a.agent_name, '(direct)') AS agent, r.reservation_status_code, r.travel_class_code, "
                 "r.number_in_party, r.created_at_utc FROM reservation r "
                 "JOIN passenger p ON p.passenger_id = r.passenger_id "
                 "LEFT JOIN booking_agent a ON a.agent_id = r.agent_id",
        search_cols=["p.first_name", "p.last_name", "a.agent_name", "CAST(r.reservation_id AS CHAR)"],
        order_by="r.reservation_id DESC",
        list_cols=[("reservation_id", "ID"), ("passenger", "Main passenger"), ("agent", "Agent"),
                   ("reservation_status_code", "Status"), ("travel_class_code", "Class"),
                   ("number_in_party", "Party"), ("created_at_utc", "Created (UTC)")],
        delete_note="Deleting a reservation removes only its payment and leg LINKS. "
                    "The payments and legs themselves are kept.",
        filter=("r.reservation_status_code", "Status", RESERVATION_STATUS),
    ),
    Entity(
        name="payments", table="payment", title="Payments",
        fields=[
            Field("payment_id", "Payment ID", "int", key=True, auto=True),
            Field("payment_status_code", "Status", "choice", choices=PAYMENT_STATUS),
            Field("payment_date", "Payment date", "date"),
            Field("payment_amount", "Amount", "money", help="Must be greater than 0"),
        ],
        list_sql="SELECT pm.payment_id, pm.payment_status_code, pm.payment_date, pm.payment_amount, "
                 "(SELECT COUNT(*) FROM reservation_payment rp WHERE rp.payment_id = pm.payment_id) AS reservations "
                 "FROM payment pm",
        search_cols=["CAST(pm.payment_id AS CHAR)", "CAST(pm.payment_amount AS CHAR)", "CAST(pm.payment_date AS CHAR)"],
        order_by="pm.payment_id DESC",
        list_cols=[("payment_id", "ID"), ("payment_status_code", "Status"), ("payment_date", "Date"),
                   ("payment_amount", "Amount"), ("reservations", "Linked reservations")],
        dependents=[("reservation(s) are linked to this payment - remove those links first",
                     "SELECT COUNT(*) FROM reservation_payment WHERE payment_id = %s")],
        filter=("pm.payment_status_code", "Status", PAYMENT_STATUS),
    ),
]}


# ---------------------------------------------------------------------------
# Form parsing + validation
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_form(entity, form, editing=False):
    """Turn submitted text into typed values. Returns (values, errors)."""
    values, errors = {}, []
    for f in entity.editable:
        if editing and f.key:
            continue  # keys cannot be changed on edit
        raw = (form.get(f.name) or "").strip()
        if f.upper:
            raw = raw.upper()
        if raw == "":
            if f.required:
                errors.append(f"{f.label} is required.")
            values[f.name] = None
            continue
        if f.maxlen and len(raw) > f.maxlen:
            errors.append(f"{f.label} must be at most {f.maxlen} characters.")
            continue
        if f.pattern and not re.match(f.pattern, raw):
            errors.append(f"{f.label} has an invalid format. {f.help}")
            continue
        try:
            values[f.name] = convert(f, raw)
        except ValueError as exc:
            errors.append(f"{f.label}: {exc}")
    return values, errors


def convert(f, raw):
    if f.type == "int":
        if not re.fullmatch(r"\d+", raw) or int(raw) <= 0:
            raise ValueError("must be a whole number greater than 0")
        return int(raw)
    if f.type == "money":
        try:
            amount = Decimal(raw)
            if not amount.is_finite():
                raise InvalidOperation
            amount = amount.quantize(Decimal("0.01"))
        except InvalidOperation:
            raise ValueError("must be a number like 1500.00")
        if amount < 0 or (f.name == "payment_amount" and amount <= 0):
            raise ValueError("must be greater than 0" if f.name == "payment_amount" else "cannot be negative")
        if amount >= Decimal("10000000000"):
            raise ValueError("is too large")
        return amount
    if f.type == "date":
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            raise ValueError("must be a valid date (YYYY-MM-DD)")
    if f.type == "datetime":
        try:
            return dt.datetime.fromisoformat(raw.replace("T", " "))
        except ValueError:
            raise ValueError("must be a valid date and time")
    if f.type == "email" and not EMAIL_RE.match(raw):
        raise ValueError("must be a valid email address")
    if f.type == "choice" and raw not in [c[0] for c in f.choices]:
        raise ValueError("is not an allowed value")
    if f.type == "fk" and f.name in ("passenger_id", "agent_id"):
        if not raw.isdigit():
            raise ValueError("invalid selection")
        return int(raw)
    return raw
