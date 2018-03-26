"""Command line script for inspecting attached volumes."""
import glob
import json
import os
import subprocess
from gettext import gettext as _

import click
from kombu import Connection, Exchange, Queue

INSPECT_PATH = '/mnt/inspect'


@click.command()
@click.option('--cloud',
              '-c',
              default='aws',
              help='Cloud in which we are performing the inspection.',
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
    r"""
    Mounts provided volumes and inspects them.

    The script takes provided target information and checks if there are any
    partitions on that device, then it loops through, mounting every partition
    and inspecting it. As it loops through it builds a dictionary of results
    that gets placed on a queue once the processing is done.

    \b
    Args:
        cloud (str): Cloud in which we are performing the inspection.
        target (str): Inspection target, the cloud specific image identifier
                      and path to the attached drive on the machine.
        debug (boolean): Boolean flag that turns on debug output.

    """
    click.echo(_('Provided cloud: {}'.format(cloud)))
    click.echo(_('Provided drive(s) to inspect: {}'.format(target)))

    results = {
        'cloud': cloud,
        'inspection_targets': target,
        'facts': {},
    }

    for image_id, drive in target:
        click.echo('Checking drive {}'.format(drive))

        results['facts'][drive] = {'image_id': image_id}
        for partition in get_partitions(drive):
            click.echo('Checking partition {}'.format(partition))

            results['facts'][drive][partition] = []
            try:
                subprocess.run([
                    'mount',
                    '-t',
                    'auto',
                    '{}'.format(partition),
                    '{}'.format(INSPECT_PATH)
                ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
            except subprocess.CalledProcessError as e:
                click.echo(
                    _('Mount of {} failed '
                      'with error: {}'.format(partition, e.stderr)),
                    err=True
                )

                results['facts'][drive][partition].append({
                    'error': e.stderr
                })

                continue

            check_release_files(partition, results['facts'][drive][partition])

            click.echo('Unmounting partition: {}'.format(partition))
            subprocess.run(['umount', '{}'.format(INSPECT_PATH)])

    if debug:
        click.echo(json.dumps(results))

    report_results(results)


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
        results (list): Part of the results dict to which we should be
        writing our results.

    """
    release_file_paths = find_release_files()

    if not release_file_paths:
        click.echo('No release files found on {}'.format(partition))
        results.append({
            'rhel_found': False,
            'status': 'No release files found on {}'.format(partition)
        })
    else:
        for release_file_path in release_file_paths:
            rhel_found, file = check_file(release_file_path)

            if rhel_found:
                click.echo('RHEL found on: {}'.format(partition))
            else:
                click.echo('RHEL not found on: {}'.format(partition))

            results.append({
                'rhel_found': rhel_found,
                'release_file': release_file_path,
                'release_file_contents': file
            })


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
        file (str): The contents of the release file to support our decision.

    """
    try:
        with open(file_path) as f:
            file = f.read()
            if 'Red Hat' in file:
                return True, file
            else:
                return False, file
    except FileNotFoundError as e:
        click.echo('{}'.format(e))
        return False, None


if __name__ == '__main__':
    main()
