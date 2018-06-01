"""Command line script for inspecting attached volumes."""
import glob
import json
import os
import subprocess
from contextlib import contextmanager
from gettext import gettext as _

import click
from kombu import Connection, Exchange, Queue

INSPECT_PATH = '/mnt/inspect'


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
        'results': {},
    }

    for image_id, drive in target:
        mount_and_inspect(drive, image_id, results)

    if debug:
        click.echo(json.dumps(results))

    report_results(results)


def mount_and_inspect(drive, image_id, results):
    """
    Mount provided drive and inspect it.

    Args:
        drive (str): The path to the drive to mount.
        image_id (str): The id of the image we're inspecting.
        results (dict): The results of the inspection.

    """
    click.echo(_('Checking drive {}').format(drive))
    results['results'][image_id] = results['results'].get(image_id, {})
    results['results'][image_id][drive] = {}
    for partition in get_partitions(drive):
        click.echo(_('Checking partition {}').format(partition))

        results['results'][image_id][drive][partition] = {}
        try:
            with mount(partition, INSPECT_PATH):
                check_release_files(
                    partition,
                    results['results'][image_id][drive][partition]
                )

        except subprocess.CalledProcessError as e:
            click.echo(
                _('Mount of {} failed with error: {}').format(
                    partition, e.stderr),
                err=True
            )
            results['results'][image_id][drive][partition]['error'] = e.stderr


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


def report_results(results):
    """
    Places the results on a queue.

    Args:
        results (dict): The results of the finished inspection.

    """
    queue_name = os.getenv('RABBITMQ_QUEUE_NAME')

    exchange = Exchange(os.getenv('RABBITMQ_EXCHANGE_NAME'), durable=True)
    queue = Queue(queue_name, exchange=exchange, routing_key=queue_name)

    with Connection(os.getenv('RABBITMQ_URL')) as conn:
        producer = conn.Producer(serializer='json')
        producer.publish(
            results,
            exchange=exchange,
            routing_key=queue_name,
            declare=[queue]
        )


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
        results['rhel_found'] = False
        results['status'] = _('No release files found on {}').format(partition)
    else:
        for release_file_path in release_file_paths:
            rhel_found, contents = check_file(release_file_path)

            if rhel_found:
                click.echo(_('RHEL found on: {}').format(partition))
            else:
                click.echo(_('RHEL not found on: {}').format(partition))

            evidence = results.get('evidence', [])
            new_evidence = \
                {'release_file': release_file_path,
                 'release_file_contents': contents,
                 'rhel_found': rhel_found}
            evidence.append(new_evidence)
            results['rhel_found'] = \
                rhel_found or results.get('rhel_found', False)
            results['evidence'] = evidence


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
