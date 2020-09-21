"""Helper functions for houndigrade tests."""
import contextlib
import os
import pathlib
import random
import shutil
import tempfile

import cli
from tests import data


def absolute_resolved_path(some_path):
    """Get the absolute path with symlinks resolved from some_path."""
    return os.path.abspath(str(pathlib.Path(some_path).resolve()))


def safety_check_path(some_path, expected_common):
    """
    Perform checks on some_path to ensure it is safe for use in our tests.

    For our tests, we need to be extra careful that certain paths are both inside the
    main temp directory and inside the current working directory because we are writing
    and deleting files, and we don't want to accidentally trash our local filesystem.

    First we ensure that the provided some_path is in the standard temp dir.
    Then we ensure that some_path is also in the expected_common_path.
    At each step, we get the absolute path and resolve any potential symlinks.

    If any sanity checks fail, raise ValueError.

    Args:
        some_path (str): path to check and sanitize
        expected_common (str): path that should share a common base with some_path
    """
    tempdir_path = tempfile.gettempdir()
    absolute_tempdir_path = absolute_resolved_path(tempdir_path)
    absolute_some_path = absolute_resolved_path(some_path)
    common_path = os.path.commonpath([absolute_tempdir_path, absolute_some_path])
    if not common_path.startswith(absolute_tempdir_path):
        raise ValueError(
            f"some_path is not in tempdir. "
            f"some_path is {some_path} but tempdir is {tempdir_path}"
        )

    absolute_expected_common = absolute_resolved_path(expected_common)
    common_path = os.path.commonpath([absolute_expected_common, absolute_some_path])
    if not common_path.startswith(absolute_expected_common):
        raise ValueError(
            f"some_path is not in expected_common. "
            f"some_path is {some_path} but expected_common is {expected_common}"
        )


def fake_mount(tempdir_path):
    """Create a context manager that mimics the behavior of `mount`."""

    @contextlib.contextmanager
    def _fake_mount(device_path, mount_path):
        """
        Fake `mount` so device_path's directory contents appear at mount_path.

        This ultimately just copies the directory at device_path to mount_path after
        performing some sanity checks on their paths.

        Args:
            device_path: source path
            mount_path: destination path
        """
        cwd = os.getcwd()
        safety_check_path(cwd, tempdir_path)  # ensure cwd is in tempdir_path
        safety_check_path(device_path, cwd)  # ensure device_path is in cwd
        safety_check_path(mount_path, cwd)  # ensure mount_path is in cwd

        shutil.rmtree(mount_path, ignore_errors=True)
        mount_path_parent = os.path.dirname(absolute_resolved_path(mount_path))
        pathlib.Path(mount_path_parent).mkdir(parents=True, exist_ok=True)
        shutil.copytree(device_path, mount_path)
        yield
        shutil.rmtree(mount_path)

    return _fake_mount


def prepare_fs_empty(root_path):
    """Prepare an empty filesystem directory."""
    pathlib.Path(root_path).mkdir(parents=True, exist_ok=True)


def prepare_fs_rhel_release(root_path):
    """Prepare a filesystem directory with RHEL release files."""
    etc_path = f"{root_path}/etc"
    write_data(data.OS_RELEASE_REDHAT, f"{etc_path}/os-release")
    write_data(data.REDHAT_RELEASE, f"{etc_path}/redhat-release")


def prepare_fs_rhel_syspurpose(root_path, content=None):
    """Prepare a filesystem directory with a RHEL syspurpose file."""
    etc_path = f"{root_path}/etc"
    if content is None:
        content = data.SYSPURPOSE_JSON_RHEL
    write_data(content, f"{etc_path}/rhsm/syspurpose/syspurpose.json")


def prepare_fs_centos_release(root_path):
    """Prepare a filesystem directory with CentOS release files."""
    etc_path = f"{root_path}/etc"
    write_data(data.OS_RELEASE_CENTOS, f"{etc_path}/os-release")
    write_data(data.CENTOS_RELEASE, f"{etc_path}/centos-release")


def prepare_fs_with_yum(
    root_path,
    rhel_enabled=True,
    include_yum_conf=True,
    include_optional=True,
    default_reposdir=True,
):
    """
    Prepare a filesystem directory with a yum config and repo(s).

    If rhel_enabled, all repos are RHEL and are enabled.
    If not rhel_enabled, a RHEL repo exists but is not enabled, and the optional repo is
    not RHEL but is enabled.
    """
    etc_path = f"{root_path}/etc"
    repos_path = (
        f"{etc_path}/yum.repos.d"
        if default_reposdir
        else f"{etc_path}/new_dir/yum_repos"
    )
    if include_yum_conf:
        yum_conf_data = (
            data.YUM_CONF if default_reposdir else data.YUM_CONF_WITH_REPOSDIR
        )
        write_data(yum_conf_data, f"{etc_path}/yum.conf")

    rhel_repo_path = f"{repos_path}/rhel7-internal.repo"
    rhel_repo_data = (
        data.YUM_REPO_RHEL_ENABLED if rhel_enabled else data.YUM_REPO_RHEL_NOT_ENABLED
    )
    write_data(rhel_repo_data, rhel_repo_path)

    if include_optional:
        optional_repo_path = (
            f"{repos_path}/rhel.repo" if rhel_enabled else f"{repos_path}/random.repo"
        )
        optional_repo_data = (
            data.YUM_REPO_RHEL_OPTIONAL_ENABLED
            if rhel_enabled
            else data.YUM_REPO_RANDOM_ENABLED
        )
        write_data(optional_repo_data, optional_repo_path)


def prepare_fs_with_bad_yum_conf(root_path):
    """Prepare a filesystem directory for testing with a bad yum repo conf."""
    yum_conf_path = "{}/etc/yum.conf".format(root_path)
    write_non_utf8_data(yum_conf_path)


def prepare_fs_with_bad_release_file(root_path):
    """Prepare a filesystem directory for testing with a bad release file."""
    release_file_path = "{}/etc/potato-release".format(root_path)
    write_non_utf8_data(release_file_path)


def prepare_fs_with_rhel_product_certificate(root_path):
    """Prepare a filesystem directory for testing with a RHEL product certificate."""
    cert_dir = random.choice(cli.CERT_PATHS)
    cert_name = random.choice(cli.RHEL_PEMS)
    cert_path = f"{root_path}{cert_dir}{cert_name}"
    write_data(data.PRODUCT_CERTIFICATE, cert_path)


def prepare_fs_with_rpm_db(root_path):
    """
    Prepare a filesystem directory for testing with an RPM DB directory.

    Note: We do not populate real data here because all of our tests currently just
    check for the presence of a file. We do not check the content of the file because
    that would require running the real `rpm` command on the local system, and we
    cannot assume it is installed and available.
    """
    db_file_path = f"{root_path}/var/lib/rpm/taters"
    db_data = "po-tay-toes"
    write_data(db_data, db_file_path)


def write_data(contents, file_path, mode="w"):
    """Write contents to file_path, also ensuring its parent directory exists."""
    pathlib.Path(os.path.dirname(file_path)).mkdir(parents=True, exist_ok=True)
    with open(file_path, mode) as f:
        f.write(contents)


def write_non_utf8_data(file_path):
    """Write non-utf8 "bad" data to file_path."""
    write_data(b"\xac", file_path, "wb")  # not a valid utf8 string!
