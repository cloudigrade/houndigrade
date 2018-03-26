"""Collection of tests for ``cli`` module."""
import pathlib
from unittest import TestCase
from unittest.mock import call, patch

from subprocess import CalledProcessError
from click.testing import CliRunner

from cli import main


class TestCLI(TestCase):
    def test_cli_no_options(self):
        runner = CliRunner()
        result = runner.invoke(main)

        self.assertEqual(result.exit_code, 2)
        self.assertIn(
            'Error: Missing option "--target" / "-t".', result.output)

    @patch('cli.Connection')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    def test_cli_happy_path(self, mock_subprocess_run, mock_glob_glob,
                            mock_connection):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return ['./dev/xvdf/xvdf1/etc/redhat-release',
                        './dev/xvdf/xvdf1/etc/os-release',
                        './dev/xvdf/xvdf2/etc/centos-release',
                        './dev/xvdf/xvdf2/etc/os-release', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect

        mock_with_conn = mock_connection.return_value.__enter__.return_value
        mock_producer = mock_with_conn.Producer.return_value
        mock_pub = mock_producer.publish
        mock_pub.return_value = True

        runner = CliRunner()

        with runner.isolated_filesystem():
            self.prep_fs(drive_path)

            result = runner.invoke(main,
                                   ['-c', cloud, '--debug', '-t', image_id, drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(mock_subprocess_run.call_count, 4)

        mock_subprocess_run.assert_has_calls([
            call(['mount', '-t', 'auto', './dev/xvdf1', '/mnt/inspect'],
                 check=True, stderr=-1, stdout=-1, universal_newlines=True),
            call(['umount', '/mnt/inspect']),
            call(['mount', '-t', 'auto', './dev/xvdf2', '/mnt/inspect'],
                 check=True, stderr=-1, stdout=-1, universal_newlines=True),
            call(['umount', '/mnt/inspect']),
        ])

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"cloud": "aws"', result.output)
        self.assertIn(
            '"inspection_targets": [["ami-123456789", "./dev/xvdf"]]',
            result.output
        )

        self.assertEqual(len(mock_with_conn.method_calls), 1)
        self.assertEqual(mock_with_conn.method_calls[0],
                         call.Producer(serializer='json'))
        self.assertEqual(len(mock_producer.method_calls), 1)
        self.assertTrue(mock_pub.called)

    @patch('cli.Connection')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    def test_cli_disappearing_files(self, mock_subprocess_run, mock_glob_glob,
                                    mock_connection):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return ['./dev/xvdf/xvdf1/etc/redhat-release',
                        './dev/xvdf/xvdf1/etc/os-release',
                        './dev/xvdf/xvdf2/etc/centos-release',
                        './dev/xvdf/xvdf2/etc/os-release', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect

        mock_with_conn = mock_connection.__enter__.return_value
        mock_producer = mock_with_conn.Producer.return_value
        mock_pub = mock_producer.publish
        mock_pub.return_value = True

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path('{}/xvdf1'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
            result = runner.invoke(main,
                                   ['-c', cloud, '--debug', '-t', image_id,
                                    drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(' No such file or directory', result.output)

    @patch('cli.Connection')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    def test_cli_no_version_files(self, mock_subprocess_run, mock_glob_glob,
                                  mock_connection):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return []
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect

        mock_with_conn = mock_connection.__enter__.return_value
        mock_producer = mock_with_conn.Producer.return_value
        mock_pub = mock_producer.publish
        mock_pub.return_value = True

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path('{}/xvdf1'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
            result = runner.invoke(main,
                                   ['-c', cloud, '--debug', '-t', image_id,
                                    drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn(
            '"status": "No release files found on ./dev/xvdf1"', result.output)
        self.assertIn(
            '"status": "No release files found on ./dev/xvdf2"', result.output)

    @patch('cli.Connection')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    def test_failed_mount(self, mock_subprocess_run, mock_glob_glob, mock_con):
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'

        e = CalledProcessError(1, 'mount', stderr='Mount failed.')

        mock_subprocess_run.side_effect = e

        def mock_glob_side_effect(pattern):
            return ['./dev/xvdf1']

        mock_glob_glob.side_effect = mock_glob_side_effect

        mock_with_conn = mock_con.return_value__enter__.return_value
        mock_producer = mock_with_conn.Producer.return_value
        mock_pub = mock_producer.publish
        mock_pub.return_value = True

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path('{}/xvdf1'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
            result = runner.invoke(main, ['-t', image_id, drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual('Mount failed.',
                      mock_con.mock_calls[3][1][0]['facts']['./dev/xvdf'][
                          './dev/xvdf1'][0]['error'])

    @staticmethod
    def prep_fs(drive_path):
        pathlib.Path('{}/xvdf1/etc'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
        pathlib.Path('{}/xvdf2/etc'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)

        with open('{}/xvdf1/etc/redhat-release'.format(drive_path), 'w') as f:
            f.write('Red Hat Enterprise Linux Server release 7.4 (Maipo)\n')
        with open('{}/xvdf1/etc/os-release'.format(drive_path), 'w') as f:
            f.write('NAME=\"Red Hat Enterprise Linux Server\"\nVERSION=\"7.4 '
                    '(Maipo)\"\nID=\"rhel\"\nID_LIKE=\"fedora\"\nVARIANT'
                    '=\"Server\"\nVARIANT_ID=\"server\"\nVERSION_ID=\"7.4'
                    '\"\nPRETTY_NAME=\"Red Hat Enterprise Linux Server 7.4 ('
                    'Maipo)\"\nANSI_COLOR=\"0;31\"\nCPE_NAME=\"cpe:/o:redhat'
                    ':enterprise_linux:7.4:GA:server\"\nHOME_URL=\"https'
                    '://www.redhat.com/\"\nBUG_REPORT_URL=\"https://bugzilla'
                    '.redhat.com/\"\n\nREDHAT_BUGZILLA_PRODUCT=\"Red Hat '
                    'Enterprise Linux '
                    '7\"\nREDHAT_BUGZILLA_PRODUCT_VERSION=7.4'
                    '\nREDHAT_SUPPORT_PRODUCT=\"Red Hat Enterprise '
                    'Linux\"\nREDHAT_SUPPORT_PRODUCT_VERSION=\"7.4\"\n')

        with open('{}/xvdf2/etc/centos-release'.format(drive_path), 'w') as f:
            f.write('CentOS Linux release 7.4.1708 (Core) \n')
        with open('{}/xvdf2/etc/os-release'.format(drive_path), 'w') as f:
            f.write('NAME=\"CentOS Linux\"\nVERSION=\"7 ('
                    'Core)\"\nID=\"centos\"\nID_LIKE=\"rhel '
                    'fedora\"\nVERSION_ID=\"7\"\nPRETTY_NAME=\"CentOS Linux '
                    '7 (Core)\"\nANSI_COLOR=\"0;31\"\nCPE_NAME=\"cpe:/o'
                    ':centos:centos:7\"\nHOME_URL=\"https://www.centos.org'
                    '/\"\nBUG_REPORT_URL=\"https://bugs.centos.org/\"\n'
                    '\nCENTOS_MANTISBT_PROJECT=\"CentOS-7'
                    '\"\nCENTOS_MANTISBT_PROJECT_VERSION=\"7'
                    '\"\nREDHAT_SUPPORT_PRODUCT=\"centos'
                    '\"\nREDHAT_SUPPORT_PRODUCT_VERSION=\"7\"\n\n')
