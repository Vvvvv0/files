import sqlite3
from datetime import datetime

NOW = datetime(2026, 10, 12, 9, 0)      # simulated clock so results are repeatable
DELAY_MARGIN_H = 24
OPEN_ORDER_STATUSES = ("Pending", "Customs On Hold")
NEXT = {
    "Open": ["Assigned", "Escalated"],
    "Assigned": ["In Progress", "Escalated"],
    "In Progress": ["Resolved", "Escalated"],
    "Escalated": ["Assigned", "In Progress"],
    "Resolved": [],
}
CATEGORY_ROLE = {"Low inventory": "Inventory staff", "Delayed order": "Customer service",
                 "Data quality": "System administrator"}


class TransitionError(Exception):
    """Raised when a status change breaks a lifecycle rule."""


def _stamp():
    return datetime.now().strftime("%d %b %H:%M")


def _log(conn, ex_id, text):
    conn.execute("INSERT INTO exception_history (exception_id, at, text) VALUES (?,?,?)",
                 (ex_id, _stamp(), text))


def _add(conn, key, category, severity, order_id, sku, impact):
    try:
        cur = conn.execute(
            "INSERT INTO exceptions (key, category, severity, detected_at, order_id, sku, impact)"
            " VALUES (?,?,?,?,?,?,?)", (key, category, severity, _stamp(), order_id, sku, impact))
    except sqlite3.IntegrityError:          # same problem already tracked
        return 0
    _log(conn, cur.lastrowid, "Detected by rule check")
    return 1


def detect(conn, now=NOW):
    """Run all rules; return how many NEW exceptions were created."""
    created = 0
    marks = ",".join("?" * len(OPEN_ORDER_STATUSES))
    for i in conn.execute("SELECT * FROM inventory WHERE qty < threshold").fetchall():
        open_orders = conn.execute(
            f"SELECT id, qty FROM orders WHERE sku=? AND status IN ({marks})",
            (i["sku"], *OPEN_ORDER_STATUSES)).fetchall()
        need = sum(o["qty"] for o in open_orders)
        affected = (f"{len(open_orders)} open order(s) need {need} units: "
                    + ", ".join(o["id"] for o in open_orders) + ".") if open_orders \
            else "No open orders use it yet."
        sev = "High" if i["qty"] < i["threshold"] / 2 else "Medium"
        created += _add(conn, f"LOW:{i['sku']}", "Low inventory", sev, None, i["sku"],
                        f"{i['name']} has {i['qty']} units against a minimum of "
                        f"{i['threshold']}. {affected}")
    containers = {r["id"] for r in conn.execute("SELECT id FROM containers")}
    for o in conn.execute("SELECT * FROM orders").fetchall():
        if o["status"] in OPEN_ORDER_STATUSES:
            late_h = (now - datetime.fromisoformat(o["expected_departure"])).total_seconds() / 3600
            if late_h > DELAY_MARGIN_H:
                mates = [r["id"] for r in conn.execute(
                    "SELECT id FROM orders WHERE container_id=? AND id!=? AND status!='Complete'",
                    (o["container_id"], o["id"]))]
                extra = f" Same container also carries {', '.join(mates)}." if mates else ""
                created += _add(conn, f"DEL:{o['id']}", "Delayed order",
                                "High" if late_h > 72 else "Medium", o["id"], o["sku"],
                                f"{o['id']} is {round(late_h)} h past expected departure "
                                f"({o['status']}). It holds {o['qty']} x {o['sku']} in "
                                f"container {o['container_id']}.{extra}")
        missing = [n for n, v in (("customer", o["customer"]), ("SKU", o["sku"]),
                                  ("quantity", o["qty"])) if not v]
        if missing:
            created += _add(conn, f"DQ:{o['id']}:missing", "Data quality", "Medium", o["id"],
                            o["sku"], f"{o['id']} is missing: {', '.join(missing)}.")
        if o["container_id"] and o["container_id"] not in containers:
            created += _add(conn, f"DQ:{o['id']}:container", "Data quality", "Medium", o["id"],
                            o["sku"], f"{o['id']} points to unknown container "
                            f"{o['container_id']}; container-to-SKU trace is broken.")
    conn.commit()
    return created


def list_exceptions(conn, status=None, category=None):
    sql = ("SELECT e.*, s.name AS owner FROM exceptions e "
           "LEFT JOIN staff s ON s.id = e.owner_id WHERE 1=1")
    args = []
    if status:
        sql += " AND e.status=?"; args.append(status)
    if category:
        sql += " AND e.category=?"; args.append(category)
    return conn.execute(sql + " ORDER BY e.id", args).fetchall()


def history(conn, ex_id):
    return conn.execute("SELECT at, text FROM exception_history WHERE exception_id=? ORDER BY id",
                        (ex_id,)).fetchall()


def transition(conn, ex_id, to, owner_id=None, notes=None):
    """Move an exception to a new status, enforcing the lifecycle rules."""
    e = conn.execute("SELECT * FROM exceptions WHERE id=?", (ex_id,)).fetchone()
    if e is None:
        raise TransitionError(f"Exception {ex_id} does not exist.")
    if to not in NEXT[e["status"]]:
        raise TransitionError(f"Cannot move from {e['status']} to {to}.")
    owner = owner_id if owner_id is not None else e["owner_id"]
    notes = notes if notes is not None else (e["notes"] or "")
    if to == "Assigned" and owner is None:
        raise TransitionError("Choose an owner before assigning.")
    if to == "Resolved" and not notes.strip():
        raise TransitionError("Add resolution notes before resolving.")
    if to == "Escalated":
        owner = conn.execute("SELECT id FROM staff WHERE role='Operations manager'").fetchone()["id"]
    conn.execute("UPDATE exceptions SET status=?, owner_id=?, notes=? WHERE id=?",
                 (to, owner, notes, ex_id))
    who = conn.execute("SELECT name FROM staff WHERE id=?", (owner,)).fetchone()
    _log(conn, ex_id, f"{e['status']} -> {to}" + (f" ({who['name']})" if who else ""))
    conn.commit()
