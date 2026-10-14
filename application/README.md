# HarborWing Air — CRUD Application (Part 2)

A small web application (Python **Flask** + **PyMySQL**) that lets HarborWing employees work with the
reservation database without writing SQL.

**Database dependency:** uses the `harborwing` database from [`../database`](../database/README.md)
(Midterm Drill). Use the same commit of this repository for both folders. Schema version: the one in
`database/schema.sql` at this commit — **no schema changes were needed for the application.**

---

## 1. Install and run

```bash
# 1) Create the database first (once)
cd database
pip install -r requirements.txt
python seed.py

# 2) Install the app
cd ../application
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3) Configure credentials (never commit .env)
copy .env.example .env          # macOS/Linux: cp .env.example .env
#    edit .env -> DB_PASSWORD=<your MySQL password>

# 4) Start
python app.py
#    open http://127.0.0.1:5000
```

`.env` settings: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (default `harborwing`),
`FLASK_SECRET_KEY`, `FLASK_DEBUG`. `.env` is listed in `.gitignore`.

---

## 2. Features

| Area | What you can do |
|---|---|
| Passengers, Booking agents, Airports, Flight schedules, Flight legs, Flight costs, Reservations, Payments | List, search, filter (status), page, create, edit, delete |
| Reservation page | See passenger, agent, all legs and all payments in one place |
| Links | Add / remove legs and payments on a reservation (removing a link never deletes the leg or payment) |
| Payments | Create a payment and link it to this reservation (and optionally other reservations) in one transaction |
| New reservation | Choose initial legs; the reservation and its links are saved in one transaction |
| Reference / Calendar | Read-only views of airlines, aircraft types, code lists and calendar dates (maintained by `seed.py`) |

### Validation and error handling
* Required fields, maximum lengths, email/phone/code formats, positive numbers, valid dates.
* Business rules checked before saving: origin ≠ destination, arrival after departure, valid-to ≥ valid-from,
  cost dates must exist in the calendar, cost periods may not overlap, party size > 0, payment amount > 0.
* Duplicate links are detected and reported ("already linked"); the composite primary key is the final guard.
* Missing records show a "not found" page instead of crashing.
* Database errors are translated into plain messages (duplicate, still in use, missing reference, rule broken,
  cannot connect).

### Safe deletion policy
Before deleting, the app counts dependent rows and explains why a delete is blocked, e.g.
*"Cannot delete: 3 flight schedule(s) use this airport."* The database's RESTRICT foreign keys are the final
safety net. Deleting an agent turns their reservations into direct bookings; deleting a reservation removes only
its links.

---

## 3. How the code is organised

| File | Role |
|---|---|
| `app.py` | Routes (URLs) → read the form → call validation and repository → flash a message → redirect |
| `entities.py` | One definition per screen: table, fields, search columns, delete rules, validation |
| `repository.py` | Builds SQL with `%s` placeholders (parameterized) and the multi-step transactions |
| `db.py` | Connection from `.env`, `query` / `execute` helpers, `transaction()`, friendly error messages |
| `templates/` | HTML pages (Jinja2) |

### From a click to the database (example: "Add leg" on a reservation)
1. The browser posts `other_id=57` to `/reservations/12/legs/add`.
2. `app.add_link()` checks the input is a number, that reservation 12 and leg 57 exist, and that the pair is not already linked.
3. `repository.add_link()` runs
   `INSERT INTO reservation_leg (reservation_id, leg_id) VALUES (%s, %s)` with `(12, 57)`.
4. `db.execute()` gives the SQL and the values **separately** to PyMySQL, which escapes them — so input can never change the SQL (no SQL injection).
5. MySQL checks the foreign keys and the composite primary key, then the app shows "Leg 57 linked." and reloads the page.

### Transactions
`db.transaction()` is a context manager: it starts a transaction, commits if every statement succeeds and **rolls back**
if any fails. It is used by `create_reservation_with_legs()` and `create_payment_and_link()`, where one action inserts
several related rows.

---

## 4. Known limitations
* No login/roles — any user with the URL can edit data (fine for a class demo, not for production).
* Key fields (flight number, airport code, cost key) cannot be edited; delete and re-create instead.
* Drop-down lists load all rows (fine for hundreds of rows, would need search-as-you-type for thousands).
* Shared payments show the full amount; the per-reservation split is not stored (database design limitation).
* Times are entered and shown in UTC; there is no local-time conversion.
* Calendar, airlines and aircraft types are read-only in the app (maintained through `database/seed.py`).
