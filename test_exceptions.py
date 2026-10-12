"""Test cases. Run: python -m unittest -v"""
import unittest
import db
import exception_service as svc


class ExceptionTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.init_db(db.connect())

    def keys(self):
        return {r["key"] for r in self.conn.execute("SELECT key FROM exceptions")}

    def test_detects_all_three_categories(self):
        self.assertEqual(svc.detect(self.conn), 7)
        cats = {r["category"] for r in svc.list_exceptions(self.conn)}
        self.assertEqual(cats, {"Low inventory", "Delayed order", "Data quality"})

    def test_expected_exceptions_present(self):
        svc.detect(self.conn)
        for k in ("LOW:SKU-102", "DEL:O-2001", "DQ:O-2005:container", "DQ:O-2006:missing"):
            self.assertIn(k, self.keys())

    def test_detection_is_idempotent(self):
        svc.detect(self.conn)
        self.assertEqual(svc.detect(self.conn), 0)

    def test_healthy_stock_not_flagged(self):
        svc.detect(self.conn)
        self.assertNotIn("LOW:SKU-101", self.keys())

    def test_stock_drop_creates_new_exception(self):
        svc.detect(self.conn)
        self.conn.execute("UPDATE inventory SET qty=5 WHERE sku='SKU-104'")
        self.assertEqual(svc.detect(self.conn), 1)

    def test_severity_rules(self):
        svc.detect(self.conn)
        sev = {r["key"]: r["severity"] for r in svc.list_exceptions(self.conn)}
        self.assertEqual(sev["LOW:SKU-106"], "High")      # 9 < 25/2
        self.assertEqual(sev["DEL:O-2001"], "Medium")     # 71 h late

    def test_long_delay_is_high_severity(self):
        self.conn.execute("UPDATE orders SET expected_departure='2026-10-01T10:00' WHERE id='O-2001'")
        svc.detect(self.conn)
        sev = {r["key"]: r["severity"] for r in svc.list_exceptions(self.conn)}
        self.assertEqual(sev["DEL:O-2001"], "High")

    def test_on_time_order_not_flagged(self):
        svc.detect(self.conn)
        self.assertNotIn("DEL:O-2004", self.keys())       # only 17 h late, inside margin

    def test_valid_lifecycle(self):
        svc.detect(self.conn)
        svc.transition(self.conn, 1, "Assigned", owner_id=1)
        svc.transition(self.conn, 1, "In Progress")
        svc.transition(self.conn, 1, "Resolved", notes="Fixed")
        self.assertEqual(svc.list_exceptions(self.conn, status="Resolved")[0]["id"], 1)

    def test_invalid_jump_rejected(self):
        svc.detect(self.conn)
        with self.assertRaises(svc.TransitionError):
            svc.transition(self.conn, 1, "Resolved", notes="x")

    def test_assign_requires_owner(self):
        svc.detect(self.conn)
        with self.assertRaises(svc.TransitionError):
            svc.transition(self.conn, 1, "Assigned")

    def test_resolve_requires_notes(self):
        svc.detect(self.conn)
        svc.transition(self.conn, 1, "Assigned", owner_id=1)
        svc.transition(self.conn, 1, "In Progress")
        with self.assertRaises(svc.TransitionError):
            svc.transition(self.conn, 1, "Resolved")

    def test_escalation_goes_to_manager(self):
        svc.detect(self.conn)
        svc.transition(self.conn, 1, "Escalated")
        self.assertEqual(svc.list_exceptions(self.conn)[0]["owner"], "Dana Cho")

    def test_history_is_logged(self):
        svc.detect(self.conn)
        svc.transition(self.conn, 1, "Assigned", owner_id=2)
        self.assertEqual(len(svc.history(self.conn, 1)), 2)


if __name__ == "__main__":
    unittest.main()
