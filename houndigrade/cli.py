"""Command line script for inspecting attached volumes."""
import glob
import json
import os
import subprocess
from contextlib import contextmanager
from gettext import gettext as _

import boto3
import click
import jsonpickle
from botocore.exceptions import ClientError

INSPECT_PATH = '/mnt/inspect'
RHEL_FOUND = 'rhel_found'
RHEL_PEMS = ['69.pem']
RHEL_REPOS = ['rhel', 'red hat']
RH_KEY_IDS = ['199e2f91fd431d51',
              '5326810137017186',
              '45689c882fa658e0',
              '219180cddb42a60e',
              '7514f77d8366b0d9',
              '45689c882fa658e0']


@click.command()
@click.option('--cloud',
              '-c',
              default='aws',
              help=_('Cloud in which we are performing the inspection.'),
              type=click.Choice(['aws', 'gcp', 'azure']))
@click.option('--target',
              '-t',
              multiple=True,
              type=(str, click.Path(exists=True)),
              required=True,
              help=_('Inspection target, the cloud specific image identifier'
                     ' and path to the attached drive on the machine. e.g.'
                     ' -t ami-12312839312 /dev/sda'))
@click.option('--debug',
              is_flag=True,
              help=_('Print debug output.'))
def main(cloud, target, debug):
    """
    Mounts provided volumes and inspects them.

    The script takes provided target information and checks if there are any
    partitions on that device, then it loops through, mounting every partition
    and inspecting it. As it loops through it builds a dictionary of results
    that gets placed on a queue once the processing is done.

    """
    click.echo(_('Provided cloud: {}').format(cloud))
    click.echo(_('Provided drive(s) to inspect: {}').format(target))

    results = {
        'cloud': cloud,
        'images': {},
    }

    for image_id, drive in target:
        mount_and_inspect(drive, image_id, results, debug)

    if debug:
        click.echo(json.dumps(results))

    report_results(results)


def mount_and_inspect(drive, image_id, results, debug):
    """
    Mount provided drive and inspect it.

    Args:
        drive (str): The path to the drive to mount.
        image_id (str): The id of the image we're inspecting.
        results (dict): The results of the inspection.
        debug (bool): Boolean regarding whether or not we are in debug mode.

    """
    click.echo(_('Checking drive {}').format(drive))
    results['images'][image_id] = results['images'].get(image_id, {})
    results['images'][image_id][RHEL_FOUND] = False
    results['images'][image_id]['rhel_signed_packages_found'] = \
        False
    results['images'][image_id]['rhel_product_certs_found'] = \
        False
    results['images'][image_id]['rhel_release_files_found'] = \
        False
    results['images'][image_id]['rhel_enabled_repos_found'] = \
        False
    results['images'][image_id][drive] = {}
    for partition in get_partitions(drive):
        click.echo(_('Checking partition {}').format(partition))
        rhel_release_files = {}
        rhel_product_certs = {}
        rhel_signed_packages = {}
        rhel_enabled_repos = {}
        partition_result = {
            'facts': {
                'rhel_release_files': rhel_release_files,
                'rhel_product_certs': rhel_product_certs,
                'rhel_signed_packages': rhel_signed_packages,
                'rhel_enabled_repos': rhel_enabled_repos
            }
        }
        results['images'][image_id][drive][partition] = partition_result
        try:
            with mount(partition, INSPECT_PATH):
                check_release_files(partition,
                                    rhel_release_files
                                    )
                check_for_rhel_certs(partition,
                                     rhel_product_certs
                                     )
                check_enabled_repos(partition,
                                    rhel_enabled_repos,
                                    image_id,
                                    debug
                                    )
                check_for_signed_packages(partition,
                                          rhel_signed_packages,
                                          image_id,
                                          debug
                                          )

                rhel_found = rhel_release_files[RHEL_FOUND] or \
                    rhel_product_certs[RHEL_FOUND] or \
                    rhel_enabled_repos[RHEL_FOUND] or \
                    rhel_signed_packages[RHEL_FOUND]

                results['images'][image_id][RHEL_FOUND] |= rhel_found
                results['images'][image_id]['rhel_signed_packages_found'] |= \
                    rhel_signed_packages[RHEL_FOUND]
                results['images'][image_id]['rhel_product_certs_found'] |= \
                    rhel_product_certs[RHEL_FOUND]
                results['images'][image_id]['rhel_release_files_found'] |= \
                    rhel_release_files[RHEL_FOUND]
                results['images'][image_id]['rhel_enabled_repos_found'] |= \
                    rhel_enabled_repos[RHEL_FOUND]

                if rhel_found:
                    click.echo(_('RHEL found on: {}').format(
                        image_id))
                else:
                    click.echo(_('RHEL not found on: {}').format(
                        image_id))

        except subprocess.CalledProcessError as e:
            click.echo(
                _('Mount of {} on image {} failed with error: {}').format(
                    partition, image_id, e.stderr),
                err=True
            )
            results['images'][image_id][drive][partition]['error'] = e.stderr


@contextmanager
def mount(partition, inspect_path):
    """
    Mount given partition.

    Args:
        partition (str):  The path to the partition to mount.
        inspect_path (str): The path where the partition should be mounted.

    """
    mount_result = subprocess.run([
        'mount',
        '-t',
        'auto',
        '{}'.format(partition),
        '{}'.format(inspect_path)
    ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    yield mount_result
    subprocess.run(['umount', '{}'.format(inspect_path)])


def _get_sqs_queue_url(queue_name):
    """
    Get the SQS queue URL for the given queue name.

    This has the side-effect on ensuring that the queue exists.

    Note: This function was copied verbatim from `cloudigrade`.

    FIXME: Move this function to a shared library.

    Args:
        queue_name (str): the name of the target SQS queue

    Returns:
        str: the queue's URL.

    """
    sqs = boto3.client('sqs')
    try:
        return sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    except ClientError as e:
        if e.response['Error']['Code'].endswith('.NonExistentQueue'):
            return sqs.create_queue(QueueName=queue_name)['QueueUrl']
        raise


def report_results(results):
    """
    Places the results on a queue.

    Args:
        results (dict): The results of the finished inspection.

    """
    message_body = jsonpickle.encode(results)
    queue_name = os.getenv('RESULTS_QUEUE_NAME')
    queue_url = _get_sqs_queue_url(queue_name)

    sqs = boto3.client('sqs')
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=message_body,
    )


def echo_error(debug, command, partition, image_id, error):
    """Echo an error at the debug level.

    Args:
        debug (bool): Bool regarding whether or not we are in debug mode.
        command (str): The command we are trying to run.
        partition (str): The partition we are currently checking.
        image_id (str): The image that we are currently checking.
        error (str): The error that resulted from attempting the command.
    """
    if debug:
        click.echo(
            _('The `{}` command ran on {} on image '
              '"{}" failed with error: {}').format(command,
                                                   partition,
                                                   image_id,
                                                   error),
            err=True
        )


def try_subprocess_check_output(debug, command, partition, image_id):
    """Attempt to run subprocess.check_output on the given command.

    Args:
        debug (bool): Bool regarding whether or not we are in debug mode.
        command (str): The command we are trying to run.
        partition (str): The partition we are currently checking.
        image_id (str): The image that we are currently checking.
    """
    try:
        subprocess.check_output([command],
                                stderr=subprocess.PIPE,
                                shell=True,
                                encoding='utf-8'
                                )
    except subprocess.CalledProcessError as e:
        echo_error(debug, command, partition, image_id, e.stderr)


def check_enabled_repos(partition, results, image_id, debug):
    """
    Run the chroot yum repolist enabled command to gather enabled repos.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which
        we should be writing our results.
        image_id (str): The image that we are currently checking.
        debug (bool): Bool regarding whether or not we are in debug mode.
    """
    chroot_yum_command = 'chroot {} yum repolist enabled'.format(INSPECT_PATH)
    rhel_repos = []
    prepare_new_root_dir(partition, image_id, debug)
    try:
        chroot_yum_result = subprocess.check_output([chroot_yum_command],
                                                    stderr=subprocess.PIPE,
                                                    shell=True,
                                                    encoding='utf-8'
                                                    )
        results['yum_enabled_repos_result'] = chroot_yum_result
        repo_results = chroot_yum_result.split('\n')
        rhel_repos = check_repos_for_rhel(repo_results)
        results['rhel_enabled_repos'] = rhel_repos
        if rhel_repos:
            results[RHEL_FOUND] = True
            click.echo(_('RHEL found via enabled repos on: {}').format(
                partition))
        else:
            results[RHEL_FOUND] = False
            click.echo(_('RHEL not found via enabled repos on: {}').format(
                partition))

    except subprocess.CalledProcessError as e:
        results[RHEL_FOUND] = False
        results['rhel_enabled_repos'] = rhel_repos
        results['error'] = e.stderr
        echo_error(debug, chroot_yum_command, partition, image_id, e.stderr)


def prepare_new_root_dir(partition, image_id, debug):
    """Create /dev random urandom in root dir to prepare partition for yum.

    Args:
        partition (str): The partition we are currently checking.
        image_id (str): The image that we are currently checking.
        debug (bool): Bool regarding whether or not we are in debug mode.
    """
    # The following commands attempt to create the /dev directory
    # and the kernel random number source devices (random & urandom)
    # if they do not already exist. The /dev directory & random/urandom
    # files are needed to run the yum command successfully
    # on a partition. Learn more about the random/urandom files
    # at https://linux.die.net/man/4/urandom
    mkdir = 'mkdir {}/dev'.format(INSPECT_PATH)
    mknod_random = 'mknod -m 666 {}/dev/random c 1 8'.format(INSPECT_PATH)
    mknod_urandom = 'mknod -m 666 {}/dev/urandom c 1 9'.format(INSPECT_PATH)

    try_subprocess_check_output(debug, mkdir, partition, image_id)
    try_subprocess_check_output(debug, mknod_random, partition, image_id)
    try_subprocess_check_output(debug, mknod_urandom, partition, image_id)


def check_repos_for_rhel(results):
    """
    Check the results of yum repolist enabled for RHEL repos.

    Args:
        results (list): A list of lines from the std_out of the
        yum repolist enabled command that we need to check for rhel.
    """
    result = []
    repos = []
    for line in results:
        if 'repo id' in line or 'repo name' in line:
            repos = results[results.index(line) + 1:]
    if repos:
        for line in repos:
            repo, _, remainder = line.partition(' ')
            repo_name, _, _ = remainder.rpartition(' ')
            repo = repo.strip()
            repo_name = repo_name.strip()
            for name in RHEL_REPOS:
                if name in repo_name.lower():
                    result.append({'repo': repo, 'name': repo_name})
    return result


def check_for_rhel_certs(partition, results):
    """
    Check os for rhel certificates.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.

    """
    pem_paths = glob.glob('{}/etc/pki/product/*'.format(INSPECT_PATH))
    pem_files = [(os.path.basename(os.path.normpath(pem)), pem)
                 for pem in pem_paths]
    matching_pems = [pem[1] for pem in pem_files if pem[0] in RHEL_PEMS]
    results['rhel_pem_files'] = matching_pems
    if matching_pems:
        results[RHEL_FOUND] = True
        click.echo(_('RHEL found via product certificate on: {}').format(
            partition))
    else:
        results[RHEL_FOUND] = False
        click.echo(_('RHEL not found via product certificate on: {}').format(
            partition))


def check_release_files(partition, results):
    """
    Check os release files to see if they indicate RHEL.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.

    """
    release_file_paths = find_release_files()

    if not release_file_paths:
        click.echo(_('No release files found on {}').format(partition))
        results[RHEL_FOUND] = False
        results['status'] = _('No release files found on {}').format(partition)
    else:
        for release_file_path in release_file_paths:
            rhel_found, contents = check_file(release_file_path)

            if rhel_found:
                click.echo(_('RHEL found via release file on: {}').format(
                    partition))
            else:
                click.echo(_('RHEL not found via release file on: {}').format(
                    partition))

            release_files = results.get('release_files', [])
            if release_file_path.startswith(INSPECT_PATH):
                release_file_path = release_file_path[len(INSPECT_PATH):]
            new_release_files = \
                {'rhel_release_file': release_file_path,
                 'rhel_release_file_contents': contents,
                 RHEL_FOUND: rhel_found}
            release_files.append(new_release_files)
            results[RHEL_FOUND] = \
                rhel_found or results.get(RHEL_FOUND, False)
            results['release_files'] = release_files


def check_for_signed_packages(partition, results, image_id, debug):
    """
    Check partition for redhat signed packages installed.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.
        image_id (str): The image that we are currently checking.
        debug (bool): Bool regarding whether or not we are in debug mode.

    """
    signed_rpm_count = 0
    rpm_format_statement = r'"%{DSAHEADER:pgpsig}|%{RSAHEADER:pgpsig}'\
        r'|%{SIGGPG:pgpsig}|%{SIGPGP:pgpsig}\n"'
    rh_key_id_string = r"'"
    for key_id in RH_KEY_IDS:
        rh_key_id_string += r'Key ID {}\|'.format(key_id)
    rh_key_id_string = rh_key_id_string[:-2] + "'"
    rpm_command = 'rpm -qa --dbpath={0}/var/lib/rpm/ '\
        '--qf {1} 2> /dev/null | grep {2} | wc -l'.format(
            INSPECT_PATH, rpm_format_statement, rh_key_id_string)
    try:
        rpm_result = subprocess.check_output([rpm_command],
                                             stderr=subprocess.PIPE,
                                             shell=True,
                                             encoding='utf-8'
                                             )

        signed_rpm_count = int(rpm_result.strip())
    except subprocess.CalledProcessError as e:
        results['error'] = e.stderr
        echo_error(debug, rpm_command, partition, image_id, e.stderr)
    if signed_rpm_count:
        results['rhel_found'] = True
        click.echo(_('RHEL found via signed packages on: {}').format(
            partition))
    else:
        results['rhel_found'] = False
        click.echo(_('RHEL not found via signed packages on: {}').format(
            partition))
    results['rhel_signed_package_count'] = signed_rpm_count


def find_release_files():
    """
    Look for potential release files on the mounted volume.

    Returns (list): List of file system paths that much the pattern.

    """
    return glob.glob('{}/etc/*-release'.format(INSPECT_PATH))


def get_partitions(drive):
    """
    Look for partitions belonging to an attached volume.

    Args:
        drive (str): The drive to check.

    Returns (list): List of file system paths that much the pattern.

    """
    return glob.glob('{}*[0-9]'.format(drive))


def check_file(file_path):
    """
    Check the release file to see if it indicated a RHEL OS.

    Args:
        file_path (str): Path of the file to check.

    Returns:
        boolean: Whether we think this file is from RHEL.
        file_contents (str): The contents of the release file to
        support our decision.

    """
    try:
        with open(file_path) as f:
            file_contents = f.read()
            if 'Red Hat' in file_contents:
                return True, file_contents
            else:
                return False, file_contents
    except FileNotFoundError as e:
        click.echo('{}'.format(e))
        return False, None


if __name__ == '__main__':
    main()
