"""Collection of tests for ``cli.read_config`` function."""
from tempfile import NamedTemporaryFile
from unittest import TestCase

from cli import read_config


class TestReadConfig(TestCase):
    """Test suite for houndigrade CLI's "read_config" function."""

    def test_read_dnf_config_ok(self):
        """Assert happy path works."""
        with NamedTemporaryFile() as conf:
            conf.write(
                b"""
[main]
gpgcheck=1
installonly_limit=3
clean_requirements_on_remove=True
best=True
reposdir="/etc/dnf.repos.d"
skip_if_unavailable=False"""
            )
            conf.seek(0)
            read_conf = read_config(conf.name)
            read_dnf_repo_dir = read_conf["main"].getlist("reposdir")
            self.assertEqual(read_dnf_repo_dir, ["/etc/dnf.repos.d"])

    def test_read_dnf_config_multiple_ok(self):
        """Assert defining multiple reposdirs is properly parsed."""
        with NamedTemporaryFile() as conf:
            conf.write(
                b"""
[main]
gpgcheck=1
installonly_limit=3
clean_requirements_on_remove=True
best=True
reposdir="/etc/dnf.repos.d","/etc/yum.repos.d","/mnt/repos/taco.repos.d"
skip_if_unavailable=False"""
            )
            conf.seek(0)
            read_conf = read_config(conf.name)
            read_dnf_repo_dir = read_conf["main"].getlist("reposdir")
            self.assertIn("/etc/dnf.repos.d", read_dnf_repo_dir)
            self.assertIn("/etc/yum.repos.d", read_dnf_repo_dir)
            self.assertIn("/mnt/repos/taco.repos.d", read_dnf_repo_dir)

    def test_read_dnf_config_multiple_weird_ok(self):
        """Assert defining multiple weird reposdirs is properly parsed."""
        with NamedTemporaryFile() as conf:
            conf.write(
                b"""
[main]
gpgcheck=1
installonly_limit=3
clean_requirements_on_remove=True
best=True
reposdir="/etc/dnf.rep,os.d","/e,,tc/yum.repos.d","/mnt/rep,os/taco.repos.d"
skip_if_unavailable=False"""
            )
            conf.seek(0)
            read_conf = read_config(conf.name)
            read_dnf_repo_dir = read_conf["main"].getlist("reposdir")
            self.assertIn("/etc/dnf.rep,os.d", read_dnf_repo_dir)
            self.assertIn("/e,,tc/yum.repos.d", read_dnf_repo_dir)
            self.assertIn("/mnt/rep,os/taco.repos.d", read_dnf_repo_dir)
