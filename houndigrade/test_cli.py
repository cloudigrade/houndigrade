"""Collection of tests for ``cli`` module."""
import pathlib
from gettext import gettext as _
from subprocess import CalledProcessError
from textwrap import dedent
from unittest import TestCase
from unittest.mock import Mock, patch

import sh
from botocore.exceptions import ClientError
from cli import _get_sqs_queue_url, main
from click.testing import CliRunner


class TestCLI(TestCase):
    """Test suite for houndigrade CLI."""

    def test_cli_no_options(self):
        """Test CLI output when given no options."""
        runner = CliRunner()
        result = runner.invoke(main)

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Error: Missing option '--target' / '-t'.", result.output)

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via multiple ways."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        rhel_packages_result = "448\n"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/redhat-release",
                    "./dev/xvdf/xvdf1/etc/os-release",
                    "./dev/xvdf/xvdf2/etc/centos-release",
                    "./dev/xvdf/xvdf2/etc/os-release",
                ]
            elif "/etc/os-release" in pattern:
                return ["./dev/xvdf/xvdf1/etc/os-release"]
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return ["./dev/xvdf/xvdf1/etc/rhsm/syspurpose/syspurpose.json"]
            elif "/etc/pki/product/*" in pattern:
                return ["./dev/xvdf/xvdf1/etc/pki/product/69.pem"]
            elif "/etc/yum.conf" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/yum.conf",
                    "./dev/xvdf/xvdf2/etc/yum.conf",
                ]
            elif "/*.repo" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/yum.repos.d/rhel7-internal.repo",
                    "./dev/xvdf/xvdf1/etc/yum.repos.d/rhel.repo",
                    "./dev/xvdf/xvdf2/etc/yum.repos.d/rhel7-internal.repo",
                ]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            rhel_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            self.prep_fs(drive_path)
            self.prepare_fs_with_rhel_repos(drive_path)

            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])
        self.assertTrue(mock_sh_mount.called)
        self.assertEqual(mock_sh_mount.call_count, 2)
        self.assertEqual(mock_sh_umount.call_count, 2)
        self.assertEqual(result.exit_code, 0)
        self.assertIn('"cloud": "aws"', result.output)
        self.assertIn('"ami-123456789"', result.output)
        self.assertIn("RHEL found via release file on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn("RHEL found via signed packages on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn("RHEL found via release file on: ./dev/xvdf2", result.output)
        self.assertIn("RHEL (version 7.4) found on: ami-1234567", result.output)
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

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertTrue(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertTrue(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertTrue(results["images"][image_id]["rhel_product_certs_found"])
        self.assertTrue(results["images"][image_id]["rhel_release_files_found"])
        self.assertEqual(results["images"][image_id]["rhel_version"], "7.4")
        self.assertEqual(
            results["images"][image_id]["syspurpose"]["role"],
            "Red Hat Enterprise Linux Server",
        )

    @patch("cli.report_results")
    @patch("cli.subprocess.run")
    def test_results_error_when_mount_path_does_not_exist(
        self, mock_subprocess_run, mock_report_results
    ):
        """Test errors in the results when mount path does not exist."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"

        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        expected_error_message = _("Nothing found at path {} for {}").format(
            drive_path, image_id
        )

        self.assertFalse(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn(expected_error_message, results["errors"])
        self.assertIn(image_id, results["images"])
        image_result = results["images"][image_id]
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
        mock_report_results,
    ):
        """Test appropriate error handling when expected files are missing."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/redhat-release",
                    "./dev/xvdf/xvdf1/etc/os-release",
                    "./dev/xvdf/xvdf2/etc/centos-release",
                    "./dev/xvdf/xvdf2/etc/os-release",
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
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No such file or directory", result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test appropriate error handling when release files are missing."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
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
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test not finding RHEL via normal inspection."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
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
                return ["./dev/xvdf/xvdf2/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/yum.conf",
                    "./dev/xvdf/xvdf2/etc/yum.conf",
                ]
            elif "/*.repo" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/yum.repos.d/rhel7-internal.repo",
                    "./dev/xvdf/xvdf2/etc/yum.repos.d/random.repo",
                ]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [no_packages_result, e]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            self.prepare_fs_with_non_enabled_repos(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(mock_sh_mount.call_count, 2)
        self.assertEqual(mock_sh_umount.call_count, 2)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn("RHEL not found on: ami-1234567", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf2", result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertFalse(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via enabled yum repos."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return ["./dev/xvdf/xvdf2/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/yum.conf",
                    "./dev/xvdf/xvdf2/etc/yum.conf",
                ]
            elif "/*.repo" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/yum.repos.d/rhel7-internal.repo",
                    "./dev/xvdf//xvdf1/etc/yum.repos.d/rhel.repo",
                    "./dev/xvdf/xvdf2/etc/yum.repos.d/rhel7-internal.repo",
                ]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            self.prepare_fs_with_rhel_repos(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn("RHEL (version None) found on: ami-1234567", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf2", result.output
        )
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

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertTrue(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via enabled yum repos in custom yum repos path."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return ["./dev/xvdf/xvdf2/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return ["./dev/xvdf/xvdf1/etc/yum.conf"]
            elif "/*.repo" in pattern:
                return ["./dev/xvdf/xvdf1/etc/new_dir/yum_repos/rhel7-internal.repo"]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            self.prepare_fs_with_reposdir_specified(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn("RHEL (version None) found on: ami-1234567", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-extras", "name": "RHEL 7 - $basearch"}',
            result.output,
        )

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertTrue(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via enabled yum repos without yum.conf."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return ["./dev/xvdf/xvdf2/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return ["./dev/xvdf/xvdf1/etc/new_dir/yum_repos/rhel7-internal.repo"]
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            self.prepare_fs_with_reposdir_specified(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn("RHEL (version None) found on: ami-1234567", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal", "name": "RHEL 7 - $basearch"}',
            result.output,
        )
        self.assertIn(
            '{"repo": "rhel7-cdn-internal-extras", "name": "RHEL 7 - $basearch"}',
            result.output,
        )

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertTrue(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test not finding RHEL with bad yum.conf."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
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
                return ["./dev/xvdf1"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            self.prepare_fs_with_bad_yum_conf(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn("RHEL not found on: ami-1234567", result.output)
        self.assertIn("Error reading yum repo files on", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertFalse(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test not finding RHEL with an unreadable release file."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return ["./dev/xvdf/xvdf1/etc/potato-release"]
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
                return ["./dev/xvdf1"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            self.prepare_fs_with_bad_release_file(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn("Error reading release files on ./dev/xvdf1:", result.output)
        self.assertIn("RHEL not found on: ami-1234567", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertFalse(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])
        self.assertEqual(
            (
                "Error reading release files on ./dev/xvdf1: "
                "'utf-8' codec can't decode byte 0xac in position 0: invalid start byte"
            ),
            results["images"][image_id]["drives"]["./dev/xvdf"]["./dev/xvdf1"]["facts"][
                "rhel_release_files"
            ]["status"],
        )

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via signed package."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        rhel_packages_result = "1\n"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return ["./dev/xvdf/xvdf2/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            rhel_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn("RHEL (version None) found on: ami-1234567", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("No yum.conf file found on: ./dev/xvdf1", result.output)
        self.assertIn("No .repo files found on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn("RHEL found via signed packages on: ./dev/xvdf1", result.output)
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn("No yum.conf file found on: ./dev/xvdf2", result.output)
        self.assertIn("No .repo files found on: ./dev/xvdf2", result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertTrue(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via product certificate in primary location."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product/*" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/pki/product/69.pem",
                    "./dev/xvdf/xvdf2/etc/pki/product/185.pem",
                    "./dev/xvdf/xvdf3/etc/pki/product/479.pem",
                ]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2", "./dev/xvdf3"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn("RHEL (version None) found on: ami-1234567", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf3", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf3", result.output
        )
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertTrue(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via product certificate in secondary location."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return []
            elif "/etc/os-release" in pattern:
                return []
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return []
            elif "/etc/pki/product-default/*" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/pki/product-default/69.pem",
                    "./dev/xvdf/xvdf2/etc/pki/product-default/185.pem",
                    "./dev/xvdf/xvdf3/etc/pki/product-default/479.pem",
                ]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2", "./dev/xvdf3"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf1"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf2"))
            ),
            result.output,
        )
        self.assertIn(
            '"status": "{}"'.format(
                _("No release files found on {}".format("./dev/xvdf3"))
            ),
            result.output,
        )
        self.assertIn("RHEL (version None) found on: ami-1234567", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf3", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf3", result.output
        )
        self.assertIn(
            "RHEL found via product certificate on: ./dev/xvdf3", result.output
        )
        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertTrue(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])

    @patch("cli.report_results")
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
        mock_report_results,
    ):
        """Test finding RHEL via etc release file."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        no_packages_result = "0\n"

        def mock_glob_side_effect(pattern):
            if "etc/*-release" in pattern:
                return [
                    "./dev/xvdf/xvdf1/etc/redhat-release",
                    "./dev/xvdf/xvdf1/etc/os-release",
                    "./dev/xvdf/xvdf2/etc/centos-release",
                    "./dev/xvdf/xvdf2/etc/os-release",
                ]
            elif "/etc/os-release" in pattern:
                return ["./dev/xvdf/xvdf1/etc/os-release"]
            elif "/etc/rhsm/syspurpose/syspurpose.json" in pattern:
                return ["./dev/xvdf/xvdf1/etc/rhsm/syspurpose/syspurpose.json"]
            elif "/etc/pki/product/*" in pattern:
                return ["./dev/xvdf/xvdf2/etc/pki/product/185.pem"]
            elif "/etc/yum.conf" in pattern:
                return []
            elif "/*.repo" in pattern:
                return []
            elif "/var/lib/rpm/*" in pattern:
                return ["__db.001"]
            else:
                return ["./dev/xvdf1", "./dev/xvdf2"]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [
            no_packages_result,
            no_packages_result,
        ]

        runner = CliRunner()

        with runner.isolated_filesystem():
            self.prep_fs(drive_path)
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("RHEL (version 7.4) found on: ami-1234567", result.output)
        self.assertIn("RHEL found via release file on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf1", result.output
        )
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf1", result.output
        )
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf1", result.output)
        self.assertIn("RHEL not found via release file on: ./dev/xvdf2", result.output)
        self.assertIn("RHEL not found via enabled repos on: ./dev/xvdf2", result.output)
        self.assertIn(
            "RHEL not found via signed packages on: ./dev/xvdf2", result.output
        )
        self.assertIn(
            "RHEL not found via product certificate on: ./dev/xvdf2", result.output
        )
        self.assertIn("RHEL found via release file on: ./dev/xvdf2", result.output)
        self.assertIn('"role": "Red Hat Enterprise Linux Server"', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertTrue(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertTrue(results["images"][image_id]["rhel_release_files_found"])
        self.assertEqual(results["images"][image_id]["rhel_version"], "7.4")
        self.assertEqual(
            results["images"][image_id]["syspurpose"]["role"],
            "Red Hat Enterprise Linux Server",
        )

    @patch("cli.report_results")
    @patch("cli.glob.glob")
    @patch("cli.sh.umount")
    @patch("cli.sh.mount")
    def test_no_rpm_db_early_return(
        self, mock_sh_mount, mock_sh_umount, mock_glob_glob, mock_report_results
    ):
        """Test error handling when RPM DB does not exist."""
        cloud = "aws"
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"

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
                return ["./dev/xvdf1"]

        mock_glob_glob.side_effect = mock_glob_side_effect

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-c", cloud, "-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertTrue(mock_sh_umount.called)
        self.assertEqual(result.exit_code, 0)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 0)
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 0)
        self.assertFalse(results["images"][image_id]["rhel_found"])
        self.assertFalse(results["images"][image_id]["rhel_signed_packages_found"])
        self.assertFalse(results["images"][image_id]["rhel_enabled_repos_found"])
        self.assertFalse(results["images"][image_id]["rhel_product_certs_found"])
        self.assertFalse(results["images"][image_id]["rhel_release_files_found"])
        self.assertIsNone(results["images"][image_id]["rhel_version"])
        self.assertIsNone(results["images"][image_id]["syspurpose"])
        self.assertEqual(
            _("RPM DB directory on {0} has no data for {1}").format(
                "./dev/xvdf1", image_id
            ),
            results["images"][image_id]["drives"]["./dev/xvdf"]["./dev/xvdf1"]["facts"][
                "rhel_signed_packages"
            ]["status"],
        )

    @patch("cli.report_results")
    @patch("cli.glob.glob")
    @patch("cli.sh.mount")
    def test_failed_mount(self, mock_sh_mount, mock_glob_glob, mock_report_results):
        """Test error handling when mount fails."""
        image_id = "ami-123456789"
        drive_path = "./dev/xvdf"
        error_message = "failed"
        e = sh.ErrorReturnCode_1(
            full_cmd="mount", stdout=Mock(), stderr=Mock(), truncate=False
        )
        mock_sh_mount.mount.side_effect = e

        def mock_glob_side_effect(pattern):
            return ["./dev/xvdf1"]

        mock_glob_glob.side_effect = mock_glob_side_effect

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path("{}/xvdf1".format(drive_path)).mkdir(
                parents=True, exist_ok=True
            )
            result = runner.invoke(main, ["-t", image_id, drive_path])

        self.assertTrue(mock_sh_mount.called)
        self.assertEqual(result.exit_code, 0)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]

        self.assertIn("cloud", results)
        self.assertIn("images", results)
        self.assertIn("errors", results)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn(error_message, results["errors"][0])
        self.assertIn(image_id, results["images"])
        self.assertEqual(len(results["images"][image_id]["errors"]), 1)
        self.assertIn(error_message, results["images"][image_id]["errors"][0])

    @staticmethod
    def prep_fs(drive_path):
        """Prepare a filesystem directory for testing."""
        pathlib.Path("{}/xvdf1/etc/rhsm/syspurpose".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf2/etc".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )

        redhat_release = "Red Hat Enterprise Linux Server release 7.4 (Maipo)\n"
        centos_release = "CentOS Linux release 7.4.1708 (Core)\n"

        rh_os_release = """\
            NAME="Red Hat Enterprise Linux Server"
            VERSION="7.4 (Maipo)"
            ID="rhel"
            ID_LIKE="fedora"
            VARIANT="Server"
            VARIANT_ID="server"
            VERSION_ID="7.4"
            PRETTY_NAME="Red Hat Enterprise Linux Server 7.4 (Maipo)"
            ANSI_COLOR="0;31"
            CPE_NAME="cpe:/o:redhat:enterprise_linux:7.4:GA:server"
            HOME_URL="https://www.redhat.com/"
            BUG_REPORT_URL="https://bugzilla.redhat.com/"

            REDHAT_BUGZILLA_PRODUCT="Red Hat Enterprise Linux 7"
            REDHAT_BUGZILLA_PRODUCT_VERSION=7.4
            REDHAT_SUPPORT_PRODUCT="Red Hat Enterprise Linux"
            REDHAT_SUPPORT_PRODUCT_VERSION="7.4"

            """

        centos_os_release = """\
            NAME="CentOS Linux"
            VERSION="7 (Core)"
            ID="centos"
            ID_LIKE="rhel fedora"
            VERSION_ID="7"
            PRETTY_NAME="CentOS Linux 7 (Core)"
            ANSI_COLOR="0;31"
            CPE_NAME="cpe:/o:centos:centos:7"
            HOME_URL="https://www.centos.org/"
            BUG_REPORT_URL="https://bugs.centos.org/"

            CENTOS_MANTISBT_PROJECT="CentOS-7"
            CENTOS_MANTISBT_PROJECT_VERSION="7"
            REDHAT_SUPPORT_PRODUCT="centos"
            REDHAT_SUPPORT_PRODUCT_VERSION="7"

            """

        rh_syspurpose = """\
            {
              "role": "Red Hat Enterprise Linux Server",
              "service_level_agreement": "Premium",
              "usage": "Development/Test"
            }

            """

        with open("{}/xvdf1/etc/redhat-release".format(drive_path), "w") as f:
            f.write(redhat_release)
        with open("{}/xvdf1/etc/os-release".format(drive_path), "w") as f:
            f.write(dedent(rh_os_release))
        with open(
            "{}/xvdf1/etc/rhsm/syspurpose/syspurpose.json".format(drive_path), "w"
        ) as f:
            f.write(dedent(rh_syspurpose))

        with open("{}/xvdf2/etc/centos-release".format(drive_path), "w") as f:
            f.write(centos_release)
        with open("{}/xvdf2/etc/os-release".format(drive_path), "w") as f:
            f.write(dedent(centos_os_release))

    @staticmethod
    def prepare_fs_with_rhel_repos(drive_path):
        """Prepare a filesystem directory for testing with enabled yum repos."""
        pathlib.Path("{}/xvdf1/etc".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf2/etc".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf1/etc/yum.repos.d".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf2/etc/yum.repos.d".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )

        yum_conf = """\
            [main]
            cachedir=/var/cache/yum/$basearch/$releasever
            keepcache=0
            debuglevel=2
            logfile=/var/log/yum.log
            exactarch=1
            obsoletes=1
            gpgcheck=1
            plugins=1
            installonly_limit=3

            #  This is the default, if you make this bigger yum won't see if the metadata
            # is newer on the remote and so you'll "gain" the bandwidth of not having to
            # download the new metadata and "pay" for it by yum not having correct
            # information.
            #  It is esp. important, to have correct metadata, for distributions like
            # Fedora which don't keep old packages around. If you don't like this checking
            # interupting your command line usage, it's much better to have something
            # manually check the metadata once an hour (yum-updatesd will do this).
            # metadata_expire=90m

            # PUT YOUR REPOS HERE OR IN separate files named file.repo
            # in /etc/yum.repos.d"""  # noqa: E501

        yum_repo_file = """\
            [rhel7-cdn-internal]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
            enabled=1
            gpgcheck=0

            [rhel7-cdn-internal-extras]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
            enabled=1
            gpgcheck=0"""  # noqa: E501

        more_rhel_repos = """\
            [rhel7-cdn-internal-optional]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/optional/os/
            enabled=1
            gpgcheck=0"""  # noqa: E501

        with open("{}/xvdf1/etc/yum.conf".format(drive_path), "w") as f:
            f.write(yum_conf)
        with open(
            "{}/xvdf1/etc/yum.repos.d/rhel7-internal.repo".format(drive_path), "w"
        ) as f:
            f.write(yum_repo_file)
        with open("{}/xvdf1/etc/yum.repos.d/rhel.repo".format(drive_path), "w") as f:
            f.write(more_rhel_repos)
        with open("{}/xvdf2/etc/yum.conf".format(drive_path), "w") as f:
            f.write(yum_conf)
        with open(
            "{}/xvdf2/etc/yum.repos.d/rhel7-internal.repo".format(drive_path), "w"
        ) as f:
            f.write(yum_repo_file)

    @staticmethod
    def prepare_fs_with_non_enabled_repos(drive_path):
        """Prepare a filesystem directory for testing with disabled yum repos."""
        pathlib.Path("{}/xvdf1/etc".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf2/etc".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf1/etc/yum.repos.d".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf2/etc/yum.repos.d".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )

        yum_conf = """\
            [main]
            cachedir=/var/cache/yum/$basearch/$releasever
            keepcache=0
            debuglevel=2
            logfile=/var/log/yum.log
            exactarch=1
            obsoletes=1
            gpgcheck=1
            plugins=1
            installonly_limit=3

            #  This is the default, if you make this bigger yum won't see if the metadata
            # is newer on the remote and so you'll "gain" the bandwidth of not having to
            # download the new metadata and "pay" for it by yum not having correct
            # information.
            #  It is esp. important, to have correct metadata, for distributions like
            # Fedora which don't keep old packages around. If you don't like this checking
            # interupting your command line usage, it's much better to have something
            # manually check the metadata once an hour (yum-updatesd will do this).
            # metadata_expire=90m

            # PUT YOUR REPOS HERE OR IN separate files named file.repo
            # in /etc/yum.repos.d"""  # noqa: E501

        non_enabled_repo_file = """\
            [rhel7-cdn-internal]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
            enabled=0
            gpgcheck=0

            [rhel7-cdn-internal-extras]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
            enabled=0
            gpgcheck=0
            """  # noqa: E501

        non_rhel_repo_file = """\
            [random-cdn-internal]
            name=Random repo
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
            enabled=1
            gpgcheck=0

            [random-cdn-internal-extras]
            name=Random repo
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
            enabled=1
            gpgcheck=0
            """  # noqa: E501

        with open("{}/xvdf1/etc/yum.conf".format(drive_path), "w") as f:
            f.write(yum_conf)
        with open(
            "{}/xvdf1/etc/yum.repos.d/rhel7-internal.repo".format(drive_path), "w"
        ) as f:
            f.write(non_enabled_repo_file)
        with open("{}/xvdf2/etc/yum.conf".format(drive_path), "w") as f:
            f.write(yum_conf)
        with open("{}/xvdf2/etc/yum.repos.d/random.repo".format(drive_path), "w") as f:
            f.write(non_rhel_repo_file)

    @staticmethod
    def prepare_fs_with_reposdir_specified(drive_path):
        """Prepare a filesystem directory for testing with custom yum repo dir."""
        pathlib.Path("{}/xvdf1/etc".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        pathlib.Path("{}/xvdf1/etc/new_dir/yum_repos".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )

        yum_conf = """\
            [main]
            cachedir=/var/cache/yum/$basearch/$releasever
            keepcache=0
            debuglevel=2
            logfile=/var/log/yum.log
            exactarch=1
            obsoletes=1
            gpgcheck=1
            plugins=1
            installonly_limit=3
            reposdir=/etc/new_dir/yum_repos

            #  This is the default, if you make this bigger yum won't see if the metadata
            # is newer on the remote and so you'll "gain" the bandwidth of not having to
            # download the new metadata and "pay" for it by yum not having correct
            # information.
            #  It is esp. important, to have correct metadata, for distributions like
            # Fedora which don't keep old packages around. If you don't like this checking
            # interupting your command line usage, it's much better to have something
            # manually check the metadata once an hour (yum-updatesd will do this).
            # metadata_expire=90m

            # PUT YOUR REPOS HERE OR IN separate files named file.repo
            # in /etc/yum.repos.d"""  # noqa: E501

        yum_repo_file = """\
            [rhel7-cdn-internal]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
            enabled=1
            gpgcheck=0

            [rhel7-cdn-internal-extras]
            name=RHEL 7 - $basearch
            baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
            enabled=1
            gpgcheck=0"""  # noqa: E501

        with open("{}/xvdf1/etc/yum.conf".format(drive_path), "w") as f:
            f.write(yum_conf)
        with open(
            "{}/xvdf1/etc/new_dir/yum_repos/rhel7-internal.repo".format(drive_path), "w"
        ) as f:
            f.write(yum_repo_file)

    @staticmethod
    def prepare_fs_with_bad_yum_conf(drive_path):
        """Prepare a filesystem directory for testing with a bad yum repo conf."""
        pathlib.Path("{}/xvdf1/etc/".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        with open("{}/xvdf1/etc/yum.conf".format(drive_path), "wb") as f:
            f.write(b"\xac")  # not a valid utf8 string!

    @staticmethod
    def prepare_fs_with_bad_release_file(drive_path):
        """Prepare a filesystem directory for testing with a bad release file."""
        pathlib.Path("{}/xvdf1/etc/".format(drive_path)).mkdir(
            parents=True, exist_ok=True
        )
        release_file_path = "{}/xvdf1/etc/potato-release".format(drive_path)
        with open(release_file_path, "wb") as f:
            f.write(b"\xac")  # not a valid utf8 string!

    @patch("cli.boto3")
    def test_get_sqs_queue_url_for_existing_queue(self, mock_boto3):
        """
        Test getting URL for existing SQS queue.

        Note: This function was copied verbatim from `cloudigrade`.

        FIXME: Move this function to a shared library.
        """
        mock_client = mock_boto3.client.return_value
        queue_name = Mock()
        expected_url = Mock()
        mock_client.get_queue_url.return_value = {"QueueUrl": expected_url}
        queue_url = _get_sqs_queue_url(queue_name)
        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)

    @patch("cli.boto3")
    def test_get_sqs_queue_url_creates_new_queue(self, mock_boto3):
        """
        Test getting URL for a SQS queue that does not yet exist.

        Note: This function was copied verbatim from `cloudigrade`.

        FIXME: Move this function to a shared library.
        """
        mock_client = mock_boto3.client.return_value
        queue_name = Mock()
        expected_url = Mock()
        error_response = {"Error": {"Code": ".NonExistentQueue"}}
        exception = ClientError(error_response, Mock())
        mock_client.get_queue_url.side_effect = exception
        mock_client.create_queue.return_value = {"QueueUrl": expected_url}
        queue_url = _get_sqs_queue_url(queue_name)
        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)
        mock_client.create_queue.assert_called_with(QueueName=queue_name)
