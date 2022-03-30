"""Collection of tests for ``cli.mount`` context manager."""
import random
import string
from unittest import TestCase
from unittest.mock import patch

from click.testing import CliRunner

from cli import mount
from tests import helper


class TestMount(TestCase):
    """Test suite for houndigrade CLI's "mount" context manager."""

    def setUp(self):
        """Set up random fixture data for each test."""
        self.aws_image_id = f"ami-{random.randrange(10 ** 11, 10 ** 12 - 1)}"
        drive_letter = random.choice(string.ascii_lowercase)
        self.drive_path = f"./dev/xvd{drive_letter}"
        self.partition_1 = f"{self.drive_path}1"

    @patch("cli.sh.umount", create=True)
    @patch("cli.sh.mount", create=True)
    @patch("cli.click")
    def test_mount_non_ostree(self, mock_click, mock_sh_mount, mock_sh_umount):
        """Test handling of mounting non-ostree deployments."""
        mock_click_echo = mock_click.echo
        mock_inspect_path = "/mnt/inspect"
        mock_mount_result = mock_sh_mount.return_value
        mock_umount_result = mock_sh_umount.return_value
        mock_mount_result.exit_code = 0
        mock_umount_result.exit_code = 0

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path:
            with mount(tempdir_path, mock_inspect_path):
                mock_click_echo.assert_any_call(f"Mounting {tempdir_path}.")
                mock_click_echo.assert_called_with(
                    f"Mounting result {mock_mount_result.exit_code}."
                )
                mock_sh_mount.assert_called_once_with(
                    "-t", "auto", "-o", "ro", f"{tempdir_path}", f"{mock_inspect_path}"
                )
            mock_click_echo.assert_any_call(f"UnMounting {tempdir_path}.")
            mock_click_echo.assert_called_with(
                f"UnMounting result {mock_umount_result.exit_code}."
            )

    @patch("cli.sh.umount", create=True)
    @patch("cli.sh.mount", create=True)
    @patch("cli.click")
    def test_mount_ostree(self, mock_click, mock_sh_mount, mock_sh_umount):
        """Test handling of mounting ostree deployments."""
        mock_click_echo = mock_click.echo
        mock_mount_result = mock_sh_mount.return_value
        mock_umount_result = mock_sh_umount.return_value
        mock_mount_result.exit_code = 0
        mock_umount_result.exit_code = 0

        runner = CliRunner()
        with runner.isolated_filesystem() as tempdir_path:
            helper.prepare_fs_empty(self.drive_path)
            helper.prepare_fs_ostree_rhel_release(self.partition_1)
            fs_root = f"{tempdir_path}/{self.partition_1}"
            with patch("cli.INSPECT_PATH", fs_root), mount(
                tempdir_path, "/mnt/inspect"
            ):
                from cli import INSPECT_PATH

                mock_click_echo.assert_any_call(f"Mounting {tempdir_path}.")
                mock_click_echo.assert_any_call(
                    f"Mounting result {mock_mount_result.exit_code}."
                )
                mock_click_echo.assert_called_with(
                    f"Found ostree deployment, updating INSPECT_PATH to "
                    f"{INSPECT_PATH} for {tempdir_path}."
                )
                mock_sh_mount.assert_called_once_with(
                    "-t", "auto", "-o", "ro", f"{tempdir_path}", "/mnt/inspect"
                )
            mock_click_echo.assert_any_call(f"UnMounting {tempdir_path}.")
            mock_click_echo.assert_any_call(f"Restored INSPECT_PATH to {fs_root}.")
            mock_click_echo.assert_called_with(
                f"UnMounting result {mock_umount_result.exit_code}."
            )
