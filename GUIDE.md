# HarborWing Air — Step-by-Step Guide (Part 1 + Part 2)

Follow these steps in order. Commands are for **Windows** (macOS/Linux differences are noted).
Everything you need to write is already in this folder — you mostly install, run, record and submit.

```
harborwing/
├── GUIDE.md            <- this guide
├── README.md
├── .gitignore          <- keeps .env (passwords) out of GitHub
├── database/           <- PART 1 (Midterm Drill)
│   ├── schema.sql  seed.py  queries.sql  row_counts.sql
│   ├── requirements.txt  .env.example  README.md
└── application/        <- PART 2 (CRUD app)
    ├── app.py  db.py  entities.py  repository.py
    ├── templates/  static/
    ├── requirements.txt  .env.example  README.md
```

---

## PART 0 — Install the tools (once)

1. **MySQL Server 8** and **MySQL Workbench 8**
   - Download *MySQL Installer for Windows* from dev.mysql.com/downloads/installer.
   - Choose **Custom** → add *MySQL Server 8.x* and *MySQL Workbench 8.x*.
   - When asked, set a **root password** and write it down. Keep port **3306**.
2. **Python 3.10 or newer** from python.org → on the first screen tick **"Add python.exe to PATH"**.
3. **Git** from git-scm.com, and a **GitHub** account.
4. Check in Command Prompt:
   ```
   python --version
   git --version
   ```

---

## PART 1 — Midterm Drill: the database

### Step 1 — Put the project somewhere simple
Unzip `harborwing` to e.g. `C:\IT8\harborwing`. Open Command Prompt there:
```
cd C:\IT8\harborwing\database
```

### Step 2 — Create a virtual environment and install packages
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
(macOS/Linux: `source .venv/bin/activate`.) You should now see `(.venv)` at the start of the line.

### Step 3 — Add your MySQL password
```
copy .env.example .env
notepad .env
```
Change `DB_PASSWORD=change_me` to your real root password. Save. **Never upload `.env`** (`.gitignore` already blocks it).

### Step 4 — Create and fill the database
```
python seed.py
```
This runs `schema.sql` (drops + creates the `harborwing` database), generates the fake data with a fixed seed and inserts it.
At the end you see a row-count table — every table must show **50 or more**.

> Run it again anytime to **reset** — you'll get exactly the same data.
> Error `Access denied` → wrong password in `.env`. Error `Can't connect` → MySQL service is not running
> (Windows: Services → MySQL80 → Start).

### Step 5 — Make the EER diagram in MySQL Workbench
1. Open Workbench → click your **Local instance** → log in.
2. Menu **Database → Reverse Engineer…** → Next → (password) → Next.
3. Tick only **harborwing** → Next → Next → Execute → Finish.
   Workbench draws the EER diagram with all 13 tables and relationship lines.
4. Drag tables so the lines are readable (suggestion: passenger/agent left, reservation middle, linking tables
   between reservation and payment/flight_leg, schedule/airport/cost right).
5. **File → Save Model As…** → save as `database\harborwing.mwb`.
6. **File → Export → Export as PNG…** → save as `database\harborwing_eer.png` (or *Export as PDF*).

### Step 6 — Run the SQL evidence in Workbench
1. In the Workbench SQL tab: **File → Open SQL Script** → `row_counts.sql` → click the ⚡ (Execute) button.
   Take a screenshot — this is your "50 rows per table" evidence.
2. Open `queries.sql` → execute. You get results for:
   - Q1 reservation with passenger, agent, payment totals and legs (no inflated totals)
   - Q2 reservations that use a leg
   - Q3 payments linked to a reservation
   - Q4 the flight cost for a flight + aircraft type + date
   - extra evidence: reservations with several payments and legs, shared payments, direct vs agent, cost periods
   Change `SET @reservation_id = 1;` to another number to try other reservations.

### Step 7 — Read `database/README.md` before recording
It already explains everything the drill asks: purpose of each table, relationships, why two linking tables,
why scheduled/actual times are separate, why flight cost has a composite key, advantages, trade-offs,
the four limitations, deletion rules and the flight-number assumption. Put your name/section at the top.

### Step 8 — Upload to GitHub
1. On github.com click **New repository** → name `harborwing-air` → **Create** (leave it empty).
2. In Command Prompt:
   ```
   cd C:\IT8\harborwing
   git init
   git add .
   git status
   ```
   Check that **`.env` is NOT in the list** and `.mwb` + `.png` ARE in the list.
   ```
   git commit -m "Midterm drill: HarborWing database"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/harborwing-air.git
   git push -u origin main
   ```
3. Copy the commit ID (`git log --oneline -1`) — Part 2's README must mention the database version you used.

### Step 9 — Record Video 1 (face visible) — suggested script (~6–8 min)
1. **Intro (20 s):** "I'm ___, this is the HarborWing Air reservation database for IT8."
2. **Problem (30 s):** the spreadsheet problems → how each is fixed (airport codes table, linking tables,
   separate scheduled/actual times, cost history, passenger stored once).
3. **Diagram (2 min):** show the EER diagram. Walk through: passenger 1–many reservation; agent optional;
   reservation ↔ payment and reservation ↔ leg via linking tables (composite keys stop duplicates);
   schedule → legs; schedule/leg → two airport FKs; flight_cost composite key + two FKs to calendar_date.
4. **Constraints (1 min):** open `schema.sql`, point at the CHECKs (party > 0, amount > 0, origin ≠ destination,
   valid_to ≥ valid_from) and the deletion rules comment at the top.
5. **Seed script (1 min):** show `seed.py` — fixed `SEED`, Faker, parents before children, shared payments,
   then run `python seed.py` live.
6. **Evidence (1 min):** run `row_counts.sql` (all ≥ 50), then `queries.sql` Q1–Q4. For Q1, explain why the
   subqueries prevent inflated payment totals.
7. **Limitations (40 s):** shared payment split unknown, party members not stored, joins needed, cost-overlap policy,
   flight number assumption.

---

## PART 2 — The CRUD application

### Step 10 — Install the app
```
cd C:\IT8\harborwing\application
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env
```
Set `DB_PASSWORD` to your MySQL password (same database `harborwing` from Part 1). Save.

### Step 11 — Start it
```
python app.py
```
Open **http://127.0.0.1:5000** in your browser. The home page shows record counts — if you see them, the
connection works. (If you see "Cannot connect to the database", fix `.env` and restart.) Stop with **Ctrl + C**.

### Step 12 — Practise the required demonstration (do it once before recording)
| # | Required action | Where to click |
|---|---|---|
| 1 | Create a passenger | **Passengers → + New** → fill the form → Save (note the new ID shown) |
| 2 | Create a reservation for that passenger | **Reservations → + New** → pick your passenger, status CONF, ticket MULTI, class ECON, party 2 → Save |
| 3 | Add two flight legs | On the reservation page, **Flight legs** box → choose a leg → *Add leg*; repeat for a second leg (tip: pick a leg whose origin is the first leg's destination) |
| 4 | Create and link a payment | **Payments** box → *Create a new payment and link it* → status PAID, today's date, amount 5000 → *Create & link* |
| 5 | View the complete reservation | You're already on it: passenger, agent, legs and payments in one page |
| 6 | Update a record | Click **Edit** → change party size to 3 → Save (success message) |
| 7 | Remove a link without deleting | Click **Remove link** next to one leg → message says the leg itself was NOT deleted → open **Flight legs**, search the leg ID, it's still there |
| 8 | Safely delete an eligible record | **Airports → + New** → code `ZZZ`, any name/location → Save → find it → **Delete → Yes, delete** (allowed because nothing uses it) |
| 9 | Invalid operation + error handling | Any of: **Airports** → Delete a used airport → "cannot be deleted because N flight schedule(s) use this airport"; add the **same leg twice** → "already linked"; new schedule with **same origin and destination** → "must be different"; payment amount **0** → "must be greater than 0" |

### Step 13 — Update the README and push
1. In `application/README.md`, replace "Use the same commit…" with your Part 1 commit ID and the GitHub link.
2. Push:
   ```
   cd C:\IT8\harborwing
   git add .
   git commit -m "Project 2: CRUD application"
   git push
   ```

### Step 14 — Record Video 2 (face visible) — suggested script (~6–8 min)
1. **Intro (20 s)** and show the repo structure (database/ and application/).
2. **Setup (1 min):** show `.env.example` (no secrets), explain `.env` is git-ignored, run `python app.py`.
3. **Demo (3–4 min):** steps 1–9 of the table above.
4. **Code walk-through (2 min):** follow "Add leg":
   `templates/reservation.html` form → `app.py add_link()` (validation, duplicate check) →
   `repository.add_link()` (`INSERT … VALUES (%s, %s)`) → `db.execute()` (parameterized). Then show
   `db.transaction()` and `create_payment_and_link()` — commit or rollback together.
5. **Integrity (40 s):** show `repository.blocking_dependents()` + the RESTRICT foreign keys = safe deletes.
6. **Limitations (30 s):** from `application/README.md`.

---

## Final checklist
- [ ] `database/harborwing.mwb` and `database/harborwing_eer.png` (or .pdf) are in GitHub
- [ ] `schema.sql`, `seed.py`, `requirements.txt`, `queries.sql`, `row_counts.sql`, README in `database/`
- [ ] Row counts screenshot/video shows every table ≥ 50
- [ ] Application source, `requirements.txt`, `.env.example`, README in `application/`
- [ ] **No `.env` file and no real passwords** in GitHub
- [ ] Both READMEs link to each other; Part 2 README states the database commit used
- [ ] Two videos (one per project), face visible
