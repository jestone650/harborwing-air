"""
HarborWing Air - CRUD application (Flask + PyMySQL)
Start:  python app.py   then open http://127.0.0.1:5000
"""
import os

import pymysql
from flask import Flask, abort, flash, redirect, render_template, request, url_for

import repository as repo
from db import close_connection, friendly_error, query, scalar
from entities import ENTITIES, PAYMENT_STATUS, RESERVATION_STATUS, TICKET_TYPES, TRAVEL_CLASSES, options, parse_form

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")
app.teardown_appcontext(close_connection)


@app.template_filter("inputval")
def inputval(value, ftype="text"):
    """Format a stored value for an HTML input."""
    if value is None:
        return ""
    if ftype == "datetime" and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@app.template_filter("show")
def show(value):
    """Format a value for display in tables."""
    if value is None:
        return "—"
    if hasattr(value, "strftime") and hasattr(value, "hour"):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return value


@app.context_processor
def helpers():
    def key_url(endpoint, entity, row):
        return url_for(endpoint, name=entity.name, **{k: row[k] for k in entity.keys})
    return dict(key_url=key_url, nav=ENTITIES)


def get_entity(name):
    entity = ENTITIES.get(name)
    if not entity:
        abort(404)
    return entity


def key_from_args(entity):
    keyvals = {k: request.args.get(k, "").strip() for k in entity.keys}
    if not all(keyvals.values()):
        abort(400, "Missing record key.")
    return keyvals


def form_context(entity, row=None, editing=False):
    """Field list + drop-down options for form.html."""
    choices = {}
    for f in entity.editable:
        if f.type == "fk":
            choices[f.name] = options(f.fk)
        elif f.type == "choice":
            choices[f.name] = f.choices
    return dict(entity=entity, row=row or {}, editing=editing, choices=choices)


@app.errorhandler(pymysql.MySQLError)
def database_error(exc):
    return render_template("error.html", message=friendly_error(exc)), 500


@app.errorhandler(404)
def not_found(exc):
    return render_template("error.html", message="Record or page not found."), 404


@app.errorhandler(400)
def bad_request(exc):
    return render_template("error.html", message=exc.description), 400


@app.route("/")
def home():
    counts = {e.title: scalar(f"SELECT COUNT(*) FROM {e.table}") for e in ENTITIES.values()}
    return render_template("home.html", counts=counts)


# ---------------------------------------------------------------------------
# Generic CRUD for the 8 entities
# ---------------------------------------------------------------------------
@app.route("/e/<name>")
def list_view(name):
    entity = get_entity(name)
    search = request.args.get("q", "").strip()
    filter_value = request.args.get("f", "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    rows, total = repo.list_rows(entity, search, filter_value, page)
    return render_template("list.html", entity=entity, rows=rows, total=total, q=search, f=filter_value,
                           page=page, pages=max((total - 1) // repo.PAGE_SIZE + 1, 1))


@app.route("/e/<name>/new", methods=["GET", "POST"])
def create(name):
    entity = get_entity(name)
    ctx = form_context(entity)
    if name == "reservations":
        ctx["legs"] = options("leg")
    if request.method == "POST":
        values, errors = parse_form(entity, request.form)
        if not errors and entity.check:
            errors += entity.check(values, None)
        if errors:
            for e in errors:
                flash(e, "error")
            ctx["row"] = request.form
            return render_template("form.html", **ctx), 422
        try:
            if name == "reservations":
                leg_ids = [int(x) for x in request.form.getlist("initial_legs") if x.isdigit()]
                new_id = repo.create_reservation_with_legs(values, leg_ids)
                flash(f"Reservation {new_id} created with {len(leg_ids)} leg(s).", "success")
                return redirect(url_for("reservation_view", reservation_id=new_id))
            new_id = repo.insert(entity, values)
            flash(f"{entity.title[:-1]} saved.", "success")
            if name == "passengers":
                flash(f"New passenger ID is {new_id}.", "success")
            return redirect(url_for("list_view", name=name))
        except pymysql.MySQLError as exc:
            flash(friendly_error(exc), "error")
            ctx["row"] = request.form
            return render_template("form.html", **ctx), 422
    return render_template("form.html", **ctx)


@app.route("/e/<name>/edit", methods=["GET", "POST"])
def edit(name):
    entity = get_entity(name)
    keyvals = key_from_args(entity)
    row = repo.get_row(entity, keyvals)
    if not row:
        abort(404)
    ctx = form_context(entity, row, editing=True)
    if request.method == "POST":
        values, errors = parse_form(entity, request.form, editing=True)
        if not errors and entity.check:
            errors += entity.check({**row, **values}, keyvals)
        if not errors:
            try:
                repo.update(entity, keyvals, values)
                flash(f"{entity.title[:-1]} updated.", "success")
                if name == "reservations":
                    return redirect(url_for("reservation_view", reservation_id=keyvals["reservation_id"]))
                return redirect(url_for("list_view", name=name))
            except pymysql.MySQLError as exc:
                errors.append(friendly_error(exc))
        for e in errors:
            flash(e, "error")
        ctx["row"] = {**row, **request.form}
        return render_template("form.html", **ctx), 422
    return render_template("form.html", **ctx)


@app.route("/e/<name>/delete", methods=["GET", "POST"])
def delete(name):
    entity = get_entity(name)
    keyvals = key_from_args(entity)
    row = repo.get_row(entity, keyvals)
    if not row:
        abort(404)
    reasons = repo.blocking_dependents(entity, keyvals)
    if request.method == "POST":
        if reasons:
            flash("Cannot delete: " + "; ".join(reasons) + ".", "error")
        else:
            try:
                repo.delete(entity, keyvals)
                flash(f"{entity.title[:-1]} deleted.", "success")
                return redirect(url_for("list_view", name=name))
            except pymysql.MySQLError as exc:  # database is the final safety net
                flash(friendly_error(exc), "error")
    return render_template("confirm_delete.html", entity=entity, row=row, keyvals=keyvals, reasons=reasons)


# ---------------------------------------------------------------------------
# Reservation detail + link management
# ---------------------------------------------------------------------------
@app.route("/reservations/<int:reservation_id>")
def reservation_view(reservation_id):
    detail = repo.reservation_detail(reservation_id)
    if not detail:
        abort(404)
    linked_legs = {l["leg_id"] for l in detail["legs"]}
    linked_pay = {p["payment_id"] for p in detail["payments"]}
    return render_template(
        "reservation.html", **detail,
        leg_options=[o for o in options("leg") if int(o[0]) not in linked_legs],
        payment_options=[o for o in options("payment") if int(o[0]) not in linked_pay],
        payment_status=PAYMENT_STATUS, codes=dict(RESERVATION_STATUS + TICKET_TYPES + TRAVEL_CLASSES))


LINKS = {"legs": ("reservation_leg", "leg_id", "flight_leg"),
         "payments": ("reservation_payment", "payment_id", "payment")}


@app.post("/reservations/<int:reservation_id>/<kind>/add")
def add_link(reservation_id, kind):
    if kind not in LINKS:
        abort(404)
    table, col, parent = LINKS[kind]
    other = request.form.get("other_id", "")
    if not other.isdigit():
        flash("Choose a record to link.", "error")
    elif not repo.reservation_detail(reservation_id):
        abort(404)
    elif not scalar(f"SELECT COUNT(*) FROM {parent} WHERE {col} = %s", (other,)):
        flash(f"{kind[:-1].capitalize()} {other} does not exist.", "error")
    elif repo.link_exists(table, col, reservation_id, other):
        flash(f"{kind[:-1].capitalize()} {other} is already linked to this reservation.", "error")
    else:
        try:
            repo.add_link(table, col, reservation_id, other)
            flash(f"{kind[:-1].capitalize()} {other} linked.", "success")
        except pymysql.MySQLError as exc:
            flash(friendly_error(exc), "error")
    return redirect(url_for("reservation_view", reservation_id=reservation_id))


@app.post("/reservations/<int:reservation_id>/<kind>/<int:other_id>/remove")
def remove_link(reservation_id, kind, other_id):
    if kind not in LINKS:
        abort(404)
    table, col, _ = LINKS[kind]
    if repo.remove_link(table, col, reservation_id, other_id):
        flash(f"Link removed. {kind[:-1].capitalize()} {other_id} itself was NOT deleted.", "success")
    else:
        flash("That link did not exist.", "error")
    return redirect(url_for("reservation_view", reservation_id=reservation_id))


@app.post("/reservations/<int:reservation_id>/payments/create")
def create_payment_for_reservation(reservation_id):
    if not repo.reservation_detail(reservation_id):
        abort(404)
    values, errors = parse_form(ENTITIES["payments"], request.form)
    extra = [int(x) for x in request.form.get("also_reservations", "").replace(" ", "").split(",") if x.isdigit()]
    for rid in extra:
        if not scalar("SELECT COUNT(*) FROM reservation WHERE reservation_id = %s", (rid,)):
            errors.append(f"Reservation {rid} does not exist.")
    if errors:
        for e in errors:
            flash(e, "error")
    else:
        try:
            pid = repo.create_payment_and_link(values, sorted({reservation_id, *extra}))
            flash(f"Payment {pid} created and linked.", "success")
        except pymysql.MySQLError as exc:
            flash(friendly_error(exc) + " Nothing was saved (transaction rolled back).", "error")
    return redirect(url_for("reservation_view", reservation_id=reservation_id))


# ---------------------------------------------------------------------------
# Calendar and reference data (read-only; maintained by the seed script)
# ---------------------------------------------------------------------------
@app.route("/reference")
def reference():
    return render_template(
        "reference.html",
        airlines=query("SELECT * FROM airline ORDER BY airline_code"),
        aircraft=query("SELECT * FROM aircraft_type ORDER BY aircraft_type_code"),
        code_lists={"Reservation status": RESERVATION_STATUS, "Ticket type": TICKET_TYPES,
                    "Travel class": TRAVEL_CLASSES, "Payment status": PAYMENT_STATUS})


@app.route("/calendar")
def calendar():
    month = request.args.get("month", "2026-10")
    if len(month) != 7 or month[4] != "-" or not (month[:4] + month[5:]).isdigit():
        flash("Month must look like 2026-10.", "error")
        month = "2026-10"
    days = query("SELECT * FROM calendar_date WHERE DATE_FORMAT(day_date, '%%Y-%%m') = %s ORDER BY day_date",
                 (month,))
    return render_template("calendar.html", days=days, month=month)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1",
            host=os.getenv("APP_HOST", "127.0.0.1"), port=int(os.getenv("APP_PORT", "5000")))
