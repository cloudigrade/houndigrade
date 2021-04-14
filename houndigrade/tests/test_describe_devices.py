"""Collection of tests for ``cli.describe_devices`` function."""
from itertools import chain
from unittest import TestCase
from unittest.mock import Mock, call, patch


class TestDescribeDevices(TestCase):
    """Test suite for houndigrade CLI's "describe_devices" function."""

    @patch("cli.get_partitions")
    @patch("cli.sh")
    def test_describe_devices(
        self, mock_sh, mock_get_partitions,
    ):
        """Assert various expected sh calls for describe_devices."""
        from cli import describe_devices

        amis = ("ami-potato", "ami-gems")
        drives = ("/dev/xvdp", "/dev/xvdg")
        targets = zip(amis, drives)
        partitions = (("/dev/xvdp1", "/dev/xvdp2"), ("/dev/xvdg1",))

        mock_get_partitions.side_effect = partitions
        expected_get_partition_calls = [call(drive) for drive in drives]

        mock_sh.fdisk.return_value = Mock()  # necessary due to how click.echo wraps it
        expected_fdisk_calls = [call("-l", drive) for drive in drives]

        udevadm_info_path = "/some/other/path"
        mock_sh.udevadm.return_value = udevadm_info_path
        expected_udevadm_calls = list(
            # from_iterable flattens the nested lists to a single list of calls
            chain.from_iterable(
                [
                    [
                        call("info", "-q", "path", "-n", partition),
                        call("test", "-a", "-p", udevadm_info_path),
                        call("info", "--query=all", f"--name={partition}"),
                    ]
                    for partition in chain.from_iterable(partitions)
                ]
            )
        )

        mock_sh.lsblk.return_value = Mock()  # necessary due to how click.echo wraps it
        expected_lsblk_calls = [
            call(
                "--all",
                "--ascii",
                "--output",
                "NAME,TYPE,FSTYPE,PARTLABEL,MOUNTPOINT",
                drive,
            )
            for drive in drives
        ]

        describe_devices(targets)
        mock_get_partitions.assert_has_calls(expected_get_partition_calls)
        mock_sh.pvs.assert_called_once()
        mock_sh.fdisk.assert_has_calls(expected_fdisk_calls)
        mock_sh.udevadm.assert_has_calls(expected_udevadm_calls)
        mock_sh.lsblk.assert_has_calls(expected_lsblk_calls)
