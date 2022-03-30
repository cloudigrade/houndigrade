"""Command line script for inspecting attached volumes."""
import configparser
import csv
import glob
import json
import os
import subprocess
import sys
from base64 import b64encode
from contextlib import contextmanager
from datetime import datetime
from gettext import gettext as _
from hashlib import md5
from uuid import uuid4

import boto3
import click
import jsonpickle
import sh
from sentry_sdk import init

INSPECT_PATH = "/mnt/inspect"
RHEL_FOUND = "rhel_found"
RHEL_PEMS = ["69.pem", "479.pem"]
CERT_PATHS = ["/etc/pki/product/", "/etc/pki/product-default/"]
RHEL_REPOS = ["rhel", "red hat"]
RH_KEY_IDS = [
    "199e2f91fd431d51",
    "5326810137017186",
    "45689c882fa658e0",
    "219180cddb42a60e",
    "7514f77d8366b0d9",
    "45689c882fa658e0",
]
SYSPURPOSE_FILESIZE_LIMIT = 1024


@click.command()
@click.option(
    "--cloud",
    "-c",
    default="aws",
    help=_("Cloud in which we are performing the inspection."),
    type=click.Choice(["aws", "gcp", "azure"]),
)
@click.option(
    "--target",
    "-t",
    multiple=True,
    type=(str, click.Path()),
    required=True,
    help=_(
        "Inspection target, the cloud specific image identifier"
        " and path to the attached drive on the machine. e.g."
        " -t ami-12312839312 /dev/sda"
    ),
)
def main(cloud, target):
    """
    Mounts provided volumes and inspects them.

    The script takes provided target information and checks if there are any
    partitions on that device, then it loops through, mounting every partition
    and inspecting it. As it loops through it builds a dictionary of results
    that gets placed on a queue once the processing is done.

    """
    click.echo(_("Provided cloud: {}").format(cloud))
    click.echo(_("Provided drive(s) to inspect: {}").format(target))
    describe_devices(target)

    results = {"cloud": cloud, "images": {}, "errors": []}

    for image_id, drive in target:
        mount_and_inspect(drive, image_id, results)

    click.echo(jsonpickle.encode(results))

    click.echo(_("Reporting results."))
    report_results(results)
    click.echo(_("Results reported. Exiting"))

    sys.exit(0)


def describe_devices(target):
    """Describe all devices for diagnosing general issues."""
    try:
        all_devices = os.listdir("/dev/")
        click.echo(_("/dev/ contains: {}").format(all_devices))
        click.echo(sh.pvs("-a"))

        for image_id, drive in target:
            click.echo(
                _("General information about device {drive} for {image_id}:").format(
                    drive=drive, image_id=image_id
                )
            )
            click.echo(str(sh.fdisk("-l", drive)))

            # Because udev device initialization is weird in Docker, we have to "test"
            # each partition before we can see useful details about their filesystems.
            # Because udev data is used under the covers by lsblk, this test also needs
            # to happen before calling lsblk.
            partitions = get_partitions(drive)
            for partition in partitions:
                # get the "/devices/..." block path
                device_block_path = sh.udevadm("info", "-q", "path", "-n", partition)
                # test the device on that path so udev refreshes its knowledge
                sh.udevadm("test", "-a", "-p", device_block_path.strip())
                # then we can ask for info and hopefully get a useful response
                click.echo(sh.udevadm("info", "--query=all", f"--name={partition}"))

            click.echo(
                sh.lsblk(
                    "--all",
                    "--ascii",
                    "--output",
                    "NAME,TYPE,FSTYPE,PARTLABEL,MOUNTPOINT",
                    drive,
                )
            )
    except Exception as e:
        click.echo(_("Unexpected error in describe_devices: {0}").format(e))


def mount_and_inspect(drive, image_id, results):
    """
    Mount provided drive and inspect it.

    Note: This function updates results and returns nothing.

    Args:
        drive (str): The path to the drive to mount.
        image_id (str): The id of the image we're inspecting.
        results (dict): The results of the inspection.

    """
    click.echo(_("Checking drive {0} for {1}").format(drive, image_id))

    if image_id not in results["images"]:
        results["images"][image_id] = {
            RHEL_FOUND: False,
            "rhel_signed_packages_found": False,
            "rhel_product_certs_found": False,
            "rhel_release_files_found": False,
            "rhel_enabled_repos_found": False,
            "rhel_version": None,
            "syspurpose": None,
            "drives": {},
            "errors": [],
        }

    image_results = results["images"][image_id]

    if drive not in results["images"][image_id]["drives"]:
        image_results["drives"][drive] = {}

    if not os.path.exists(drive):
        message = _("Nothing found at path {0} for {1}").format(drive, image_id)
        click.echo(message, err=True)
        results["errors"].append(message)
        image_results["errors"].append(message)
        return

    if partitions := get_partitions(drive):
        if lvm_partitions := is_lvm(partitions):
            partitions = [i for i in partitions if i not in lvm_partitions]
            partitions.extend(fetch_lv_paths())

            # Make sure all the nodes are created
            click.echo(sh.vgscan("--mknodes"))

        click.echo(
            _("Found following partitions on drive {0}: {1}").format(drive, partitions)
        )

        for partition in partitions:
            check_partition(drive, partition, image_id, results)
    else:
        click.echo(
            _("No partitions found on drive {0} for {1}").format(drive, image_id)
        )


def check_partition(drive, partition, image_id, results):
    """
    Check the partition.

    Note: This function updates results and returns nothing.

    Args:
        drive (str): The path to the mounted drive.
        partition (str): The partition mounted from the drive.
        image_id (str): The id of the image we're inspecting.
        results (dict): The results of the inspection.

    """
    image_results = results["images"][image_id]

    click.echo(
        _("Checking partition {partition} for image {image_id}").format(
            partition=partition, image_id=image_id
        )
    )
    rhel_release_files = {}
    rhel_product_certs = {}
    rhel_signed_packages = {}
    rhel_enabled_repos = {}
    partition_result = {
        "facts": {
            "rhel_release_files": rhel_release_files,
            "rhel_product_certs": rhel_product_certs,
            "rhel_signed_packages": rhel_signed_packages,
            "rhel_enabled_repos": rhel_enabled_repos,
        }
    }
    image_results["drives"][drive][partition] = partition_result
    try:
        with mount(partition, INSPECT_PATH):
            check_release_files(partition, rhel_release_files)
            check_for_rhel_certs(partition, rhel_product_certs)
            check_enabled_repos(partition, rhel_enabled_repos)
            check_for_signed_packages(partition, rhel_signed_packages, image_id)

            os_version = get_os_version(partition)
            partition_result["facts"]["os_version"] = os_version

            syspurpose = get_syspurpose(partition)
            partition_result["facts"]["syspurpose_contents"] = syspurpose

            rhel_found = (
                rhel_release_files[RHEL_FOUND]
                or rhel_product_certs[RHEL_FOUND]
                or rhel_enabled_repos[RHEL_FOUND]
                or rhel_signed_packages[RHEL_FOUND]
            )

            if rhel_release_files[RHEL_FOUND] and os_version:
                # Only set the os_version if RHEL is found in the release files because
                # we also get os_version from the release files. We don't want to use
                # the version from some other operating system which could be present
                # if release files exist but are not for RHEL.
                # Note: If multiple partitions, the last one found is set.
                image_results["rhel_version"] = os_version

            if rhel_found and syspurpose:
                syspurpose_parsed = parse_syspurpose(syspurpose, partition)
                if syspurpose_parsed:
                    # Set the syspurpose only if the content parsed successfully.
                    # Note: If multiple partitions, the last one found is set.
                    image_results["syspurpose"] = syspurpose_parsed

            image_results[RHEL_FOUND] |= rhel_found
            image_results["rhel_signed_packages_found"] |= rhel_signed_packages[
                RHEL_FOUND
            ]
            image_results["rhel_product_certs_found"] |= rhel_product_certs[RHEL_FOUND]
            image_results["rhel_release_files_found"] |= rhel_release_files[RHEL_FOUND]
            image_results["rhel_enabled_repos_found"] |= rhel_enabled_repos[RHEL_FOUND]

            if rhel_found:
                click.echo(
                    _(
                        "RHEL (version {os_version}) found on: {image_id} "
                        "in {partition}"
                    ).format(
                        os_version=os_version,
                        image_id=image_id,
                        partition=partition,
                    )
                )
            else:
                click.echo(
                    _("RHEL not found on: {image_id} in {partition}").format(
                        image_id=image_id, partition=partition
                    )
                )

    except sh.ErrorReturnCode as e:
        message = (
            _(
                "Mount of {partition} on image {image_id} failed with error: {stderr} "
                "full_command: {full_cmd} stdout: {stdout}",
            )
            .format(
                partition=partition,
                image_id=image_id,
                stderr=e.stderr,
                full_cmd=e.full_cmd,
                stdout=e.stdout,
            )
            .strip()
        )

        click.echo(message, err=True)
        image_results["drives"][drive][partition]["error"] = e.stderr
        image_results["errors"].append(message)
        results["errors"].append(message)


def check_for_ostree():
    """
    Check for presence of an ostree deployment on mounted partition.

    Returns:
        (os.path): path to the root of the ostree deployment.

    """
    ostree_root = os.path.join(INSPECT_PATH, "ostree")
    # Get default boot target, which will always either be boot.0 or boot.1
    path_pattern = os.path.join(ostree_root, "boot.[0,1]/**/**/**/")
    if boot_path := glob.glob(path_pattern):
        return os.path.realpath(boot_path[0])


@contextmanager
def mount(partition, inspect_path):
    """
    Mount given partition.

    Args:
        partition (str):  The path to the partition to mount.
        inspect_path (str): The path where the partition should be mounted.

    """
    global INSPECT_PATH
    default_inspect_path = INSPECT_PATH
    click.echo(_("Mounting {}.").format(partition))
    mount_result = sh.mount(
        "-t",
        "auto",
        "-o",
        "ro",
        "{}".format(partition),
        "{}".format(inspect_path),
    )
    click.echo(_("Mounting result {}.").format(mount_result.exit_code))
    if ostree_path := check_for_ostree():
        # Set INSPECT_PATH to the ostree deployment root
        click.echo(
            _(
                "Found ostree deployment, updating INSPECT_PATH "
                "to {ostree_path} for {partition}."
            ).format(ostree_path=ostree_path, partition=partition)
        )
        INSPECT_PATH = ostree_path
    yield mount_result
    click.echo(_("UnMounting {}.").format(partition))
    if ostree_path:
        # Restore INSPECT_PATH if we set it earlier.
        INSPECT_PATH = default_inspect_path
        click.echo(
            _("Restored INSPECT_PATH to {inspect_path}.").format(
                inspect_path=INSPECT_PATH
            )
        )
    unmount_result = sh.umount("{}".format(inspect_path))
    click.echo(_("UnMounting result {}.").format(unmount_result.exit_code))


def generate_results_key():
    """
    Generate the key at which the results object will be placed.

    Returns:
        (str): String representation of the object key.

    """
    now = datetime.now()
    time_path = now.strftime("%Y-%m/%d/%H.%M.%S")

    return f"InspectionResults/{time_path}-{uuid4()}.json"


def report_results(results):
    """
    Places results in the bucket.

    Args:
        results (s3.Object): Object representing the results stored in our S3 bucket.

    """
    json_results = jsonpickle.encode(results)
    encoded_results = json_results.encode()
    results_md5 = b64encode(md5(encoded_results).digest()).decode()

    bucket_name = os.getenv("RESULTS_BUCKET_NAME")

    s3 = boto3.resource("s3")
    bucket = s3.Bucket(bucket_name)

    results = bucket.put_object(
        Body=encoded_results, ContentMD5=results_md5, Key=generate_results_key()
    )

    return results


def check_for_rhel_certs(partition, results):
    """
    Check os for rhel certificates.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.

    """
    pem_paths = []
    for path in CERT_PATHS:
        pem_paths = pem_paths + glob.glob(
            "{inspection_path}{pem_path}*".format(
                inspection_path=INSPECT_PATH, pem_path=path
            )
        )

    pem_files = [(os.path.basename(os.path.normpath(pem)), pem) for pem in pem_paths]
    matching_pems = [pem[1] for pem in pem_files if pem[0] in RHEL_PEMS]
    results["rhel_pem_files"] = matching_pems
    if matching_pems:
        results[RHEL_FOUND] = True
        click.echo(_("RHEL found via product certificate on: {}").format(partition))
    else:
        results[RHEL_FOUND] = False
        click.echo(_("RHEL not found via product certificate on: {}").format(partition))


def check_release_files(partition, results):
    """
    Check os release files to see if they indicate RHEL.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.

    """
    release_file_paths = find_release_files()
    results[RHEL_FOUND] = False
    if not release_file_paths:
        message = _("No release files found on {}").format(partition)
        click.echo(message)
        results["status"] = message
        return
    exception_messages = []
    for release_file_path in release_file_paths:
        try:
            rhel_found, contents = check_file(release_file_path)

            if rhel_found:
                click.echo(_("RHEL found via release file on: {}").format(partition))
            else:
                click.echo(
                    _("RHEL not found via release file on: {}").format(partition)
                )

            release_files = results.get("release_files", [])
            if release_file_path.startswith(INSPECT_PATH):
                release_file_path = release_file_path[len(INSPECT_PATH) :]
            new_release_files = {
                "rhel_release_file": release_file_path,
                "rhel_release_file_contents": contents,
                RHEL_FOUND: rhel_found,
            }
            release_files.append(new_release_files)
            results[RHEL_FOUND] = rhel_found or results.get(RHEL_FOUND, False)
            results["release_files"] = release_files
        except Exception as e:
            message = _("Error reading release files on {0}: {1}").format(partition, e)
            click.echo(message, err=True)
            exception_messages.append(message)
    if exception_messages:
        results["status"] = "\n".join(exception_messages)


def check_for_signed_packages(partition, results, image_id):
    """
    Check partition for redhat signed packages installed.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.
        image_id (str): The image that we are currently checking.

    """
    if not glob.glob("{0}/var/lib/rpm/*".format(INSPECT_PATH)):
        message = _("RPM DB directory on {0} has no data for {1}").format(
            partition, image_id
        )
        click.echo(message)
        results["rhel_found"] = False
        results["rhel_signed_package_count"] = 0
        results["status"] = message
        return

    signed_rpm_count = 0
    rpm_format_statement = (
        r'"%{DSAHEADER:pgpsig}|%{RSAHEADER:pgpsig}'
        r'|%{SIGGPG:pgpsig}|%{SIGPGP:pgpsig}\n"'
    )
    rh_key_id_string = r"'"
    for key_id in RH_KEY_IDS:
        rh_key_id_string += r"Key ID {}\|".format(key_id)
    rh_key_id_string = rh_key_id_string[:-2] + "'"
    rpm_command = (
        "rpm -qa --dbpath={0}/var/lib/rpm/ "
        "--qf {1} 2> /dev/null | grep {2} | wc -l".format(
            INSPECT_PATH, rpm_format_statement, rh_key_id_string
        )
    )
    try:
        rpm_result = subprocess.check_output(
            [rpm_command], stderr=subprocess.PIPE, shell=True, encoding="utf-8"
        )

        signed_rpm_count = int(rpm_result.strip())
    except subprocess.CalledProcessError as e:
        results["error"] = e.stderr
        click.echo(
            _(
                'The `{0}` command ran on {1} on image "{2}" failed with ' "error: {3}."
            ).format(rpm_command, partition, image_id, e.stderr)
        )

    if signed_rpm_count:
        results["rhel_found"] = True
        click.echo(_("RHEL found via signed packages on: {}").format(partition))
    else:
        results["rhel_found"] = False
        click.echo(_("RHEL not found via signed packages on: {}").format(partition))
    results["rhel_signed_package_count"] = signed_rpm_count


def find_release_files():
    """
    Look for potential release files on the mounted volume.

    Returns (list): List of file system paths that much the pattern.

    """
    return glob.glob("{}/etc/*-release".format(INSPECT_PATH))


def get_partitions(drive):
    """
    Look for partitions belonging to an attached volume.

    Args:
        drive (str): The drive to check.

    Returns (list): List of file system paths that much the pattern.

    """
    click.echo(_("Checking if drive {drive} has partitions.").format(drive=drive))

    # Scan and activate all volume groups in case of LVM
    click.echo(sh.vgscan())
    click.echo(sh.lvscan())
    click.echo(sh.vgchange("-a", "y"))

    # Before we can really _get_ the partitions, we should
    # really check and make sure we have any at all.
    blkid_out = sh.blkid("-p", "-o", "export", drive)
    blkid_out = blkid_out.rstrip().split("\n")
    blkid_dict = dict(map(lambda x: x.split("=", 1), blkid_out))

    click.echo(
        _('Block device attributes for drive "{}"\n"Output:"\n"{}"').format(
            drive, blkid_dict
        )
    )

    if partition_type := blkid_dict.get("PTTYPE"):
        click.echo(
            _("Device appears to have partitions, PTTYPE: {}").format(partition_type)
        )
        partitions = sorted(glob.glob("{}*[0-9]".format(drive)))
    elif "filesystem" in blkid_dict.get("USAGE", ""):
        click.echo(
            _("Device appears to lack a partition table, type: {}").format(
                blkid_dict.get("TYPE", "Not Present")
            )
        )
        partitions = sorted(glob.glob("{}*".format(drive)))
    else:
        click.echo(
            _(
                "We're not sure what this device is, assuming "
                "lack of partition table, blkid output:\n{}"
            ).format(blkid_dict)
        )
        partitions = sorted(glob.glob("{}*".format(drive)))

    return partitions


def is_lvm(partitions):
    """
    Determine if LVM is present on any of the provided partitions.

    Args:
        partitions: list of partitions to be checked.

    Returns:
        set: of partitions containing LVM metadata.

    """
    partition_info = {}
    lvm_partitions = set()

    for partition in partitions:
        udevadm_out = sh.udevadm("info", "--query=property", f"--name={partition}")
        properties = dict(
            map(str.strip, prop.split("=", 1))
            for prop in udevadm_out.split("\n")
            if "=" in prop
        )
        partition_info[partition] = properties

    for partition, properties in partition_info.items():
        if properties.get("ID_FS_TYPE", "") == "LVM2_member":
            lvm_partitions.add(partition)
        if "LVM2" in properties.get("ID_FS_VERSION", ""):
            lvm_partitions.add(partition)

    return lvm_partitions


def fetch_lv_paths():
    """
    Fetch paths for all available LVs.

    Returns:
        list: of LV paths.

    """
    lvdisplay_out = sh.tail(sh.lvdisplay("-C", "-o", "lv_path"), "-n", "+2")
    lv_paths = [path.strip() for path in lvdisplay_out]

    return lv_paths


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
            if "Red Hat" in file_contents:
                return True, file_contents
            else:
                return False, file_contents
    except FileNotFoundError as e:
        click.echo("{}".format(e))
        return False, None


def get_os_version(partition):
    """
    Get the OS version if present.

    Returns:
        str containing the version or None if not found or empty.

    """
    os_release_file_path = glob.glob("{}/etc/os-release".format(INSPECT_PATH))
    if os_release_file_path:
        try:
            with open(os_release_file_path[0]) as f:
                for line in f:
                    if line.startswith("VERSION_ID="):
                        version = line[11:].strip().strip('"')
                        return version if version else None
        except Exception as e:
            click.echo("{}".format(e))
    else:
        click.echo(_("No os-release file found on: {}").format(partition))
    return None


def get_syspurpose(partition):
    """
    Get the syspurpose.json (system purpose) file contents if present.

    Returns:
         str containing the contents of syspurpose.json or None if not found,
         empty or larger than 1K.

    """
    syspurpose_file_path = glob.glob(
        "{}/etc/rhsm/syspurpose/syspurpose.json".format(INSPECT_PATH)
    )
    if syspurpose_file_path:
        try:
            if os.path.getsize(syspurpose_file_path[0]) > SYSPURPOSE_FILESIZE_LIMIT:
                click.echo(
                    _(
                        "Skipping system purpose file, file is larger than {0} bytes"
                    ).format(SYSPURPOSE_FILESIZE_LIMIT)
                )
                return None
            with open(syspurpose_file_path[0]) as f:
                file_contents = f.read()
            return file_contents if file_contents else None
        except Exception as e:
            click.echo("{}".format(e))
    else:
        click.echo(_("No syspurpose.json file found on: {}").format(partition))
    return None


def parse_syspurpose(syspurpose, partition):
    """
    Parse the system purpose file's contents.

    Returns:
         object representation of the parsed contents or None if or empty.

    """
    if syspurpose and syspurpose.strip():
        try:
            return json.loads(syspurpose)
        except Exception as e:
            click.echo(
                _("Parsing system purpose on {0} failed because: {1}").format(
                    partition, str(e)
                )
            )
    else:
        click.echo(_("System purpose is empty on: {}").format(partition))
    return None


def find_repos_via_config(partition):
    """
    Find .repo files by checking package manager configuration files.

    Returns:
        list: of found .repo files, or an empty list of none are found.

    """
    # check if dnf or yum
    repo_file_dirs, dnf_config_path, yum_config_path = find_repo_file_dirs()

    click.echo(_("Found following repo_file_dirs: {}").format(repo_file_dirs))

    repo_files = []
    for repo_file_dir in repo_file_dirs:
        repo_files.extend(glob.glob("{}/*.repo".format(repo_file_dir)))

    if not repo_files:
        click.echo(_("No .repo files found on: {}").format(partition))
    else:
        click.echo(
            _('Found following .repo files on "{}": {}').format(partition, repo_files)
        )
    # it is also possible to list repos inside of the yum.conf file so we
    # want to add it to the list of files to check if it exists
    if dnf_config_path:
        repo_files.append(dnf_config_path)
    if yum_config_path:
        repo_files.append(yum_config_path)

    click.echo(
        _('Final list of .repo file dirs being checked on "{}": {}').format(
            partition, repo_files
        )
    )

    return repo_files


def find_repo_file_dirs():
    """
    Check package manager config files for defined .repo file dirs.

    Returns:
        list, str, str: representing the list of .repo dirs along with
            dnf and yum config paths if present.

    """
    repo_dirs = []

    if dnf_config_path := glob.glob("{}/etc/dnf/dnf.conf".format(INSPECT_PATH)):
        click.echo(_("Found following dnf config path(s): {}").format(dnf_config_path))
        dnf_config_path = dnf_config_path[0]
        repo_dirs.extend(read_reposdir_value_from_config(dnf_config_path))
    if yum_config_path := glob.glob("{}/etc/yum.conf".format(INSPECT_PATH)):
        click.echo(_("Found following yum config path(s): {}").format(yum_config_path))
        yum_config_path = yum_config_path[0]
        repo_dirs.extend(read_reposdir_value_from_config(yum_config_path))

    # Always check the dnf/yum default.
    repo_dirs.extend(glob.glob("{}/etc/yum.repos.d".format(INSPECT_PATH)))

    return repo_dirs, dnf_config_path, yum_config_path


def read_reposdir_value_from_config(config_path):
    """
    Check a given configuration file for a configured reposdir value.

    Args:
        config_path (str): Path of the configuration file to inspect.

    Returns:
        list: of configured repo_dirs, empty if not configured.

    """
    parser = read_config(config_path)

    # Why .getlist now instead of .get? In yum this was a single directory,
    # in dnf this can be a list of directories. This allows us to support both.
    if repo_dirs := parser["main"].getlist("reposdir"):
        repo_dirs = list(map(lambda x: "{}{}".format(INSPECT_PATH, x), repo_dirs))
        click.echo(
            _("Found the following repo directories defined in {}: {}").format(
                config_path, repo_dirs
            )
        )
        return repo_dirs
    else:
        click.echo(_('No "reposdir" defined in {}').format(config_path))
        return []


def read_config(config_path):
    """
    Parse the configuration file, returning an instance of the prepped parser.

    Args:
        config_path (str): Path of the configuration file to inspect.

    Returns:
        configparser.ConfigParser: that has parsed the configuration file.

    """
    parser = configparser.ConfigParser(
        converters={
            "list": lambda x: [
                "{}".format(x) for x in list(csv.reader([x], delimiter=","))[0]
            ]
        }
    )
    parser.read(config_path)

    return parser


def check_repo_files(file_paths):
    """
    Check the given files to extract any enabled RHEL repos.

    Args:
        file_paths (list): A list of files to check for enabled RHEL repos.

    Returns:
        (list) : A list of dictionaries that contains info on the repo
        & repo name of any RHEL enabled repos.

    """
    rhel_repos = []
    for file in file_paths:
        parser = configparser.ConfigParser()
        parser.read(file)
        for repo in parser.sections():
            for repo_name in RHEL_REPOS:
                if (
                    repo_name in parser[repo].get("name", "").lower()
                    and parser[repo].get("enabled") == "1"
                ):
                    rhel_repos.append({"repo": repo, "name": parser[repo].get("name")})
    # now we want to deduplicate the dictionaries inside the list in case they
    # are listed in more than 1 file
    rhel_repos = [
        dict(deduplicated_entry)
        for deduplicated_entry in {tuple(entry.items()) for entry in rhel_repos}
    ]
    return rhel_repos


def check_enabled_repos(partition, results):
    """
    Check the partition for any enabled RHEL repos.

    Args:
        partition (str): The partition we are currently checking.
        results (dict): Part of the results dict to which we should be
        writing our results.

    """
    results[RHEL_FOUND] = False
    try:
        repo_files = find_repos_via_config(partition)
        if repo_files:
            rhel_repos = check_repo_files(repo_files)
            if rhel_repos:
                results[RHEL_FOUND] = True
                results["rhel_enabled_repos"] = rhel_repos
                click.echo(_("RHEL found via enabled repos on: {}").format(partition))
            else:
                click.echo(
                    _("RHEL not found via enabled repos on: {}").format(partition)
                )
        else:
            click.echo(_("RHEL not found via enabled repos on: {}").format(partition))
    except Exception as e:
        message = _("Error reading yum repo files on {}: {}").format(partition, e)
        click.echo(message, err=True)
        results["status"] = message


if __name__ == "__main__":
    if os.getenv("HOUNDIGRADE_SENTRY_DSN", False):
        init(
            dsn=os.getenv("HOUNDIGRADE_SENTRY_DSN"),
            environment=os.getenv("HOUNDIGRADE_SENTRY_ENVIRONMENT"),
            release=os.getenv("HOUNDIGRADE_SENTRY_RELEASE"),
        )
    else:
        main()
