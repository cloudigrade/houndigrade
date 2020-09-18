"""Collection of tests for ``tests.helper`` module."""

from unittest import TestCase

from click.testing import CliRunner

from tests import helper


class TestHelper(TestCase):
    """Test suite for houndigrade's "tests.helper" module."""

    def test_safety_check_path(self):
        """Test happy path for safety_check_path."""
        expected_common = "./some/path"
        some_path = "./some/path/nested/below"

        runner = CliRunner()
        with runner.isolated_filesystem():
            helper.safety_check_path(some_path, expected_common)

    def test_safety_check_path_not_common_path(self):
        """Test safety_check_path raises ValueError if some_path not in common_path."""
        expected_common = "./not/in/here"
        some_path = "./some/path/nested/below"

        runner = CliRunner()
        with runner.isolated_filesystem(), self.assertRaises(ValueError) as e:
            helper.safety_check_path(some_path, expected_common)
        self.assertIn("some_path is not in expected_common", str(e.exception))

    def test_safety_check_path_not_in_tempdir(self):
        """Test safety_check_path raises ValueError if specified path is not in temp."""
        expected_common = "./some/path"
        some_path = "./some/path/nested/below"

        with self.assertRaises(ValueError) as e:
            helper.safety_check_path(some_path, expected_common)
        self.assertIn("some_path is not in tempdir", str(e.exception))
