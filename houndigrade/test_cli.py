"""Collection of tests for ``cli`` module."""
import pathlib
from textwrap import dedent
from unittest import TestCase
from unittest.mock import call, patch, Mock
from gettext import gettext as _

from botocore.exceptions import ClientError
from subprocess import CalledProcessError
from click.testing import CliRunner

from cli import _get_sqs_queue_url, main


class TestCLI(TestCase):
    def test_cli_no_options(self):
        runner = CliRunner()
        result = runner.invoke(main)

        self.assertEqual(result.exit_code, 2)
        self.assertIn(
            'Error: Missing option "--target" / "-t".', result.output)

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    @patch('cli.prepare_new_root_dir')
    def test_rhel_found_multiple_ways(self, mock_prepare_new_root_dir, mock_subprocess_check_output,
                                      mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        rhel_repo_result = '\nrepo id repo name\njb-eap-7-for-rhel-7-server-rpms/$releasever/x86_64 JBoss Enterprise Appli 0\nrhel-7-server-rpms/$releasever/x86_64 Red Hat Enterprise Lin 0\nrhel7-cdn-internal/$releasever/x86_64 RHEL 7 - x86_64 0\n'
        no_repo_result = '\n'
        rhel_packages_result = '448\n'
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return ['./dev/xvdf/xvdf1/etc/redhat-release',
                        './dev/xvdf/xvdf1/etc/os-release',
                        './dev/xvdf/xvdf2/etc/centos-release',
                        './dev/xvdf/xvdf2/etc/os-release', ]
            elif '/etc/pki/product/*' in pattern:
                return ['./dev/xvdf/xvdf1/etc/pki/product/69.pem', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_prepare_new_root_dir.return_value = None
        mock_subprocess_check_output.side_effect = [rhel_repo_result, rhel_packages_result,
                                                    no_repo_result, no_packages_result]

        runner = CliRunner()

        with runner.isolated_filesystem():
            self.prep_fs(drive_path)

            result = runner.invoke(
                main,
                ['-c', cloud, '--debug', '-t', image_id, drive_path]
            )

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(mock_subprocess_run.call_count, 4)

        mock_subprocess_run.assert_has_calls(
            [call(['mount', '-t', 'auto', './dev/xvdf1', '/mnt/inspect'], check=True, stderr=-1, stdout=-1, universal_newlines=True),
             call(['umount', '/mnt/inspect']),
             call(['mount', '-t', 'auto', './dev/xvdf2', '/mnt/inspect'], check=True, stderr=-1, stdout=-1, universal_newlines=True),
             call(['umount', '/mnt/inspect']) ]
        )
        self.assertEqual(result.exit_code, 0)
        self.assertIn('"cloud": "aws"', result.output)
        self.assertIn('"ami-123456789"', result.output)
        self.assertIn('RHEL found via release file on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL found via product certificate on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL found via signed packages on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via release file on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL found via product certificate on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL found via release file on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL found on: ami-1234567', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertTrue(results['images'][image_id]['rhel_found'])
        self.assertTrue(results['images'][image_id]['rhel_signed_packages_found'])
        self.assertTrue(results['images'][image_id]['rhel_enabled_repos_found'])
        self.assertTrue(results['images'][image_id]['rhel_product_certs_found'])
        self.assertTrue(results['images'][image_id]['rhel_release_files_found'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    @patch('cli.prepare_new_root_dir')
    def test_cli_disappearing_files(self, mock_prepare_new_root_dir, mock_subprocess_check_output,
                                    mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        no_repo_result = '\n'
        e = CalledProcessError(1, 'chroot yum repolist enabled',
                               stderr='chroot: failed to run command \xe2\x80\x98yum\xe2\x80\x99: No such file or directory\n')
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return ['./dev/xvdf/xvdf1/etc/redhat-release',
                        './dev/xvdf/xvdf1/etc/os-release',
                        './dev/xvdf/xvdf2/etc/centos-release',
                        './dev/xvdf/xvdf2/etc/os-release', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_prepare_new_root_dir.return_value = None
        mock_subprocess_check_output.side_effect = [no_repo_result, no_packages_result,
                                                    e, no_packages_result]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path('{}/xvdf1'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
            result = runner.invoke(main,
                                   ['-c', cloud, '--debug', '-t', image_id,
                                    drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn('No such file or directory', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    def test_cli_no_version_files(self, mock_subprocess_check_output,
                                  mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        no_repo_result = '\n'
        e = CalledProcessError(1, 'chroot yum repolist enabled',
                               stderr='chroot: failed to run command \xe2\x80\x98yum\xe2\x80\x99: No such file or directory\n')
        no_packages_result = '0\n'
        mkdir_e = CalledProcessError(1, 'mkdir /dev',
                               stderr='mkdir: failed to create directory \xe2\x80\x98/dev\xe2\x80\x99: File exists\n')

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return []
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [mkdir_e, mkdir_e, mkdir_e, no_repo_result, no_packages_result,
                                                    mkdir_e, mkdir_e, mkdir_e, e, no_packages_result]

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
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf1'))),
            result.output)
        self.assertIn(
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf2'))),
            result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    @patch('cli.prepare_new_root_dir')
    def test_rhel_not_found(self, mock_prepare_new_root_dir, mock_subprocess_check_output,
                            mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        no_repo_result = '\n'
        e = CalledProcessError(1, 'chroot yum repolist enabled', stderr='chroot: failed to run command \xe2\x80\x98yum\xe2\x80\x99: No such file or directory\n')
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return []
            elif '/etc/pki/product/*' in pattern:
                return ['./dev/xvdf/xvdf2/etc/pki/product/185.pem', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_prepare_new_root_dir.return_value = None
        mock_subprocess_check_output.side_effect = [no_repo_result, no_packages_result,
                                                    e, no_packages_result]

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path('{}/xvdf1'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
            result = runner.invoke(main,
                                   ['-c', cloud, '--debug', '-t', image_id,
                                    drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(mock_subprocess_run.call_count, 4)

        mock_subprocess_run.assert_has_calls(
            [call(['mount', '-t', 'auto', './dev/xvdf1', '/mnt/inspect'], check=True, stderr=-1, stdout=-1,
                  universal_newlines=True),
             call(['umount', '/mnt/inspect']),
             call(['mount', '-t', 'auto', './dev/xvdf2', '/mnt/inspect'], check=True, stderr=-1, stdout=-1,
                  universal_newlines=True),
             call(['umount', '/mnt/inspect'])]
        )
        self.assertIn(
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf1'))),
            result.output)
        self.assertIn(
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf2'))),
            result.output)
        self.assertIn('RHEL not found on: ami-1234567', result.output)
        self.assertIn('The `chroot /mnt/inspect yum repolist enabled` command ran on ./dev/xvdf2 on image "ami-123456789" failed with error: chroot: ', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf2', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertFalse(results['images'][image_id]['rhel_found'])
        self.assertFalse(results['images'][image_id]['rhel_signed_packages_found'])
        self.assertFalse(results['images'][image_id]['rhel_enabled_repos_found'])
        self.assertFalse(results['images'][image_id]['rhel_product_certs_found'])
        self.assertFalse(results['images'][image_id]['rhel_release_files_found'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    def test_rhel_found_via_enabled_repos(self, mock_subprocess_check_output,
                                          mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        rhel_repo_result = '\nrepo id repo name\njb-eap-7-for-rhel-7-server-rpms/$releasever/x86_64 JBoss Enterprise Appli 0\nrhel-7-server-rpms/$releasever/x86_64 Red Hat Enterprise Lin 0\nrhel7-cdn-internal/$releasever/x86_64 RHEL 7 - x86_64 0\n'
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return []
            elif '/etc/pki/product/*' in pattern:
                return ['./dev/xvdf/xvdf2/etc/pki/product/185.pem', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_subprocess_check_output.side_effect = [None, None, None, rhel_repo_result, no_packages_result,
                                                    None, None, None, rhel_repo_result, no_packages_result]

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
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf1'))),
            result.output)
        self.assertIn(
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf2'))),
            result.output)
        self.assertIn('RHEL found on: ami-1234567', result.output)
        self.assertIn('RHEL found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL found via enabled repos on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf2', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertTrue(results['images'][image_id]['rhel_found'])
        self.assertFalse(results['images'][image_id]['rhel_signed_packages_found'])
        self.assertTrue(results['images'][image_id]['rhel_enabled_repos_found'])
        self.assertFalse(results['images'][image_id]['rhel_product_certs_found'])
        self.assertFalse(results['images'][image_id]['rhel_release_files_found'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    @patch('cli.prepare_new_root_dir')
    def test_rhel_found_via_signed_package(self, mock_prepare_new_root_dir, mock_subprocess_check_output,
                                           mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        no_repo_result = '\n'
        rhel_packages_result = '1\n'
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return []
            elif '/etc/pki/product/*' in pattern:
                return ['./dev/xvdf/xvdf2/etc/pki/product/185.pem', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_prepare_new_root_dir.return_value = None
        mock_subprocess_check_output.side_effect = [no_repo_result, rhel_packages_result,
                                                    no_repo_result, no_packages_result]

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
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf1'))),
            result.output)
        self.assertIn(
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf2'))),
            result.output)
        self.assertIn('RHEL found on: ami-1234567', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL found via signed packages on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf2', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertTrue(results['images'][image_id]['rhel_found'])
        self.assertTrue(results['images'][image_id]['rhel_signed_packages_found'])
        self.assertFalse(results['images'][image_id]['rhel_enabled_repos_found'])
        self.assertFalse(results['images'][image_id]['rhel_product_certs_found'])
        self.assertFalse(results['images'][image_id]['rhel_release_files_found'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    @patch('cli.prepare_new_root_dir')
    def test_rhel_found_via_product_cert(self, mock_prepare_new_root_dir, mock_subprocess_check_output,
                                         mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        no_repo_result = '\n'
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return []
            elif '/etc/pki/product/*' in pattern:
                return ['./dev/xvdf/xvdf1/etc/pki/product/69.pem',
                        './dev/xvdf/xvdf2/etc/pki/product/185.pem', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_prepare_new_root_dir.return_value = None
        mock_subprocess_check_output.side_effect = [no_repo_result, no_packages_result,
                                                    no_repo_result, no_packages_result]

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
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf1'))),
            result.output)
        self.assertIn(
            '"status": "{}"'.format(
                _('No release files found on {}'.format('./dev/xvdf2'))),
            result.output)
        self.assertIn('RHEL found on: ami-1234567', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL found via product certificate on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL found via product certificate on: ./dev/xvdf2', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertTrue(results['images'][image_id]['rhel_found'])
        self.assertFalse(results['images'][image_id]['rhel_signed_packages_found'])
        self.assertFalse(results['images'][image_id]['rhel_enabled_repos_found'])
        self.assertTrue(results['images'][image_id]['rhel_product_certs_found'])
        self.assertFalse(results['images'][image_id]['rhel_release_files_found'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    @patch('cli.subprocess.check_output')
    @patch('cli.prepare_new_root_dir')
    def test_rhel_found_via_release_file(self, mock_prepare_new_root_dir, mock_subprocess_check_output,
                                         mock_subprocess_run, mock_glob_glob, mock_report_results):
        cloud = 'aws'
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'
        no_repo_result = '\n'
        no_packages_result = '0\n'

        def mock_glob_side_effect(pattern):
            if 'etc/*-release' in pattern:
                return ['./dev/xvdf/xvdf1/etc/redhat-release',
                        './dev/xvdf/xvdf1/etc/os-release',
                        './dev/xvdf/xvdf2/etc/centos-release',
                        './dev/xvdf/xvdf2/etc/os-release', ]
            elif '/etc/pki/product/*' in pattern:
                return ['./dev/xvdf/xvdf2/etc/pki/product/185.pem', ]
            else:
                return ['./dev/xvdf1', './dev/xvdf2', ]

        mock_glob_glob.side_effect = mock_glob_side_effect
        mock_prepare_new_root_dir.return_value = None
        mock_subprocess_check_output.side_effect = [no_repo_result, no_packages_result,
                                                    no_repo_result, no_packages_result]

        runner = CliRunner()

        with runner.isolated_filesystem():
            self.prep_fs(drive_path)
            result = runner.invoke(main,
                                   ['-c', cloud, '--debug', '-t', image_id,
                                    drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)
        self.assertIn('RHEL found on: ami-1234567', result.output)
        self.assertIn('RHEL found via release file on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf1', result.output)
        self.assertIn('RHEL not found via release file on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via enabled repos on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via signed packages on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL not found via product certificate on: ./dev/xvdf2', result.output)
        self.assertIn('RHEL found via release file on: ./dev/xvdf2', result.output)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertTrue(results['images'][image_id]['rhel_found'])
        self.assertFalse(results['images'][image_id]['rhel_signed_packages_found'])
        self.assertFalse(results['images'][image_id]['rhel_enabled_repos_found'])
        self.assertFalse(results['images'][image_id]['rhel_product_certs_found'])
        self.assertTrue(results['images'][image_id]['rhel_release_files_found'])

    @patch('cli.report_results')
    @patch('cli.glob.glob')
    @patch('cli.subprocess.run')
    def test_failed_mount(self, mock_subprocess_run, mock_glob_glob,
                          mock_report_results):
        image_id = 'ami-123456789'
        drive_path = './dev/xvdf'

        e = CalledProcessError(1, 'mount', stderr='Mount failed.')

        mock_subprocess_run.side_effect = e

        def mock_glob_side_effect(pattern):
            return ['./dev/xvdf1']

        mock_glob_glob.side_effect = mock_glob_side_effect

        runner = CliRunner()

        with runner.isolated_filesystem():
            pathlib.Path('{}/xvdf1'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
            result = runner.invoke(main, ['-t', image_id, drive_path])

        self.assertTrue(mock_subprocess_run.called)
        self.assertEqual(result.exit_code, 0)

        mock_report_results.assert_called_once()
        results = mock_report_results.call_args[0][0]
        self.assertIn('cloud', results)
        self.assertIn('images', results)
        self.assertIn(image_id, results['images'])
        self.assertEqual(
            'Mount failed.',
            results['images'][image_id]['./dev/xvdf']['./dev/xvdf1']['error']
        )

    @staticmethod
    def prep_fs(drive_path):
        pathlib.Path('{}/xvdf1/etc'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)
        pathlib.Path('{}/xvdf2/etc'.format(drive_path)).mkdir(parents=True,
                                                              exist_ok=True)

        redhat_release = 'Red Hat Enterprise Linux Server release 7.4 (' \
                         'Maipo)\n'
        centos_release = 'CentOS Linux release 7.4.1708 (Core)\n'

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

        with open('{}/xvdf1/etc/redhat-release'.format(drive_path), 'w') as f:
            f.write(redhat_release)
        with open('{}/xvdf1/etc/os-release'.format(drive_path), 'w') as f:
            f.write(dedent(rh_os_release))

        with open('{}/xvdf2/etc/centos-release'.format(drive_path), 'w') as f:
            f.write(centos_release)
        with open('{}/xvdf2/etc/os-release'.format(drive_path), 'w') as f:
            f.write(dedent(centos_os_release))

    @patch('cli.boto3')
    def test_get_sqs_queue_url_for_existing_queue(self, mock_boto3):
        """
        Test getting URL for existing SQS queue.

        Note: This function was copied verbatim from `cloudigrade`.

        FIXME: Move this function to a shared library.
        """
        mock_client = mock_boto3.client.return_value
        queue_name = Mock()
        expected_url = Mock()
        mock_client.get_queue_url.return_value = {'QueueUrl': expected_url}
        queue_url = _get_sqs_queue_url(queue_name)
        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)

    @patch('cli.boto3')
    def test_get_sqs_queue_url_creates_new_queue(self, mock_boto3):
        """
        Test getting URL for a SQS queue that does not yet exist.

        Note: This function was copied verbatim from `cloudigrade`.

        FIXME: Move this function to a shared library.
        """
        mock_client = mock_boto3.client.return_value
        queue_name = Mock()
        expected_url = Mock()
        error_response = {
            'Error': {
                'Code': '.NonExistentQueue'
            }
        }
        exception = ClientError(error_response, Mock())
        mock_client.get_queue_url.side_effect = exception
        mock_client.create_queue.return_value = {'QueueUrl': expected_url}
        queue_url = _get_sqs_queue_url(queue_name)
        self.assertEqual(queue_url, expected_url)
        mock_client.get_queue_url.assert_called_with(QueueName=queue_name)
        mock_client.create_queue.assert_called_with(QueueName=queue_name)
