"""Helper functions for houndigrade tests."""
import pathlib
from textwrap import dedent

from tests import data


def prepare_fs(drive_path):
    """Prepare a filesystem directory for testing."""
    pathlib.Path("{}/xvdf1/etc/rhsm/syspurpose".format(drive_path)).mkdir(
        parents=True, exist_ok=True
    )
    pathlib.Path("{}/xvdf2/etc".format(drive_path)).mkdir(parents=True, exist_ok=True)

    with open("{}/xvdf1/etc/redhat-release".format(drive_path), "w") as f:
        f.write(data.REDHAT_RELEASE)
    with open("{}/xvdf1/etc/os-release".format(drive_path), "w") as f:
        f.write(data.OS_RELEASE_REDHAT)
    with open(
        "{}/xvdf1/etc/rhsm/syspurpose/syspurpose.json".format(drive_path), "w"
    ) as f:
        f.write(dedent(data.SYSPURPOSE_JSON_RHEL))

    with open("{}/xvdf2/etc/centos-release".format(drive_path), "w") as f:
        f.write(data.CENTOS_RELEASE)
    with open("{}/xvdf2/etc/os-release".format(drive_path), "w") as f:
        f.write(dedent(data.OS_RELEASE_CENTOS))


def prepare_fs_with_rhel_repos(drive_path):
    """Prepare a filesystem directory for testing with enabled yum repos."""
    pathlib.Path("{}/xvdf1/etc".format(drive_path)).mkdir(parents=True, exist_ok=True)
    pathlib.Path("{}/xvdf2/etc".format(drive_path)).mkdir(parents=True, exist_ok=True)
    pathlib.Path("{}/xvdf1/etc/yum.repos.d".format(drive_path)).mkdir(
        parents=True, exist_ok=True
    )
    pathlib.Path("{}/xvdf2/etc/yum.repos.d".format(drive_path)).mkdir(
        parents=True, exist_ok=True
    )

    with open("{}/xvdf1/etc/yum.conf".format(drive_path), "w") as f:
        f.write(data.YUM_CONF)
    with open(
        "{}/xvdf1/etc/yum.repos.d/rhel7-internal.repo".format(drive_path), "w"
    ) as f:
        f.write(data.YUM_REPO_RHEL_ENABLED)
    with open("{}/xvdf1/etc/yum.repos.d/rhel.repo".format(drive_path), "w") as f:
        f.write(data.YUM_REPO_RHEL_OPTIONAL_ENABLED)
    with open("{}/xvdf2/etc/yum.conf".format(drive_path), "w") as f:
        f.write(data.YUM_CONF)
    with open(
        "{}/xvdf2/etc/yum.repos.d/rhel7-internal.repo".format(drive_path), "w"
    ) as f:
        f.write(data.YUM_REPO_RHEL_ENABLED)


def prepare_fs_with_non_enabled_repos(drive_path):
    """Prepare a filesystem directory for testing with disabled yum repos."""
    pathlib.Path("{}/xvdf1/etc".format(drive_path)).mkdir(parents=True, exist_ok=True)
    pathlib.Path("{}/xvdf2/etc".format(drive_path)).mkdir(parents=True, exist_ok=True)
    pathlib.Path("{}/xvdf1/etc/yum.repos.d".format(drive_path)).mkdir(
        parents=True, exist_ok=True
    )
    pathlib.Path("{}/xvdf2/etc/yum.repos.d".format(drive_path)).mkdir(
        parents=True, exist_ok=True
    )

    with open("{}/xvdf1/etc/yum.conf".format(drive_path), "w") as f:
        f.write(data.YUM_CONF)
    with open(
        "{}/xvdf1/etc/yum.repos.d/rhel7-internal.repo".format(drive_path), "w"
    ) as f:
        f.write(data.YUM_REPO_RHEL_NOT_ENABLED)
    with open("{}/xvdf2/etc/yum.conf".format(drive_path), "w") as f:
        f.write(data.YUM_CONF)
    with open("{}/xvdf2/etc/yum.repos.d/random.repo".format(drive_path), "w") as f:
        f.write(data.YUM_REPO_RANDOM_ENABLED)


def prepare_fs_with_reposdir_specified(drive_path):
    """Prepare a filesystem directory for testing with custom yum repo dir."""
    pathlib.Path("{}/xvdf1/etc".format(drive_path)).mkdir(parents=True, exist_ok=True)
    pathlib.Path("{}/xvdf1/etc/new_dir/yum_repos".format(drive_path)).mkdir(
        parents=True, exist_ok=True
    )

    with open("{}/xvdf1/etc/yum.conf".format(drive_path), "w") as f:
        f.write(data.YUM_CONF_WITH_REPOSDIR)
    with open(
        "{}/xvdf1/etc/new_dir/yum_repos/rhel7-internal.repo".format(drive_path), "w"
    ) as f:
        f.write(data.YUM_REPO_RHEL_ENABLED)


def prepare_fs_with_bad_yum_conf(drive_path):
    """Prepare a filesystem directory for testing with a bad yum repo conf."""
    pathlib.Path("{}/xvdf1/etc/".format(drive_path)).mkdir(parents=True, exist_ok=True)
    with open("{}/xvdf1/etc/yum.conf".format(drive_path), "wb") as f:
        f.write(b"\xac")  # not a valid utf8 string!


def prepare_fs_with_bad_release_file(drive_path):
    """Prepare a filesystem directory for testing with a bad release file."""
    pathlib.Path("{}/xvdf1/etc/".format(drive_path)).mkdir(parents=True, exist_ok=True)
    release_file_path = "{}/xvdf1/etc/potato-release".format(drive_path)
    with open(release_file_path, "wb") as f:
        f.write(b"\xac")  # not a valid utf8 string!
