"""Helper functions for houndigrade tests."""
import os
import pathlib

from tests import data


def prepare_fs_empty(root_path):
    """Prepare an filesystem directory."""
    pathlib.Path(root_path).mkdir(parents=True, exist_ok=True)


def prepare_fs_rhel_release(root_path):
    """Prepare a filesystem directory with RHEL release files."""
    etc_path = f"{root_path}/etc"
    write_data(data.OS_RELEASE_REDHAT, f"{etc_path}/os-release")
    write_data(data.REDHAT_RELEASE, f"{etc_path}/redhat-release")


def prepare_fs_rhel_syspurpose(root_path):
    """Prepare a filesystem directory with a RHEL syspurpose file."""
    etc_path = f"{root_path}/etc"
    write_data(data.SYSPURPOSE_JSON_RHEL, f"{etc_path}/rhsm/syspurpose/syspurpose.json")


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


def write_data(contents, file_path, mode="w"):
    """Write contents to file_path, also ensuring its parent directory exists."""
    pathlib.Path(os.path.dirname(file_path)).mkdir(parents=True, exist_ok=True)
    with open(file_path, mode) as f:
        f.write(contents)


def write_non_utf8_data(file_path):
    """Write non-utf8 "bad" data to file_path."""
    write_data(b"\xac", file_path, "wb")  # not a valid utf8 string!
