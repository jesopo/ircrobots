import unittest
from ircrobots import glob

class GlobTestCollapse(unittest.TestCase):
    def test(self):
        c1 = glob._collapse("**?*")
        self.assertEqual(c1, "?*")

        c2 = glob._collapse("a**?a*")
        self.assertEqual(c2, "a?*a*")

        c3 = glob._collapse("?*?*?*?*a")
        self.assertEqual(c3, "????*a")

        c4 = glob._collapse("a*?*a?**")
        self.assertEqual(c4, "a?*a?*")
