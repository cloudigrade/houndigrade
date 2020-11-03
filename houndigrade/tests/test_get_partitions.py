"""Collection of tests for ``cli.get_partitions`` function."""
from unittest import TestCase
from unittest.mock import patch

from cli import get_partitions


class TestGetPartitions(TestCase):
    """Test suite for houndigrade CLI's "get_partitions" function."""

    @patch("cli.sh.vgscan", create=True)
    @patch("cli.sh.lvscan", create=True)
    @patch("cli.sh.vgchange", create=True)
    @patch("cli.glob")
    @patch("cli.click")
    @patch("cli.sh.blkid", create=True)
    def test_find_partitions(
        self, mock_blkid, mock_click, mock_glob, mock_vgchange, mock_lvscan, mock_vgscan
    ):
        """Find partitions on a partitioned drive."""
        mock_blkid.return_value = (
            "OH\\nG\\OD+HOW&DID*THIS$GET^HEREIM=NOT&"
            "GOOD(WITH)=COMPUTER\nPTTYPE=gpt\nPOTATO=seven\n"
        )
        mock_click_echo = mock_click.echo
        mock_glob = mock_glob.glob
        expected_partitions = ["/dev/xvda1", "/dev/xvda2", "/dev/xvda3"]
        mock_glob.return_value = ["/dev/xvda3", "/dev/xvda1", "/dev/xvda2"]

        partitions = get_partitions(drive := "/dev/xvda")

        mock_blkid.assert_called_once_with("-p", "-o", "export", drive)
        mock_vgchange.assert_called_once_with("-a", "y")
        mock_lvscan.assert_called_once()
        mock_vgscan.assert_called_once()
        mock_click_echo.assert_called_with(
            "Device appears to have partitions, PTTYPE: gpt"
        )
        mock_glob.assert_called_once_with("/dev/xvda*[0-9]")
        self.assertEqual(partitions, expected_partitions)

    @patch("cli.sh.vgscan", create=True)
    @patch("cli.sh.lvscan", create=True)
    @patch("cli.sh.vgchange", create=True)
    @patch("cli.glob")
    @patch("cli.click")
    @patch("cli.sh.blkid", create=True)
    def test_find_no_partitions(
        self, mock_blkid, mock_click, mock_glob, mock_vgchange, mock_lvscan, mock_vgscan
    ):
        """Use device path for devices lacking a partition table."""
        mock_blkid.return_value = "TYPE=xfs\nPOTATO=seven\nUSAGE=filesystem\n"
        mock_click_echo = mock_click.echo
        mock_glob = mock_glob.glob
        expected_partitions = ["/dev/xvda"]
        mock_glob.return_value = ["/dev/xvda"]

        partitions = get_partitions(drive := "/dev/xvda")

        mock_blkid.assert_called_once_with("-p", "-o", "export", drive)
        mock_vgchange.assert_called_once_with("-a", "y")
        mock_lvscan.assert_called_once()
        mock_vgscan.assert_called_once()
        mock_click_echo.assert_called_with(
            "Device appears to lack a partition table, type: xfs"
        )
        mock_glob.assert_called_once_with("/dev/xvda*")
        self.assertEqual(partitions, expected_partitions)

    @patch("cli.sh.vgscan", create=True)
    @patch("cli.sh.lvscan", create=True)
    @patch("cli.sh.vgchange", create=True)
    @patch("cli.glob")
    @patch("cli.click")
    @patch("cli.sh.blkid", create=True)
    def test_no_idea(
        self, mock_blkid, mock_click, mock_glob, mock_vgchange, mock_lvscan, mock_vgscan
    ):
        """Fallback when we do not know what the device is."""
        mock_blkid.return_value = (
            "MINIMUM_IO_SIZE=512\nPHYSICAL_SECTOR_SIZE=512\nLOGICAL_SECTOR_SIZE=512"
        )
        mock_click_echo = mock_click.echo
        mock_glob = mock_glob.glob
        expected_partitions = ["/dev/xvda"]
        mock_glob.return_value = ["/dev/xvda"]

        partitions = get_partitions(drive := "/dev/xvda")

        mock_blkid.assert_called_once_with("-p", "-o", "export", drive)
        mock_vgchange.assert_called_once_with("-a", "y")
        mock_lvscan.assert_called_once()
        mock_vgscan.assert_called_once()
        mock_click_echo.assert_called_with(
            "We're not sure what this device is, assuming "
            "lack of partition table, blkid output:\n"
            "{'MINIMUM_IO_SIZE': '512', 'PHYSICAL_SECTOR_SIZE': '512', "
            "'LOGICAL_SECTOR_SIZE': '512'}"
        )
        mock_glob.assert_called_once_with("/dev/xvda*")
        self.assertEqual(partitions, expected_partitions)
