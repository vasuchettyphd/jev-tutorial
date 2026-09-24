"""Offline checks for the stress test's ground truth. No API key or network needed.

Run: python3 -m unittest test_truth   (from the experiments/ folder)
"""
import random, unittest
from refund_stress_test import truth, make_case, MESSAGES


def case(days, total, tier="standard", category="home", final_sale=False, defective=False):
    return {"days": days, "total": total, "tier": tier, "category": category,
            "final_sale": final_sale, "defective": defective}


class TruthEdges(unittest.TestCase):
    def test_last_day_of_window_is_inside(self):
        self.assertEqual(truth(case(30, 50)), "AUTO_REFUND")
        self.assertEqual(truth(case(31, 50)), "DENY")

    def test_tier_windows(self):
        for tier, days in (("silver", 45), ("gold", 60), ("platinum", 90)):
            self.assertEqual(truth(case(days, 50, tier)), "AUTO_REFUND")
            self.assertEqual(truth(case(days + 1, 50, tier)), "DENY")

    def test_electronics_overrides_tier_window(self):
        self.assertEqual(truth(case(15, 50, "gold", "electronics")), "AUTO_REFUND")
        self.assertEqual(truth(case(16, 50, "gold", "electronics")), "DENY")
        self.assertEqual(truth(case(30, 50, "platinum", "electronics")), "AUTO_REFUND")
        self.assertEqual(truth(case(31, 50, "platinum", "electronics")), "DENY")

    def test_defective_gets_365_days_everywhere(self):
        self.assertEqual(truth(case(365, 50, category="electronics", defective=True)), "AUTO_REFUND")
        self.assertEqual(truth(case(366, 50, category="electronics", defective=True)), "DENY")

    def test_final_sale(self):
        self.assertEqual(truth(case(1, 50, final_sale=True)), "DENY")
        self.assertEqual(truth(case(200, 50, final_sale=True, defective=True)), "AUTO_REFUND")
        self.assertEqual(truth(case(366, 50, final_sale=True, defective=True)), "DENY")

    def test_total_bands(self):
        self.assertEqual(truth(case(1, 99.99)), "AUTO_REFUND")
        self.assertEqual(truth(case(1, 100)), "MANAGER")
        self.assertEqual(truth(case(1, 499.99)), "MANAGER")
        self.assertEqual(truth(case(1, 500)), "FINANCE")


class Generator(unittest.TestCase):
    def test_seeded_cases_are_reproducible(self):
        a = [make_case(random.Random(7)) for _ in range(3)]
        b = [make_case(random.Random(7)) for _ in range(3)]
        self.assertEqual(a, b)

    def test_messages_match_category(self):
        rng = random.Random(1)
        for _ in range(200):
            c = make_case(rng)
            self.assertIn((c["message"], c["defective"]), MESSAGES[c["category"]])

    def test_total_edge_bucket_excludes_denials(self):
        rng = random.Random(2)
        for _ in range(500):
            c = make_case(rng)
            if c["near_total_edge"]:
                self.assertNotEqual(c["truth"], "DENY")


if __name__ == "__main__":
    unittest.main()
