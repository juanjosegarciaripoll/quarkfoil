import unittest

from scientific_slides.bibliography import trim_bibliography


class BibliographyTests(unittest.TestCase):
    def test_nested_values_comments_and_dependency_fields(self) -> None:
        source = '''% @misc{fake, title={Commented out}}
@article{used,
  title = {A "quote and {nested braces}, crossref={unrelated}},
  note = "An escaped \\"quote\\" and {braces}",
  xdata = {data, more},
}
@misc{data, title={Data}}
@misc{more, xref="parent"}
@book{parent, title={Parent}}
@misc{unrelated, title={Unused}}
'''
        result = trim_bibliography(source, {"used"})
        self.assertIn('@article{used,', result)
        self.assertIn('@misc{data,', result)
        self.assertIn('@misc{more,', result)
        self.assertIn('@book{parent,', result)
        self.assertNotIn('@misc{unrelated,', result)
        self.assertIn('% @misc{fake,', result)

    def test_keys_are_case_sensitive(self) -> None:
        source = '@misc{Key, title={Yes}}\n@misc{key, title={No}}'
        self.assertEqual(trim_bibliography(source, {"Key"}), '@misc{Key, title={Yes}}\n')
