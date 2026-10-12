"""Command-line exception desk.  Run:  python app.py        
                                      python app.py demo   """
import sys
import db
import exception_service as svc


def show_list(conn, **filters):
    rows = svc.list_exceptions(conn, **filters)
    if not rows:
        print("  (no exceptions)"); return
    print(f"  {'ID':<4}{'Category':<15}{'Sev':<8}{'Status':<13}{'Owner':<11}Target")
    for r in rows:
        print(f"  {r['id']:<4}{r['category']:<15}{r['severity']:<8}{r['status']:<13}"
              f"{(r['owner'] or '-'):<11}{r['order_id'] or r['sku']}")


def show_detail(conn, ex_id):
    e = next((r for r in svc.list_exceptions(conn) if r["id"] == ex_id), None)
    if not e:
        print("  Not found."); return
    print(f"\n  EX-{e['id']:03d} [{e['severity']}] {e['category']} - {e['status']}")
    print(f"  Impact: {e['impact']}")
    print(f"  Suggested owner role: {svc.CATEGORY_ROLE[e['category']]}")
    for h in svc.history(conn, ex_id):
        print(f"    {h['at']}  {h['text']}")


def staff_pick(conn):
    for s in conn.execute("SELECT * FROM staff"):
        print(f"    {s['id']}. {s['name']} ({s['role']})")
    raw = input("  Owner id (blank to keep): ").strip()
    return int(raw) if raw.isdigit() else None


def menu(conn):
    while True:
        print("\n1 Run detection  2 List  3 Detail  4 Change status  5 Edit stock  0 Quit")
        c = input("> ").strip()
        try:
            if c == "1":
                print(f"  {svc.detect(conn)} new exception(s).")
            elif c == "2":
                show_list(conn, status=input("  Status filter (blank=all): ").strip() or None)
            elif c == "3":
                show_detail(conn, int(input("  Exception id: ")))
            elif c == "4":
                i = int(input("  Exception id: "))
                to = input("  New status (Assigned/In Progress/Resolved/Escalated): ").strip()
                owner = staff_pick(conn) if to in ("Assigned", "Escalated") else None
                notes = input("  Notes: ").strip() or None if to == "Resolved" else None
                svc.transition(conn, i, to, owner, notes); print("  Updated.")
            elif c == "5":
                sku, qty = input("  SKU: ").strip(), int(input("  New quantity: "))
                conn.execute("UPDATE inventory SET qty=? WHERE sku=?", (qty, sku)); conn.commit()
            elif c == "0":
                return
        except (ValueError, svc.TransitionError) as err:
            print(f"  ! {err}")


def demo(conn):
    print("Detection:", svc.detect(conn), "exceptions created"); show_list(conn)
    print("\nRe-running detection (should add nothing):", svc.detect(conn))
    svc.transition(conn, 1, "Assigned", owner_id=1)
    svc.transition(conn, 1, "In Progress")
    for label, fn in (("resolve without notes", lambda: svc.transition(conn, 1, "Resolved")),
                      ("jump Open -> Resolved", lambda: svc.transition(conn, 2, "Resolved", notes="x"))):
        try:
            fn()
        except svc.TransitionError as err:
            print(f"Blocked ({label}): {err}")
    svc.transition(conn, 1, "Resolved", notes="Reorder placed with supplier")
    svc.transition(conn, 2, "Escalated")
    show_detail(conn, 1); show_detail(conn, 2)


if __name__ == "__main__":
    connection = db.init_db(db.connect())
    demo(connection) if sys.argv[1:] == ["demo"] else menu(connection)
