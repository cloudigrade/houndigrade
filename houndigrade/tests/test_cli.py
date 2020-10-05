"""Collection of tests for ``cli`` module."""
import random
import string
from gettext import gettext as _
from subprocess import CalledProcessError
from unittest import TestCase
from unittest.mock import patch

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

    def assertReportResultsStructure(
        self, results, image_ids=None, error_messages=None
    ):
        """Assert the high-level structures of the report results are correct."""
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)

        actual_errors_count = len(results["errors"])
        expected_errors_count = len(error_messages) if error_messages else 0
        self.assertEqual(
            actual_errors_count,
            expected_errors_count,
            f"Expected {expected_errors_count} errors but found {actual_errors_count}",
        )
        if error_messages:
            self.assertListEqual(sorted(results["errors"]), sorted(error_messages))

        actual_images_count = len(results["images"])
        expected_images_count = len(list(results["images"].keys())) if image_ids else 0
        self.assertEqual(
            actual_images_count,
            expected_images_count,
            f"Expected {expected_images_count} images but found {actual_images_count}",
        )
        if image_ids:
            self.assertListEqual(sorted(results["images"]), sorted(image_ids))

    def assertReportResultsImageDetails(
        self,
        results,
        image_id,
        rhel_found=True,
        rhel_signed_packages_found=True,
        rhel_enabled_repos_found=True,
        rhel_product_certs_found=True,
        rhel_release_files_found=True,
        rhel_version=None,
        error_messages=None,
        syspurpose_role=None,
    ):
        """Assert the report results for the given image are correct."""
        details = results["images"][image_id]

        if rhel_found:
            self.assertTrue(details["rhel_found"])
        else:
            self.assertFalse(details["rhel_found"])

        if rhel_signed_packages_found:
            self.assertTrue(details["rhel_signed_packages_found"])
        else:
            self.assertFalse(details["rhel_signed_packages_found"])

        if rhel_enabled_repos_found:
            self.assertTrue(details["rhel_enabled_repos_found"])
        else:
            self.assertFalse(details["rhel_enabled_repos_found"])

        if rhel_product_certs_found:
            self.assertTrue(details["rhel_product_certs_found"])
        else:
            self.assertFalse(details["rhel_product_certs_found"])

        if rhel_release_files_found:
            self.assertTrue(details["rhel_release_files_found"])
        else:
            self.assertFalse(details["rhel_release_files_found"])

        if rhel_version:
            self.assertEqual(details["rhel_version"], rhel_version)
        else:
            self.assertIsNone(details["rhel_version"])

        actual_errors_count = len(details["errors"])
        expected_errors_count = len(error_messages) if error_messages else 0
        self.assertEqual(
            actual_errors_count,
            expected_errors_count,
            f"Expected {expected_errors_count} errors but found {actual_errors_count}",
        )
        if error_messages:
            self.assertListEqual(sorted(details["errors"]), sorted(error_messages))

        if syspurpose_role:
            self.assertEqual(details["syspurpose"]["role"], syspurpose_role)

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

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_multiple_ways(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
    ):
        """
        Test finding RHEL via multiple ways.

        This should verify finding RHEL in all currently know ways, which includes:

        * RHEL in at least one partition's release file(s)
        * RHEL in at least one partition's enabled yum repo(s)
        * RHEL in at least one partition's installed product certificate(s)
        * RHEL in at least one partition's RPM database
        """
        rhel_version = "7.4"

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

        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=True,
            rhel_enabled_repos_found=True,
            rhel_product_certs_found=True,
            rhel_release_files_found=True,
            rhel_version=rhel_version,
            syspurpose_role="Red Hat Enterprise Linux Server",
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

        self.assertReportResultsStructure(
            results,
            image_ids=[self.aws_image_id],
            error_messages=[expected_error_message],
        )
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            error_messages=[expected_error_message],
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_cli_no_version_files(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=True,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos_specified_dir(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=True,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos_no_conf(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=True,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found_with_bad_yum_conf(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found_with_unreadable_release_file(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
    ):
        """Test not finding RHEL with an unreadable release file."""
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

        release_files_status = (
            f"Error reading release files on {self.partition_1}: "
            "'utf-8' codec can't decode byte 0xac in position 0: invalid start byte"
        )
        self.assertEqual(
            release_files_status,
            results["images"][self.aws_image_id]["drives"][self.drive_path][
                self.partition_1
            ]["facts"]["rhel_release_files"]["status"],
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_signed_package(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=True,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_product_cert(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=True,
            rhel_release_files_found=False,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_release_file(
        self,
        mock_subprocess_check_output,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=True,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=True,
            rhel_version=rhel_version,
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    def test_no_rpm_db_early_return(
        self, mock_describe_devices, mock_report_results, mock_has_partitions
    ):
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

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(results, image_ids=[self.aws_image_id])
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
        )

        signed_packages_status = _(
            "RPM DB directory on {0} has no data for {1}"
        ).format(self.partition_1, self.aws_image_id)
        self.assertEqual(
            signed_packages_status,
            results["images"][self.aws_image_id]["drives"][self.drive_path][
                self.partition_1
            ]["facts"]["rhel_signed_packages"]["status"],
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    def test_failed_mount(
        self,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
        mock_has_partitions,
    ):
        """Test error handling when mount fails."""
        full_cmd = "mount command"
        stdout_content = b"this is stdout"
        stderr_content = b"and this is stderr"
        e = sh.ErrorReturnCode(
            full_cmd=full_cmd,
            stdout=stdout_content,
            stderr=stderr_content,
            truncate=False,
        )
        mock_sh_mount.side_effect = e
        expected_error_message = (
            f"Mount of {self.partition_1} on image {self.aws_image_id} "
            f"failed with error: {stderr_content} "
            f"full_command: {full_cmd} "
            f"stdout: {stdout_content}"
        )

        def mock_glob_side_effect(pattern):
            return [self.partition_1]

        mock_glob_glob.side_effect = mock_glob_side_effect

        runner = CliRunner()
        with runner.isolated_filesystem():
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_empty(self.partition_1)
            result = runner.invoke(main, ["-t", self.aws_image_id, self.drive_path])

        mock_sh_mount.assert_called
        mock_sh_umount.assert_not_called
        self.assertEqual(result.exit_code, 0)

        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertReportResultsStructure(
            results,
            image_ids=[self.aws_image_id],
            error_messages=[expected_error_message],
        )
        self.assertReportResultsImageDetails(
            results,
            image_id=self.aws_image_id,
            rhel_found=False,
            rhel_signed_packages_found=False,
            rhel_enabled_repos_found=False,
            rhel_product_certs_found=False,
            rhel_release_files_found=False,
            error_messages=[expected_error_message],
        )

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    def test_syspurpose_empty(
        self, mock_describe_devices, mock_report_results, mock_has_partitions
    ):
        """
        Test error handling when syspurpose.json exists but is empty.

        Note: We have to detect RHEL before we parse the syspurpose.json file.
        """
        rhel_version = "7.4"
        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_rhel_syspurpose(self.partition_1, content="")

            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    def test_syspurpose_whitespace(
        self, mock_describe_devices, mock_report_results, mock_has_partitions
    ):
        """
        Test error handling when syspurpose.json exists but only has whitespace.

        Note: We have to detect RHEL before we parse the syspurpose.json file.
        """
        rhel_version = "7.4"
        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_rhel_syspurpose(self.partition_1, content="  ")

            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )
        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        self.assertIn(f"System purpose is empty on: {self.partition_1}", result.output)

    @patch("cli.has_partitions")
    @patch("cli.report_results")
    @patch("cli.describe_devices")
    def test_syspurpose_malformed(
        self, mock_describe_devices, mock_report_results, mock_has_partitions
    ):
        """
        Test error handling when syspurpose.json exists but has non-JSON content.

        Note: We have to detect RHEL before we parse the syspurpose.json file.
        """
        rhel_version = "7.4"
        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path, patch(
            "cli.mount", helper.fake_mount(tempdir_path)
        ), patch("cli.INSPECT_PATH", self.inspect_path):
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_rhel_syspurpose(self.partition_1, content="lol nope!")

            result = runner.invoke(
                main, ["-c", CLOUD_AWS, "-t", self.aws_image_id, self.drive_path]
            )
        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)
        mock_has_partitions.assert_called_once()
        mock_describe_devices.assert_called_once()
        mock_report_results.assert_called_once()
        self.assertIn(
            f"Parsing system purpose on {self.partition_1} failed because",
            result.output,
        )
