"""Collection of tests for ``cli`` module."""
import random
import string
from gettext import gettext as _
from subprocess import CalledProcessError
from unittest import TestCase
from unittest.mock import Mock, patch

import sh
from click.testing import CliRunner

from cli import main
from tests import helper

CLOUD_AWS = "aws"
RPM_RESULT_FOUND = "448\n"
RPM_RESULT_NONE = "0\n"


class TestCLI(TestCase):
    """Test suite for houndigrade CLI."""

    def setUp(self):
        """Set up random fixture data for each test."""
        self.aws_image_id = f"ami-{random.randrange(10 ** 11, 10 ** 12 - 1)}"
        drive_letter = random.choice(string.ascii_lowercase)
        self.drive_path = f"./dev/xvd{drive_letter}"
        self.partition_1 = f"{self.drive_path}1"
        self.partition_2 = f"{self.drive_path}2"
        self.partition_3 = f"{self.drive_path}3"
        self.inspect_path = f"./inspect_{random.randrange(10 ** 4, 10 ** 5 - 1)}"

    def assertNoReleaseFiles(self, message, path):
        """Assert no release files found."""
        expected = f'"status": "{_("No release files found on {}".format(path))}"'
        self.assertIn(expected, message)

    def assertFoundReleaseFile(self, message, path, expect_found=True):
        """Assert RHEL is or is not found via release file."""
        self.assertFoundVia(message, "release file", path, expect_found)

    def assertFoundEnabledRepos(self, message, path, expect_found=True):
        """Assert RHEL is or is not found via enabled repos."""
        self.assertFoundVia(message, "enabled repos", path, expect_found)

    def assertFoundProductCertificate(self, message, path, expect_found=True):
        """Assert RHEL is or is not found via product certificate."""
        self.assertFoundVia(message, "product certificate", path, expect_found)

    def assertFoundSignedPackages(self, message, path, expect_found=True):
        """Assert RHEL is or is not found via signed packages."""
        self.assertFoundVia(message, "signed packages", path, expect_found)

    def assertFoundVia(self, message, what, path, expect_found):
        """Assert RHEL is or is not found via the given "what" string."""
        expected = (
            f"RHEL {'found' if expect_found else 'not found'} via {what} on: {path}"
        )
        self.assertIn(expected, message)

    def assertRhelFound(self, message, version, ami):
        """Assert RHEL is found for the ami in the message."""
        self.assertIn(f"RHEL (version {version}) found on: {ami}", message)

    def assertRhelNotFound(self, message, ami):
        """Assert RHEL is not found for the ami in the message."""
        self.assertIn(f"RHEL not found on: {ami}", message)

    def test_cli_no_options(self):
        """Test CLI output when given no options."""
        runner = CliRunner()
        result = runner.invoke(main)

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Error: Missing option '--target' / '-t'.", result.output)

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_multiple_ways(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """
        Test finding RHEL via multiple ways.

        This should verify finding RHEL in all currently know ways, which includes:

        * RHEL in at least one partition's release file(s)
        * RHEL in at least one partition's enabled yum repo(s)
        * RHEL in at least one partition's installed product certificate(s)
        * RHEL in at least one partition's RPM database
        """
        # rhel_version = "7.4"  # This is correct RHEL version
        centos_version = "7"  # This is the CentOS version on partition_2.
        # TODO FIXME Report the version *only* from a RHEL-positive partition!
        # This pre-existing bug is an unfortunate side-effect of the code near:
        # "# Note: If multiple partitions, the last one found is set."

        mock_subprocess_check_output.side_effect = [
            RPM_RESULT_FOUND,  # result for `rpm` call in partition_1
            RPM_RESULT_NONE,  # result for `rpm` call in partition_2
        ]

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)

            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_rhel_syspurpose(self.partition_1)
            helper.prepare_fs_with_yum(self.partition_1)
            helper.prepare_fs_with_rhel_product_certificate(self.partition_1)
            helper.prepare_fs_with_rpm_db(self.partition_1)

            helper.prepare_fs_centos_release(self.partition_2)
            helper.prepare_fs_with_yum(self.partition_2, include_optional=False)
            helper.prepare_fs_with_rpm_db(self.partition_2)

            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn(f'"cloud": "{CLOUD_AWS}"', result.output)
        self.assertIn(f'"{self.aws_image_id}"', result.output)

        self.assertFoundReleaseFile(result.output, self.partition_1)
        self.assertFoundEnabledRepos(result.output, self.partition_1)
        self.assertFoundProductCertificate(result.output, self.partition_1)
        self.assertFoundSignedPackages(result.output, self.partition_1)

        self.assertFoundReleaseFile(result.output, self.partition_2, False)
        self.assertFoundEnabledRepos(result.output, self.partition_2)
        self.assertFoundProductCertificate(result.output, self.partition_2, False)
        self.assertFoundSignedPackages(result.output, self.partition_2, False)

        self.assertRhelFound(result.output, centos_version, self.aws_image_id)  # FIXME
        self.assertIn(
            '{"repo": "rhel7-cdn-internal", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-extras", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-optional", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn('"role": "Red Hat Enterprise Linux Server"', result.output)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertEqual(
            results["images"][self.aws_image_id]["rhel_version"], centos_version
        )  # FIXME
        self.assertEqual(
            results["images"][self.aws_image_id]["syspurpose"]["role"],
            "Red Hat Enterprise Linux Server",
        )

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.run")
    def test_results_error_when_mount_path_does_not_exist(
        self, mock_subprocess_run, mock_describe_devices, mock_report_results
    ):
        """Test errors in the results when mount path does not exist."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        expected_error_message = _("Nothing found at path {} for {}").format(
            self.drive_path, self.aws_image_id
        )

        self.assertFalse(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn(expected_error_message, results["errors"])
        self.assertIn(self.aws_image_id, results["images"])
        image_result = results["images"][self.aws_image_id]
        self.assertFalse(image_result["rhel_found"])
        self.assertFalse(image_result["rhel_signed_packages_found"])
        self.assertFalse(image_result["rhel_product_certs_found"])
        self.assertFalse(image_result["rhel_release_files_found"])
        self.assertFalse(image_result["rhel_enabled_repos_found"])
        self.assertIsNone(image_result["rhel_version"])
        self.assertIsNone(image_result["syspurpose"])
        self.assertEqual(len(image_result["errors"]), 1)
        self.assertIn(expected_error_message, image_result["errors"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_cli_no_version_files(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test appropriate error handling when release files are missing."""
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_empty(self.partition_1)
            helper.prepare_fs_empty(self.partition_2)

            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertNoReleaseFiles(result.output, self.partition_1)
        self.assertNoReleaseFiles(result.output, self.partition_2)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """
        Test not finding RHEL via normal inspection.

        This exercises effectively the opposite cases of test_rhel_found_multiple_ways.
        This should verify not finding RHEL in all currently know ways, which includes:

        * release file(s) exist but do not have RHEL
        * release file(s) don't exist
        * yum repo(s) exist and are enabled but do not have RHEL
        * yum repo(s) exist with RHEL but are not enabled
        * no installed product certificate(s)
        * no RHEL found in the RPM database
        * rpm command fails to execute
        """
        subprocess_error = CalledProcessError(1, "rpm", stderr="rpm failed.")
        mock_subprocess_check_output.side_effect = [
            RPM_RESULT_NONE,  # result for `rpm` call in partition_1
            subprocess_error,  # result for `rpm` call in partition_2
        ]

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_centos_release(self.partition_1)
            helper.prepare_fs_with_yum(
                self.partition_1, rhel_enabled=False, include_optional=False
            )
            helper.prepare_fs_with_yum(
                self.partition_2, rhel_enabled=False, include_optional=True
            )
            helper.prepare_fs_with_rpm_db(self.partition_1)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelNotFound(result.output, self.aws_image_id)

        self.assertFoundReleaseFile(result.output, self.partition_1, False)
        self.assertFoundEnabledRepos(result.output, self.partition_1, False)
        self.assertFoundProductCertificate(result.output, self.partition_1, False)
        self.assertFoundSignedPackages(result.output, self.partition_1, False)

        self.assertNoReleaseFiles(result.output, self.partition_2)
        self.assertFoundEnabledRepos(result.output, self.partition_2, False)
        self.assertFoundProductCertificate(result.output, self.partition_2, False)
        # Skip next assert because the RPM check quietly errors out (correctly).
        # self.assertFoundSignedPackages(result.output, self.partition_2, False)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertFalse(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test finding RHEL via enabled yum repos."""
        rhel_version = None  # Because we detect RHEL without a release file.
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_yum(self.partition_1)
            helper.prepare_fs_with_yum(self.partition_2, include_optional=False)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        self.assertFoundEnabledRepos(result.output, self.partition_1)
        self.assertFoundEnabledRepos(result.output, self.partition_2)

        self.assertIn(
            '{"repo": "rhel7-cdn-internal", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-extras", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-optional", "name": "RHEL 7 - $basearch"}',
            result.output,
        )

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos_specified_dir(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test finding RHEL via enabled yum repos in custom yum repos path."""
        rhel_version = None  # Because we detect RHEL without a release file.
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_yum(self.partition_1, default_reposdir=False)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        self.assertFoundEnabledRepos(result.output, self.partition_1)

        self.assertIn(
            '{"repo": "rhel7-cdn-internal", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-extras", "name": "RHEL 7 - $basearch"}',
            result.output,
        )

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos_no_conf(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test finding RHEL via enabled yum repos without yum.conf."""
        rhel_version = None  # Because we detect RHEL without a release file.
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_yum(self.partition_1, include_yum_conf=False)
            helper.prepare_fs_with_yum(self.partition_2, include_yum_conf=False)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        self.assertFoundEnabledRepos(result.output, self.partition_1)
        self.assertFoundEnabledRepos(result.output, self.partition_2)

        self.assertIn(
            '{"repo": "rhel7-cdn-internal", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-extras", "name": "RHEL 7 - $basearch"}',
            result.output,
        )

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found_with_bad_yum_conf(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test not finding RHEL with bad yum.conf."""
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_bad_yum_conf(self.partition_1)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertNoReleaseFiles(result.output, self.partition_1)
        self.assertRhelNotFound(result.output, self.aws_image_id)
        self.assertIn("Error reading yum repo files on", result.output)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertFalse(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found_with_unreadable_release_file(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test not finding RHEL with an unreadable release file."""
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_bad_release_file(self.partition_1)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            f"Error reading release files on {self.partition_1}", result.output
        )
        self.assertRhelNotFound(result.output, self.aws_image_id)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertFalse(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])
        self.assertEqual(
            (
                f"Error reading release files on {self.partition_1}: "
                "'utf-8' codec can't decode byte 0xac in position 0: invalid start byte"
            ),
            results["images"][self.aws_image_id]["drives"][self.drive_path][
                self.partition_1
            ]["facts"]["rhel_release_files"]["status"],
        )

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_signed_package(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test finding RHEL via signed package (RHEL in RPM DB)."""
        rhel_version = None  # Because we detect RHEL without a release file.
        mock_subprocess_check_output.side_effect = [
            RPM_RESULT_FOUND,  # result for `rpm` call in partition_1
            RPM_RESULT_NONE,  # result for `rpm` call in partition_2
        ]

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_rpm_db(self.partition_1)
            helper.prepare_fs_with_rpm_db(self.partition_2)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        self.assertFoundSignedPackages(result.output, self.partition_1)
        self.assertFoundSignedPackages(result.output, self.partition_2, False)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_product_cert(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test finding RHEL via product certificate."""
        rhel_version = None  # Because we detect RHEL without a release file.
        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_with_rhel_product_certificate(self.partition_1)
            helper.prepare_fs_with_rhel_product_certificate(self.partition_2)

            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        self.assertFoundProductCertificate(result.output, self.partition_1)
        self.assertFoundProductCertificate(result.output, self.partition_2)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_release_file(
        self, mock_subprocess_check_output, mock_describe_devices, mock_report_results
    ):
        """Test finding RHEL via etc release file."""
        rhel_version = "7.4"

        mock_subprocess_check_output.return_value = RPM_RESULT_NONE

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_centos_release(self.partition_2)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        self.assertFoundReleaseFile(result.output, self.partition_1, True)
        self.assertFoundReleaseFile(result.output, self.partition_2, False)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertTrue(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertTrue(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertEqual(results["images"][self.aws_image_id]["rhel_version"], "7.4")

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    def test_no_rpm_db_early_return(self, mock_describe_devices, mock_report_results):
        """Test error handling when RPM DB does not exist."""
        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_empty(self.partition_1)
            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 0)
        self.assertFalse(results["images"][self.aws_image_id]["rhel_found"])
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_signed_packages_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_enabled_repos_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_product_certs_found"]
        )
        self.assertFalse(
            results["images"][self.aws_image_id]["rhel_release_files_found"]
        )
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])
        self.assertEqual(
            _("RPM DB directory on {0} has no data for {1}").format(
                self.partition_1, self.aws_image_id
            ),
            results["images"][self.aws_image_id]["drives"][self.drive_path][
                self.partition_1
            ]["facts"]["rhel_signed_packages"]["status"],
        )

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.glob.glob")
    @patch("cli.sh.mount")
    def test_failed_mount(
        self, mock_sh_mount, mock_glob_glob, mock_describe_devices, mock_report_results
    ):
        """Test error handling when mount fails."""
        error_message = "failed"
        e = sh.ErrorReturnCode_1(
            full_cmd="mount", stdout=Mock(), stderr=Mock(), truncate=False
        )
        mock_sh_mount.mount.side_effect = e

        def mock_glob_side_effect(pattern):
            return [self.partition_1]

        mock_glob_glob.side_effect = mock_glob_side_effect

        runner = CliRunner()
        with runner.isolated_filesystem():
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_empty(self.partition_1)
            result = runner.invoke(main, ["-t", self.aws_image_id, self.drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertEqual(result.exit_code, 0)

        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn(error_message, results["errors"][0])
        self.assertIn(self.aws_image_id, results["images"])
        self.assertEqual(len(results["images"][self.aws_image_id]["errors"]), 1)
        self.assertIn(error_message, results["images"][self.aws_image_id]["errors"][0])
