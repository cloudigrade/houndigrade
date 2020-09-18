"""Reference data for houndigrade tests."""
from textwrap import dedent

REDHAT_RELEASE = "Red Hat Enterprise Linux Server release 7.4 (Maipo)\n"
CENTOS_RELEASE = "CentOS Linux release 7.4.1708 (Core)\n"

OS_RELEASE_REDHAT = dedent(
    """\
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
)
OS_RELEASE_CENTOS = dedent(
    """\
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
)

SYSPURPOSE_JSON_RHEL = dedent(
    """\
    {
      "role": "Red Hat Enterprise Linux Server",
      "service_level_agreement": "Premium",
      "usage": "Development/Test"
    }

    """
)

YUM_CONF = dedent(
    """\
    [main]
    cachedir=/var/cache/yum/$basearch/$releasever
    keepcache=0
    debuglevel=2
    logfile=/var/log/yum.log
    exactarch=1
    obsoletes=1
    gpgcheck=1
    plugins=1
    installonly_limit=3

    #  This is the default, if you make this bigger yum won't see if the metadata
    # is newer on the remote and so you'll "gain" the bandwidth of not having to
    # download the new metadata and "pay" for it by yum not having correct
    # information.
    #  It is esp. important, to have correct metadata, for distributions like
    # Fedora which don't keep old packages around. If you don't like this checking
    # interupting your command line usage, it's much better to have something
    # manually check the metadata once an hour (yum-updatesd will do this).
    # metadata_expire=90m

    # PUT YOUR REPOS HERE OR IN separate files named file.repo
    # in /etc/yum.repos.d"""  # noqa: E501
)

YUM_CONF_WITH_REPOSDIR = dedent(
    """\
    [main]
    cachedir=/var/cache/yum/$basearch/$releasever
    keepcache=0
    debuglevel=2
    logfile=/var/log/yum.log
    exactarch=1
    obsoletes=1
    gpgcheck=1
    plugins=1
    installonly_limit=3
    reposdir=/etc/new_dir/yum_repos

    #  This is the default, if you make this bigger yum won't see if the metadata
    # is newer on the remote and so you'll "gain" the bandwidth of not having to
    # download the new metadata and "pay" for it by yum not having correct
    # information.
    #  It is esp. important, to have correct metadata, for distributions like
    # Fedora which don't keep old packages around. If you don't like this checking
    # interupting your command line usage, it's much better to have something
    # manually check the metadata once an hour (yum-updatesd will do this).
    # metadata_expire=90m

    # PUT YOUR REPOS HERE OR IN separate files named file.repo
    # in /etc/yum.repos.d"""  # noqa: E501
)

YUM_REPO_RHEL_ENABLED = dedent(
    """\
    [rhel7-cdn-internal]
    name=RHEL 7 - $basearch
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
    enabled=1
    gpgcheck=0

    [rhel7-cdn-internal-extras]
    name=RHEL 7 - $basearch
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
    enabled=1
    gpgcheck=0"""  # noqa: E501
)

YUM_REPO_RHEL_NOT_ENABLED = dedent(
    """\
    [rhel7-cdn-internal]
    name=RHEL 7 - $basearch
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
    enabled=0
    gpgcheck=0

    [rhel7-cdn-internal-extras]
    name=RHEL 7 - $basearch
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
    enabled=0
    gpgcheck=0
    """  # noqa: E501
)

YUM_REPO_RHEL_OPTIONAL_ENABLED = dedent(
    """\
    [rhel7-cdn-internal-optional]
    name=RHEL 7 - $basearch
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/optional/os/
    enabled=1
    gpgcheck=0"""  # noqa: E501
)

YUM_REPO_RANDOM_ENABLED = dedent(
    """\
    [random-cdn-internal]
    name=Random repo
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/
    enabled=1
    gpgcheck=0

    [random-cdn-internal-extras]
    name=Random repo
    baseurl=http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/extras/os/
    enabled=1
    gpgcheck=0
    """  # noqa: E501
)


PRODUCT_CERTIFICATE = dedent(
    """\
    -----BEGIN CERTIFICATE-----
    aGVsbG8gY2xvdWQgZnJpZW5kcyEgdGhpcyBpcyBub3QgcmVhbGx5IGEgdmFsaWQg
    cHJvZHVjdCBjZXJ0aWZpY2F0ZSwgaXMgaXQ/IHNvcnJ5IGFib3V0IHRoYXQuIHdl
    IGp1c3QgbmVlZCBzb21lIGR1bW15IGRhdGEgaGVyZSBmb3IgdGVzdGluZy4gaSBo
    b3BlIHRoYXQncyBva2F5IHdpdGggeW91LiBjaGVlcnMhCg==
    -----END CERTIFICATE-----
    """
)
