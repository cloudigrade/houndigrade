"""Helper functions for houndigrade tests."""
import os
import pathlib

from tests import data


def prepare_fs(root_path):
    """
    Prepare a filesystem directory for testing.

    File tree under {root_path}/xvdf1 will look like RHEL.
    File tree under {root_path}/xvdf2 will look like CentOS.
    """
    etc_path = f"{root_path}/xvdf1/etc"
    write_data(data.OS_RELEASE_REDHAT, f"{etc_path}/os-release")
    write_data(data.REDHAT_RELEASE, f"{etc_path}/redhat-release")
    write_data(data.SYSPURPOSE_JSON_RHEL, f"{etc_path}/rhsm/syspurpose/syspurpose.json")

    etc_path = f"{root_path}/xvdf2/etc"
    write_data(data.OS_RELEASE_CENTOS, f"{etc_path}/os-release")
    write_data(data.CENTOS_RELEASE, f"{etc_path}/centos-release")


def prepare_fs_with_rhel_repos(root_path):
    """
    Prepare a filesystem directory for testing with enabled yum repos.

    File tree under {root_path}/xvdf1 will have enabled RHEL yum repos.
    File tree under {root_path}/xvdf2 will also have enabled RHEL yum repos.
    """
    etc_path = f"{root_path}/xvdf1/etc"
    repos_path = f"{etc_path}/yum.repos.d"
    write_data(data.YUM_CONF, f"{etc_path}/yum.conf")
    write_data(data.YUM_REPO_RHEL_ENABLED, f"{repos_path}/rhel7-internal.repo")
    write_data(data.YUM_REPO_RHEL_OPTIONAL_ENABLED, f"{repos_path}/rhel.repo")
    etc_path = f"{root_path}/xvdf2/etc"
    repos_path = f"{etc_path}/yum.repos.d"
    write_data(data.YUM_CONF, f"{etc_path}/yum.conf")
    write_data(data.YUM_REPO_RHEL_ENABLED, f"{repos_path}/rhel7-internal.repo")


def prepare_fs_with_non_enabled_repos(root_path):
    """
    Prepare a filesystem directory for testing with disabled yum repos.

    File tree under {root_path}/xvdf1 will have a not-enabled RHEL yum repo.
    File tree under {root_path}/xvdf2 will also a not-enabled RHEL yum repo but also
    an enabled not-RHEL repo.
    """
    etc_path = f"{root_path}/xvdf1/etc"
    repos_path = f"{etc_path}/yum.repos.d"
    write_data(data.YUM_CONF, f"{etc_path}/yum.conf")
    write_data(data.YUM_REPO_RHEL_NOT_ENABLED, f"{repos_path}/rhel7-internal.repo")
    etc_path = f"{root_path}/xvdf2/etc"
    repos_path = f"{etc_path}/yum.repos.d"
    write_data(data.YUM_CONF, f"{etc_path}/yum.conf")
    write_data(data.YUM_REPO_RHEL_NOT_ENABLED, f"{repos_path}/rhel7-internal.repo")
    write_data(data.YUM_REPO_RANDOM_ENABLED, f"{etc_path}/random.repo")


def prepare_fs_with_reposdir_specified(root_path):
    """
    Prepare a filesystem directory for testing with custom yum repo dir.

    File tree under {root_path}/xvdf1 will have a custom yum.conf that defines reposdir
    at {root_path}/xvdf1/etc/new_dir/yum_repos which contains an enabled RHEL yum repo.
    """
    etc_path = f"{root_path}/xvdf1/etc"
    repos_path = f"{etc_path}/new_dir/yum_repos"
    write_data(data.YUM_CONF_WITH_REPOSDIR, f"{etc_path}/yum.conf")
    write_data(data.YUM_REPO_RHEL_ENABLED, f"{repos_path}/rhel7-internal.repo")


def prepare_fs_with_bad_yum_conf(root_path):
    """Prepare a filesystem directory for testing with a bad yum repo conf."""
    yum_conf_path = "{}/xvdf1/etc/yum.conf".format(root_path)
    write_non_utf8_data(yum_conf_path)


def prepare_fs_with_bad_release_file(root_path):
    """Prepare a filesystem directory for testing with a bad release file."""
    release_file_path = "{}/xvdf1/etc/potato-release".format(root_path)
    write_non_utf8_data(release_file_path)


def write_data(contents, file_path, mode="w"):
    """Write contents to file_path, also ensuring its parent directory exists."""
    pathlib.Path(os.path.dirname(file_path)).mkdir(parents=True, exist_ok=True)
    with open(file_path, mode) as f:
        f.write(contents)


def write_non_utf8_data(file_path):
    """Write non-utf8 "bad" data to file_path."""
    write_data(b"\xac", file_path, "wb")  # not a valid utf8 string!
