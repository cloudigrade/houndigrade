#!/usr/bin/env sh

if [ "$(ls /test-data/disks/ | wc -l)" == "0" ];
then
    echo "No test data disks found. Does the submodule exist?"
    echo "Try these commands:"
    echo "    git submodule sync --recursive"
    echo "    git submodule update --init --recursive --force"
    exit 1
fi

for DISK in /test-data/disks/*;
do
    echo "####################################"
    echo "# Inspection for disk file: ${DISK}"
    DISK_NAME=$(echo "${DISK}" | grep -o '[^/]*$')
    vgchange -an
    losetup -D
    losetup -P /dev/loop10 "${DISK}"
    python cli.py -t "ami-${DISK_NAME}" /dev/loop10
    vgchange -an
    losetup -D
done

for DISK in /dev/null /po/ta/toes;
do
    echo "####################################"
    echo "# Inspection for invalid device: ${DISK}"
    python cli.py -t "ami-${DISK}" /dev/loop10
done
