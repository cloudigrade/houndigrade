#!/usr/bin/env sh

losetup -D
losetup -P /dev/loop7 /dev/rh_release_disk
losetup -P /dev/loop8 /dev/nrh_disk
losetup -P /dev/loop9 /dev/2_part_release_nrh_disk
losetup -P /dev/loop10 /dev/rh_cert_disk
losetup -P /dev/loop11 /dev/rh_cert_release_disk
losetup -P /dev/loop12 /dev/rh_repo_disk
losetup -P /dev/loop13 /dev/rh_rpm_db_disk

scl enable rh-python36 'python cli.py -t ami-rh-release-ami /dev/loop7 -t ami-centosami /dev/loop8 -t ami-2-part-release-nrh /dev/loop9 -t ami-cert /dev/loop10 -t ami-cert-release /dev/loop11 -t ami-repo /dev/loop12 -t ami-rpm-db /dev/loop13'

losetup -D
