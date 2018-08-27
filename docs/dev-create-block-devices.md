# Creating block devices for local testing in houndigrade
### * Note: The following steps were completed using a CentOS Vagrant Box
Creating the disk image & partitions:
-------------------------------------
1.  Run the following command to create a disk image:
    `dd if=/dev/zero of=example_disk bs=786 count=1024`
    * you can change the `bs` & `count` to reflect the size of disk you want to create
2.  Run the following commands to create a partition using fdisk:
    1. `fdisk example_disk`
    2. `p` this command allows you to view partitions (there should be none at this point)
    3. `x` this command allows you to enter the extra functionality menu
    4. `c` this changes the number of cylinders, choose 1.
    5. `r` return to main menu
    6. `n` this creates a new partition
    7. `p` selects primary partition
    8. leave the default partition number
    9. leave the default for first sector
    10. leave the default for last sector
    11. `p` this command allows you to view partitions (the partition you just created should be visible)
    12. `w` this command writes the partition table and exits fdisk

Mounting the disk image
-----------------------
3.  Enter the following commands to mount the disk image:
    1. `sudo losetup -P /dev/loop10 /path/to/example_disk`
        * you can change `/dev/loop10` to the path that you want to mount your disk to
    2. `sudo losetup` Verify that the disk image has been mounted
4. You can optionally use the following commands to read the partition (using python):
    1. `scl enable rh-python36 python`
    2. `import glob`
    3. `drive='/dev/loop10'`
    4. `value = glob.glob('{}*[0-9]'.format(drive))`
    5. `print(value)`
5. Format partition to ext2:
    `sudo mkfs.ext2 /dev/loop10p1`
6. Run the following commands to mount the volume:
    1. `sudo mkdir /mnt/inspect`
    2. `sudo mount -t auto /dev/loop10p1 /mnt/inspect/`
        * you can change `/mnt/inspect` to the path that you want to mount the volume to