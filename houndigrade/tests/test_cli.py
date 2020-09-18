"""Collection of tests for ``cli`` module."""
import pathlib
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


class TestCLI(TestCase):
    """Test suite for houndigrade CLI."""

    def setUp(self):
        """Set up random fixture data for each test."""
        self.aws_image_id = f"ami-{random.randrange(10 ** 11, 10 ** 12 - 1)}"
        drive_letter = random.choice(string.ascii_lowercase)
        self.drive_path = f"./dev/xvd{drive_letter}"
        self.partition_1 = f"{self.drive_path}/xvd{drive_letter}1"
        self.partition_2 = f"{self.drive_path}/xvd{drive_letter}2"
        self.partition_3 = f"{self.drive_path}/xvd{drive_letter}3"

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
    @patch("cli.glob.glob")
    @patch("cli.subprocess.check_output")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    def test_rhel_found_multiple_ways(
        self,
        mock_sh_mount,
        mock_sh_umount,
        mock_subprocess_check_output,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via multiple ways."""
        cloud = "aws"
        rhel_packages_result = "448\n"
        no_packages_result = "0\n"
        rhel_version = "7.4"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [
                    f"{self.partition_1}/etc/redhat-release",
                    f"{self.partition_1}/etc/os-release",
                    f"{self.partition_2}/etc/centos-release",
                    f"{self.partition_2}/etc/os-release",
                ]
            elif "/etc/os-release" in pattern:
                return [f"{self.partition_1}/etc/os-release"]
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return [f"{self.partition_1}/etc/rhsm/syspurpose/syspurpose.json"]
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_1}/etc/pki/product/69.pem"]
            elif "/etc/yum.conf" in pattern:
                return [
                    f"{self.partition_1}/etc/yum.conf",
                    f"{self.partition_2}/etc/yum.conf",
                ]
            elif "/*.repo" in pattern:
                return [
                    f"{self.partition_1}/etc/yum.repos.d/rhel7-internal.repo",
                    f"{self.partition_1}/etc/yum.repos.d/rhel.repo",
                    f"{self.partition_2}/etc/yum.repos.d/rhel7-internal.repo",
                ]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            rhel_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_rhel_syspurpose(self.partition_1)
            helper.prepare_fs_centos_release(self.partition_2)
            helper.prepare_fs_with_yum(self.partition_1)
            helper.prepare_fs_with_yum(self.partition_2, include_optional=False)

            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )
        self.assertTrue(mock_sh_mount.called)
        self.assertEqual(mock_sh_mount.call_count, 2)
        self.assertEqual(mock_sh_umount.call_count, 2)
        self.assertEqual(result.exit_code, 0)
        self.assertIn('"cloud": "aws"', result.output)
        self.assertIn(f'"{self.aws_image_id}"', result.output)

        partition_path = self.partition_1
        self.assertFoundReleaseFile(result.output, partition_path)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path)
        self.assertFoundSignedPackages(result.output, partition_path)

        partition_path = self.partition_2
        self.assertFoundReleaseFile(result.output, partition_path)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
            results["images"][self.aws_image_id]["rhel_version"], rhel_version
        )
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
        cloud = "aws"

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
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
    @patch("cli.glob.glob")
    @patch("cli.subprocess.check_output")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    def test_cli_disappearing_files(
        self,
        mock_sh_mount,
        mock_sh_umount,
        mock_subprocess_check_output,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test appropriate error handling when expected files are missing."""
        cloud = "aws"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [
                    f"{self.partition_1}/etc/redhat-release",
                    f"{self.partition_1}/etc/os-release",
                    f"{self.partition_2}/etc/centos-release",
                    f"{self.partition_2}/etc/os-release",
                ]
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No such file or directory", result.output)

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
    @patch("cli.glob.glob")
    @patch("cli.subprocess.check_output")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    def test_cli_no_version_files(
        self,
        mock_sh_mount,
        mock_sh_umount,
        mock_subprocess_check_output,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test appropriate error handling when release files are missing."""
        cloud = "aws"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
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
        self.assertIsNone(results["images"][self.aws_image_id]["rhel_version"])
        self.assertIsNone(results["images"][self.aws_image_id]["syspurpose"])

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test not finding RHEL via normal inspection."""
        cloud = "aws"
        no_packages_result = "0\n"
        e = CalledProcessError(1, "mount", stderr="Mount failed.")

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_2}/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return [
                    f"{self.partition_1}/etc/yum.conf",
                    f"{self.partition_2}/etc/yum.conf",
                ]
            elif "/*.repo" in pattern:
                return [
                    f"{self.partition_1}/etc/yum.repos.d/rhel7-internal.repo",
                    f"{self.partition_2}/etc/yum.repos.d/random.repo",
                ]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [no_packages_result, e]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_with_yum(
                self.partition_1, rhel_enabled=False, include_optional=False
            )
            helper.prepare_fs_with_yum(
                self.partition_2, rhel_enabled=False, include_optional=True
            )
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(mock_sh_mount.call_count, 2)
        self.assertEqual(mock_sh_umount.call_count, 2)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertRhelNotFound(result.output, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via enabled yum repos."""
        cloud = "aws"
        no_packages_result = "0\n"
        rhel_version = None  # TODO Is this correct?

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_2}/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return [
                    f"{self.partition_1}/etc/yum.conf",
                    f"{self.partition_2}/etc/yum.conf",
                ]
            elif "/*.repo" in pattern:
                return [
                    f"{self.partition_1}/etc/yum.repos.d/rhel7-internal.repo",
                    f"{self.partition_1}/etc/yum.repos.d/rhel.repo",
                    f"{self.partition_2}/etc/yum.repos.d/rhel7-internal.repo",
                ]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_with_yum(self.partition_1)
            helper.prepare_fs_with_yum(self.partition_2, include_optional=False)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos_specified_dir(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via enabled yum repos in custom yum repos path."""
        cloud = "aws"
        no_packages_result = "0\n"
        rhel_version = None  # TODO Is this correct?

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_2}/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return [f"{self.partition_1}/etc/yum.conf"]
            elif "/*.repo" in pattern:
                return [f"{self.partition_1}/etc/new_dir/yum_repos/rhel7-internal.repo"]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_with_yum(self.partition_1, default_reposdir=False)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_enabled_repos_no_conf(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via enabled yum repos without yum.conf."""
        cloud = "aws"
        no_packages_result = "0\n"
        rhel_version = None  # TODO Is this correct?

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_2}/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return [f"{self.partition_1}/etc/new_dir/yum_repos/rhel7-internal.repo"]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_with_yum(
                self.partition_1, include_yum_conf=False, default_reposdir=False
            )
            helper.prepare_fs_with_yum(
                self.partition_2, include_yum_conf=False, default_reposdir=False
            )
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found_with_bad_yum_conf(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test not finding RHEL with bad yum.conf."""
        cloud = "aws"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return []
            elif "/etc/yum.conf" in pattern:
                return ["/etc/yum.conf"]
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_with_bad_yum_conf(self.partition_1)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertRhelNotFound(result.output, self.aws_image_id)
        self.assertIn("Error reading yum repo files on", result.output)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        # self.assertFoundEnabledRepos(result.output, partition_path)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_not_found_with_unreadable_release_file(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test not finding RHEL with an unreadable release file."""
        cloud = "aws"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [f"{self.partition_1}/etc/potato-release"]
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return []
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_with_bad_release_file(self.partition_1)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            f"Error reading release files on {self.partition_1}", result.output
        )
        self.assertRhelNotFound(result.output, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_signed_package(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via signed package."""
        cloud = "aws"
        rhel_packages_result = "1\n"
        no_packages_result = "0\n"
        rhel_version = None  # TODO Is this correct?

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_2}/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            rhel_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path)
        self.assertIn(f"No yum.conf file found on: {partition_path}", result.output)
        self.assertIn(f"No .repo files found on: {partition_path}", result.output)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)
        self.assertIn(f"No yum.conf file found on: {partition_path}", result.output)
        self.assertIn(f"No .repo files found on: {partition_path}", result.output)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_product_cert(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via product certificate in primary location."""
        cloud = "aws"
        no_packages_result = "0\n"
        rhel_version = None  # TODO Is this correct?

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [
                    f"{self.partition_1}/etc/pki/product/69.pem",
                    f"{self.partition_2}/etc/pki/product/185.pem",
                    f"{self.partition_3}/etc/pki/product/479.pem",
                ]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2, self.partition_3]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
            pathlib.Path(self.partition_2).mkdir(parents=True, exist_ok=True)
            pathlib.Path(self.partition_3).mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, True)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, True)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_3
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, True)
        # self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_product_cert_secondary_location(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via product certificate in secondary location."""
        cloud = "aws"
        no_packages_result = "0\n"
        rhel_version = None  # TODO Is this correct?

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product-default/*" in pattern:
                return [
                    f"{self.partition_1}/etc/pki/product-default/69.pem",
                    f"{self.partition_2}/etc/pki/product-default/185.pem",
                    f"{self.partition_3}/etc/pki/product-default/479.pem",
                ]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2, self.partition_3]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
            pathlib.Path(self.partition_2).mkdir(parents=True, exist_ok=True)
            pathlib.Path(self.partition_3).mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_1))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_2))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format(self.partition_3))
            ),
            result.output,
        )
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, True)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_3
        # self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, True)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    @patch("cli.subprocess.check_output")
    def test_rhel_found_via_release_file(
        self,
        mock_subprocess_check_output,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test finding RHEL via etc release file."""
        cloud = "aws"
        no_packages_result = "0\n"
        rhel_version = "7.4"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [
                    f"{self.partition_1}/etc/redhat-release",
                    f"{self.partition_1}/etc/os-release",
                    f"{self.partition_2}/etc/centos-release",
                    f"{self.partition_2}/etc/os-release",
                ]
            elif "/etc/os-release" in pattern:
                return [f"{self.partition_1}/etc/os-release"]
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return [f"{self.partition_1}/etc/rhsm/syspurpose/syspurpose.json"]
            elif "/etc/pki/product/*" in pattern:
                return [f"{self.partition_2}/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return [self.partition_1, self.partition_2]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            helper.prepare_fs_rhel_release(self.partition_1)
            helper.prepare_fs_rhel_syspurpose(self.partition_1)
            helper.prepare_fs_centos_release(self.partition_2)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertRhelFound(result.output, rhel_version, self.aws_image_id)

        partition_path = self.partition_1
        # These two assertions appear to be in conflict, but unfortunately this is
        # "correct" due to the how our fake filesystem is "working".
        # When `find_release_files` runs, its `glob` call actually gets *all* release
        # files in both of our fake partition folders. This means that when we're
        # looking at "xvdf1" we also see all the files for "xvdf2" and vice versa.
        # Yes, this is weird, but unfortunately it looks like this issue has been
        # hiding in our test code for a long time.
        # TODO Refactor our fake test filesystem logic to address this issue.
        self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundReleaseFile(result.output, partition_path, True)

        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

        partition_path = self.partition_2
        # These two assertions appear to be in conflict. See earlier comment...
        self.assertFoundReleaseFile(result.output, partition_path, False)
        self.assertFoundReleaseFile(result.output, partition_path, True)

        self.assertFoundEnabledRepos(result.output, partition_path, False)
        self.assertFoundProductCertificate(result.output, partition_path, False)
        self.assertFoundSignedPackages(result.output, partition_path, False)

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
        self.assertEqual(
            results["images"][self.aws_image_id]["syspurpose"]["role"],
            "Red Hat Enterprise Linux Server",
        )

    @patch("cli.report_results")
    @patch("cli.describe_devices")
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    def test_no_rpm_db_early_return(
        self,
        mock_sh_mount,
        mock_sh_umount,
        mock_glob_glob,
        mock_describe_devices,
        mock_report_results,
    ):
        """Test error handling when RPM DB does not exist."""
        cloud = "aws"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return []
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return []
            else:
                return [self.partition_1]

        mock_glob_glob.side_effect = mock_glob_side_effect

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
            result = runner.invoke(
                main, ["-c", cloud, "-t", self.aws_image_id, self.drive_path]
            )

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
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
            pathlib.Path(self.partition_1).mkdir(parents=True, exist_ok=True)
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
