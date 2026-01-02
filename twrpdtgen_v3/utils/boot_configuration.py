# Copyright (C) 2025 The LineageOS Project
# Copyright (C) 2025 The xXHenneBXx
# Copyright (C) 2025 The SebaUbuntu
#
# SPDX-License-Identifier: Apache-2.0
#

from pathlib import Path
from sebaubuntu_libs.libaik import AIKImageInfo, AIKManager
from typing import Optional, Tuple, Union
import logging

logger = logging.getLogger(__name__)

class BootConfiguration:
	"""Class representing a device's boot configuration."""
	def __init__(self, dump_path: Path):
		"""
		Given the path to a dump, parse all the images
		and generate a boot configuration.
		"""
		self.dump_path = dump_path

		self.boot = self._get_image_path("boot")
		self.dtbo = self._get_image_path("dtbo")
		self.init_boot = self._get_image_path("init_boot")
		self.recovery = self._get_image_path("recovery")
		self.vendor_boot = self._get_image_path("vendor_boot")
		self.vendor_kernel_boot = self._get_image_path("vendor_kernel_boot")

		assert self.boot, "No boot image found"

		# Extract all images
		self.boot_aik_manager = AIKManager()
		self.boot_image_info = self.boot_aik_manager.unpackimg(self.boot)

		self.init_boot_aik_manager, self.init_boot_image_info = self._extract_if_exists(
			self.init_boot
		)

		self.recovery_aik_manager, self.recovery_image_info = self._extract_if_exists(
			self.recovery
		)

		self.vendor_boot_aik_manager, self.vendor_boot_image_info = self._extract_if_exists(
			self.vendor_boot
		)

		self.vendor_kernel_boot_aik_manager, self.vendor_kernel_boot_image_info = self._extract_if_exists(
			self.vendor_kernel_boot
		)

		# Determine boot configuration type for Android 13+
		self._detect_boot_type()

		# Initialize kernel/dt/dtb/dtbo sources
		self.kernel = self.boot_image_info.kernel
		self.dt = self.boot_image_info.dt
		self.dtb = self.boot_image_info.dtb

		self.base_address = self.boot_image_info.base_address
		self.cmdline = self.boot_image_info.cmdline
		self.pagesize = self.boot_image_info.pagesize
		self.ramdisk_offset = getattr(self.boot_image_info, 'ramdisk_offset', None)
		self.tags_offset = getattr(self.boot_image_info, 'tags_offset', None)

		# Handle vendor_boot (common on Android 13+)
		if self.vendor_boot_image_info:
			self.kernel = self.vendor_boot_image_info.kernel or self.kernel
			self.dt = self.vendor_boot_image_info.dt or self.dt
			self.dtb = self.vendor_boot_image_info.dtb or self.dtb
			self.dtbo = self.vendor_boot_image_info.dtbo or self.dtbo

			self.base_address = self.vendor_boot_image_info.base_address or self.base_address
			self.cmdline = self.vendor_boot_image_info.cmdline or self.cmdline
			self.pagesize = self.vendor_boot_image_info.pagesize or self.pagesize

			# Get vendor_boot specific offsets
			self.vendor_ramdisk_offset = getattr(self.vendor_boot_image_info, 'ramdisk_offset', None)
			self.vendor_tags_offset = getattr(self.vendor_boot_image_info, 'tags_offset', None)

		# Handle init_boot
		if self.init_boot_image_info:
			self.base_address = self.init_boot_image_info.base_address or self.base_address
			self.cmdline = self.init_boot_image_info.cmdline or self.cmdline
			self.pagesize = self.init_boot_image_info.pagesize or self.pagesize

		# Handle vendor_kernel_boot
		if self.vendor_kernel_boot_image_info:
			self.kernel = self.vendor_kernel_boot_image_info.kernel or self.kernel
			self.dt = self.vendor_kernel_boot_image_info.dt or self.dt
			self.dtb = self.vendor_kernel_boot_image_info.dtb or self.dtb
			self.dtbo = self.vendor_kernel_boot_image_info.dtbo or self.dtbo

			self.base_address = self.vendor_kernel_boot_image_info.base_address or self.base_address
			self.cmdline = self.vendor_kernel_boot_image_info.cmdline or self.cmdline
			self.pagesize = self.vendor_kernel_boot_image_info.pagesize or self.pagesize

	def _get_image_path(self, partition: str) -> Union[Path, None]:
		path = self.dump_path / f"{partition}.img"
		return path if path.is_file() else None

	@staticmethod
	def _extract_if_exists(
		image: Optional[Path]
	) -> Tuple[Optional[AIKManager], Optional[AIKImageInfo]]:
		if not image:
			return None, None

		aik_manager = AIKManager()
		image_info = aik_manager.unpackimg(image, ignore_ramdisk_errors=True)

		return aik_manager, image_info

	def _detect_boot_type(self):
		"""
		Detect the boot configuration type for proper TWRP setup.
		Android 13+ devices typically use:
		- GKI (Generic Kernel Image) in boot
		- Vendor ramdisk in vendor_boot
		- Recovery resources may be in vendor_boot ramdisk
		"""
		# Check for GKI boot (Android 13+)
		self.is_gki = False
		self.uses_vendor_boot = bool(self.vendor_boot_image_info)
		self.recovery_in_vendor_boot = False

		# Check boot header version for GKI indicator
		if self.boot_image_info and hasattr(self.boot_image_info, 'header_version'):
			header_version = int(self.boot_image_info.header_version)
			# Boot header v4+ typically indicates GKI
			if header_version >= 4:
				self.is_gki = True
				logger.info("Detected GKI boot (header version %d)", header_version)

		# Check if vendor_boot has recovery resources
		if self.vendor_boot_aik_manager and hasattr(self.vendor_boot_aik_manager, 'ramdisk_path'):
			ramdisk_path = Path(self.vendor_boot_aik_manager.ramdisk_path)
			if ramdisk_path.exists():
				# Check for recovery indicators in vendor_boot ramdisk
				recovery_indicators = [
					'sbin/recovery',
					'system/bin/recovery',
					'init.recovery.*.rc'
				]
				for indicator in recovery_indicators:
					if list(ramdisk_path.rglob(indicator.replace('*', '**'))):
						self.recovery_in_vendor_boot = True
						logger.info("Detected recovery resources in vendor_boot ramdisk")
						break

		# Determine recovery mode
		if self.recovery:
			self.recovery_mode = "separate_partition"
		elif self.uses_vendor_boot:
			if self.recovery_in_vendor_boot:
				self.recovery_mode = "vendor_boot_ramdisk"
			else:
				self.recovery_mode = "boot_ramdisk"
		else:
			self.recovery_mode = "boot_ramdisk"

		logger.info("Boot configuration: is_gki=%s, uses_vendor_boot=%s, recovery_mode=%s",
		           self.is_gki, self.uses_vendor_boot, self.recovery_mode)

	def get_recovery_ramdisk_path(self) -> Optional[Path]:
		"""Get the path to the ramdisk containing recovery resources."""
		# Priority: recovery > vendor_boot > boot
		if self.recovery_aik_manager and hasattr(self.recovery_aik_manager, 'ramdisk_path'):
			return Path(self.recovery_aik_manager.ramdisk_path)

		if self.recovery_in_vendor_boot and self.vendor_boot_aik_manager:
			if hasattr(self.vendor_boot_aik_manager, 'ramdisk_path'):
				return Path(self.vendor_boot_aik_manager.ramdisk_path)

		if self.boot_aik_manager and hasattr(self.boot_aik_manager, 'ramdisk_path'):
			return Path(self.boot_aik_manager.ramdisk_path)

		return None

	def copy_files_to_folder(self, folder: Path) -> None:
		"""Copy all prebuilts to a folder."""
		if self.kernel:
			(folder / "kernel").write_bytes(self.kernel.read_bytes())

		if self.dt:
			(folder / "dt.img").write_bytes(self.dt.read_bytes())

		if self.dtb:
			(folder / "dtb.img").write_bytes(self.dtb.read_bytes())

		if self.dtbo:
			(folder / "dtbo.img").write_bytes(self.dtbo.read_bytes())

		# Copy vendor_boot ramdisk if it contains recovery resources
		if self.recovery_in_vendor_boot and self.vendor_boot_aik_manager:
			try:
				ramdisk_path = Path(self.vendor_boot_aik_manager.ramdisk_path)
				if ramdisk_path.exists():
					# Create vendor_ramdisk directory
					vendor_ramdisk_dir = folder / "vendor_ramdisk"
					vendor_ramdisk_dir.mkdir(exist_ok=True)

					# Copy recovery-related files from vendor_boot ramdisk
					for item in ramdisk_path.rglob('*'):
						if item.is_file():
							rel_path = item.relative_to(ramdisk_path)
							dest = vendor_ramdisk_dir / rel_path
							dest.parent.mkdir(parents=True, exist_ok=True)
							dest.write_bytes(item.read_bytes())
							logger.debug("Copied vendor_boot ramdisk file: %s", rel_path)
			except Exception as e:
				logger.warning("Failed to copy vendor_boot ramdisk files: %s", e)

	def cleanup(self):
		"""Cleanup all the temporary files. Do not use this object anymore after calling this."""
		self.boot_aik_manager.cleanup()

		if self.init_boot_aik_manager:
			self.init_boot_aik_manager.cleanup()

		if self.recovery_aik_manager:
			self.recovery_aik_manager.cleanup()

		if self.vendor_boot_aik_manager:
			self.vendor_boot_aik_manager.cleanup()

		if self.vendor_kernel_boot_aik_manager:
			self.vendor_kernel_boot_aik_manager.cleanup()
