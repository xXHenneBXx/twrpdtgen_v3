# Copyright (C) 2025 The LineageOS Project
# Copyright (C) 2025 The xXHenneBXx
# Copyright (C) 2025 The SebaUbuntu
#
# SPDX-License-Identifier: Apache-2.0
#

from datetime import datetime
from os import chmod
from pathlib import Path
import logging
from sebaubuntu_libs.libandroid.device_info import DeviceInfo
from sebaubuntu_libs.libandroid.fstab import Fstab
from sebaubuntu_libs.libandroid.partitions.partitions import Partitions
from sebaubuntu_libs.libandroid.props import BuildProp
from sebaubuntu_libs.liblogging import LOGI
from sebaubuntu_libs.libpath import is_relative_to
from sebaubuntu_libs.libreorder import strcoll_files_key
from shutil import rmtree
from stat import S_IRWXU, S_IRGRP, S_IROTH

from twrpdtgen_v3.proprietary_files.proprietary_files_list import ProprietaryFilesList
from twrpdtgen_v3.templates import render_template
from twrpdtgen_v3.utils.boot_configuration import BootConfiguration
from twrpdtgen_v3.utils.format_props import dump_partition_build_prop

logger = logging.getLogger(__name__)


class DeviceTree:
    """Class representing an Android device tree."""
    REQUIRED_BUILDPROP = [
        'ro.product.device',
        'ro.product.manufacturer',
        'ro.board.platform',
        'ro.product.brand',
        'ro.product.model',
    ]

    def __init__(self, path: Path):
        """Given a path to a dumpyara dump path, generate a device tree by parsing it."""
        self.path = Path(path)

        self.current_year = str(datetime.now().year)

        LOGI("Figuring out partitions scheme")
        self.partitions = Partitions(self.path)

        self.system = self.partitions.system
        self.vendor = self.partitions.vendor

        LOGI("Parsing build props and device info")
        self.build_prop = BuildProp()
        for partition in self.partitions.get_all_partitions():
            # each partition.build_prop may be a BuildProp or None
            try:
                if partition.build_prop:
                    self.build_prop.import_props(partition.build_prop)
            except Exception:
                logger.exception("Failed importing build.prop from partition: %s", partition)

        # Validate required properties are present
        missing_props = [p for p in self.REQUIRED_BUILDPROP if not self.build_prop.get_prop(p)]
        if missing_props:
            raise ValueError(
                f"Missing required build.prop entries: {missing_props}. "
                "Make sure the firmware dump contains valid build.prop files."
            )

        self.device_info = DeviceInfo(self.build_prop)

        # Attempt to detect super partition size if boot_configuration provides it later
        self.device_info.super_partition_size = None
        self.device_info.reserved_dynamic_space = None  # optional

        LOGI("Parsing fstab")
        # Use robust multi-location fstab discovery (prefer recovery ramdisk > vendor/etc > system/etc)
        self.fstab = self._locate_and_load_fstab()

        # Let the partitions know their fstab entries if any
        for partition in self.partitions.get_all_partitions():
            try:
                partition.fill_fstab_entry(self.fstab)
            except Exception:
                logger.debug("Partition %s: no fstab entry filled (or error)", getattr(partition, 'name', str(partition)), exc_info=True)

        LOGI("Extracting boot image")
        self.boot_configuration = BootConfiguration(self.path)

        # If boot configuration can report a super partition size, populate device_info
        try:
            sp_size = None
            if hasattr(self.boot_configuration, "get_super_partition_size"):
                sp_size = self.boot_configuration.get_super_partition_size()
            else:
                # some BootConfiguration implementations may expose an attribute
                sp_size = getattr(self.boot_configuration, "super_partition_size", None)
            if sp_size:
                self.device_info.super_partition_size = int(sp_size)
                logger.info("Detected super partition size: %s bytes", sp_size)
        except Exception:
            logger.debug("Could not determine super partition size", exc_info=True)

        LOGI("Getting list of rootdir files")
        # Collect vendor rootdir shell scripts
        self.rootdir_bin_files = []
        for file in self.vendor.files:
            try:
                rel = file.relative_to(self.vendor.path)
            except Exception:
                # not relative to vendor path, skip
                continue
            # prefer 'bin' under vendor root
            if len(rel.parts) > 0 and rel.parts[0] == "bin" and file.suffix == ".sh":
                self.rootdir_bin_files.append(file)
        self.rootdir_bin_files.sort(key=strcoll_files_key)

        # rootdir etc/hw init scripts
        self.rootdir_etc_files = []
        for file in self.vendor.files:
            try:
                rel = file.relative_to(self.vendor.path)
            except Exception:
                continue
            # check etc/init/hw path
            if len(rel.parts) >= 3 and rel.parts[:3] == ("etc", "init", "hw"):
                self.rootdir_etc_files.append(file)
        self.rootdir_etc_files.sort(key=strcoll_files_key)

        # Recovery resources (ramdisk) - may be under recovery or boot ramdisk
        recovery_resources_location = None
        try:
            if getattr(self.boot_configuration, "recovery_aik_manager", None):
                recovery_resources_location = self.boot_configuration.recovery_aik_manager.ramdisk_path
            elif getattr(self.boot_configuration, "boot_aik_manager", None):
                recovery_resources_location = self.boot_configuration.boot_aik_manager.ramdisk_path
        except Exception:
            logger.debug("While determining ramdisk path", exc_info=True)

        self.rootdir_recovery_etc_files = []
        if recovery_resources_location and Path(recovery_resources_location).exists():
            try:
                recovery_resources_location = Path(recovery_resources_location)
                for file in recovery_resources_location.iterdir():
                    try:
                        # include .rc files found directly in ramdisk root
                        if file.is_file() and file.suffix == ".rc":
                            self.rootdir_recovery_etc_files.append(file)
                    except Exception:
                        continue
            except Exception:
                logger.debug("Error iterating recovery ramdisk files", exc_info=True)
        else:
            logger.debug("No recovery ramdisk path detected or path does not exist: %s", recovery_resources_location)

        self.rootdir_recovery_etc_files.sort(key=strcoll_files_key)

        LOGI("Generating proprietary files list")
        self.proprietary_files_list = ProprietaryFilesList(
            [value for value in self.partitions.get_all_partitions()]
        )

    def _locate_and_load_fstab(self) -> Fstab:
        """Search multiple locations for an fstab and return a parsed Fstab object.

        Search priority:
          1. recovery ramdisk (if available)
          2. vendor/etc
          3. system/etc
          4. any fstab.* file under vendor
        """
        candidates = []

        # 1) recovery ramdisk (if present)
        try:
            ramdisk_path = None
            if getattr(self, "boot_configuration", None) and getattr(self.boot_configuration, "recovery_aik_manager", None):
                ramdisk_path = self.boot_configuration.recovery_aik_manager.ramdisk_path
            elif getattr(self, "boot_configuration", None) and getattr(self.boot_configuration, "boot_aik_manager", None):
                ramdisk_path = self.boot_configuration.boot_aik_manager.ramdisk_path

            if ramdisk_path:
                ramdisk_path = Path(ramdisk_path)
                if ramdisk_path.exists():
                    for p in ramdisk_path.rglob("fstab*"):
                        candidates.append(Path(p))
        except Exception:
            logger.debug("Error searching ramdisk for fstab", exc_info=True)

        # 2) vendor/etc
        try:
            vendor_etc = self.vendor.path / "etc"
            if vendor_etc.exists():
                for p in vendor_etc.glob("fstab*"):
                    candidates.append(p)
        except Exception:
            logger.debug("Error searching vendor/etc for fstab", exc_info=True)

        # 3) system/etc
        try:
            if getattr(self, "system", None):
                system_etc = self.system.path / "etc"
                if system_etc.exists():
                    for p in system_etc.glob("fstab*"):
                        candidates.append(p)
        except Exception:
            logger.debug("Error searching system/etc for fstab", exc_info=True)

        # 4) fallback: any fstab under vendor files
        try:
            for file in self.vendor.files:
                try:
                    rel = file.relative_to(self.vendor.path)
                except Exception:
                    continue
                if len(rel.parts) > 0 and rel.parts[0] == "etc" and file.name.startswith("fstab."):
                    candidates.append(file)
        except Exception:
            logger.debug("Fallback vendor file scan for fstab failed", exc_info=True)

        # deduplicate while preserving order
        seen = set()
        unique_candidates = []
        for p in candidates:
            key = str(p.resolve()) if p.exists() else str(p)
            if key not in seen:
                seen.add(key)
                unique_candidates.append(p)

        if not unique_candidates:
            raise FileNotFoundError(
                f"No fstab found. Searched: recovery ramdisk (if present), vendor/etc, system/etc. "
                f"Paths examined: recovery_ramdisk={locals().get('ramdisk_path')}, vendor_etc={getattr(self, 'vendor', None) and (self.vendor.path / 'etc')}"
            )

        # choose best candidate with heuristics
        chosen = None
        for cand in unique_candidates:
            try:
                text = Path(cand).read_text(errors="ignore")
            except Exception:
                continue
            # prefer fstab that mentions /data and a filesystem type
            if "/data" in text and ("ext4" in text or "f2fs" in text or "ubifs" in text):
                chosen = cand
                break

        if chosen is None:
            # fall back to first candidate
            chosen = unique_candidates[0]

        logger.info("Using fstab candidate: %s", chosen)

        try:
            fstab_obj = Fstab(chosen)
        except Exception as e:
            # re-raise with helpful context
            logger.exception("Failed to parse fstab at %s", chosen)
            raise RuntimeError(f"Failed to parse fstab {chosen}: {e}") from e

        # basic validation
        fstab_text = Path(chosen).read_text(errors="ignore")
        missing_mounts = []
        for m in ("/system", "/vendor", "/data"):
            if m not in fstab_text:
                missing_mounts.append(m)
        if missing_mounts:
            logger.warning("fstab at %s appears to be missing entries: %s", chosen, missing_mounts)

        return fstab_obj

    def dump_to_folder(self, folder: Path):
        """Dump all makefiles, blueprint and prebuilts to a folder."""
        folder = Path(folder)
        if folder.is_dir():
            rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)

        # Makefiles/blueprints
        self._render_template(folder, "Android.bp", comment_prefix="//")
        self._render_template(folder, "Android.mk")
        self._render_template(folder, "AndroidProducts.mk")
        self._render_template(folder, "BoardConfig.mk")
        self._render_template(folder, "device.mk")
        self._render_template(folder, "extract-files.sh")
        self._render_template(folder, "twrp_device.mk", out_file=f"twrp_{self.device_info.codename}.mk")
        self._render_template(folder, "README.md")
        self._render_template(folder, "setup-makefiles.sh")

        # Set permissions
        chmod(folder / "extract-files.sh", S_IRWXU | S_IRGRP | S_IROTH)
        chmod(folder / "setup-makefiles.sh", S_IRWXU | S_IRGRP | S_IROTH)

        # Proprietary files list
        (folder / "proprietary-files.txt").write_text(
            self.proprietary_files_list.get_formatted_list(self.device_info.build_description)
        )

        # Dump build props
        for partition in self.partitions.get_all_partitions():
            dump_partition_build_prop(partition.build_prop, folder / f"{partition.model.name}.prop")

        # Dump boot image prebuilt files
        prebuilts_path = folder / "prebuilts"
        prebuilts_path.mkdir(exist_ok=True)

        self.boot_configuration.copy_files_to_folder(prebuilts_path)

        # Dump rootdir
        rootdir_path = folder / "rootdir"
        rootdir_path.mkdir(exist_ok=True)

        self._render_template(rootdir_path, "rootdir_Android.bp", "Android.bp", comment_prefix="//")
        self._render_template(rootdir_path, "rootdir_Android.mk", "Android.mk")

        # rootdir/bin
        rootdir_bin_path = rootdir_path / "bin"
        rootdir_bin_path.mkdir(exist_ok=True)

        for file in self.rootdir_bin_files:
            (rootdir_bin_path / file.name).write_bytes(file.read_bytes())

        # rootdir/etc
        rootdir_etc_path = rootdir_path / "etc"
        rootdir_etc_path.mkdir(exist_ok=True)

        for file in self.rootdir_etc_files + self.rootdir_recovery_etc_files:
            try:
                (rootdir_etc_path / file.name).write_bytes(file.read_bytes())
            except Exception:
                logger.debug("Failed copying rootdir etc file: %s", file, exc_info=True)

        # write chosen fstab file
        try:
            (rootdir_etc_path / self.fstab.fstab.name).write_text(self.fstab.format())
        except Exception:
            logger.exception("Failed to write fstab into rootdir/etc")

        # Manifest
        try:
            (folder / "manifest.xml").write_text(str(self.vendor.manifest))
        except Exception:
            logger.debug("Failed writing manifest.xml", exc_info=True)

    def cleanup(self) -> None:
        """
        Cleanup all the temporary files.

        After you call this, you should throw away this object and never use it anymore.
        """
        try:
            self.boot_configuration.cleanup()
        except Exception:
            logger.debug("boot_configuration.cleanup() failed", exc_info=True)

    def _render_template(self, *args, comment_prefix: str = "#", **kwargs):
        return render_template(
            *args,
            boot_configuration=self.boot_configuration,
            comment_prefix=comment_prefix,
            current_year=self.current_year,
            device_info=self.device_info,
            fstab=self.fstab,
            rootdir_bin_files=self.rootdir_bin_files,
            rootdir_etc_files=self.rootdir_etc_files,
            rootdir_recovery_etc_files=self.rootdir_recovery_etc_files,
            partitions=self.partitions,
            **kwargs,
        )
