import unittest
from ircrobots import glob

class GlobTestCollapse(unittest.TestCase):
    def test(self):
        c1 = glob.collapse("**?*")
        self.assertEqual(c1, "?*")

        c2 = glob.collapse("a**?a*")
        self.assertEqual(c2, "a?*a*")

        c3 = glob.collapse("?*?*?*?*a")
        self.assertEqual(c3, "????*a")

        c4 = glob.collapse("a*?*a?**")
        self.assertEqual(c4, "a?*a?*")
