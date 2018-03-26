#!/usr/bin/env sh

losetup -D
losetup -P /dev/loop7 /dev/rh_disk
losetup -P /dev/loop8 /dev/nrh_disk

python cli.py -t ami-redhatami /dev/loop7 -t ami-centosami /dev/loop8

losetup -D
