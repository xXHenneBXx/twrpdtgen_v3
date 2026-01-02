# Android 13+ Vendor Boot & Recovery Support

This document explains the enhancements made to twrpdtgen_v3 for properly handling Android 13+ devices that use vendor_boot partitions and modern boot configurations for TWRP recovery.

## Overview

Starting with Android 13, Google introduced significant changes to the boot process:

1. **GKI (Generic Kernel Image)**: Standardized kernel with boot header version 4+
2. **Vendor Boot Partition**: Contains vendor-specific ramdisk and configuration
3. **Recovery in Vendor Boot**: Recovery resources may be in vendor_boot ramdisk instead of boot
4. **Vendor Ramdisk Fragments**: Modular ramdisk components for recovery

## Key Changes

### 1. Enhanced Boot Configuration Detection

The `BootConfiguration` class now automatically detects:

- **GKI Boot**: Identifies devices using Generic Kernel Image (boot header v4+)
- **Vendor Boot Usage**: Detects presence and configuration of vendor_boot partition
- **Recovery Location**: Determines if recovery resources are in boot, vendor_boot, or separate partition
- **Recovery Mode**: Sets appropriate recovery mode for the device

#### Detection Logic

```python
# Automatically sets:
self.is_gki = True/False                    # GKI boot detected
self.uses_vendor_boot = True/False          # vendor_boot partition present
self.recovery_in_vendor_boot = True/False   # Recovery in vendor_boot ramdisk
self.recovery_mode = "vendor_boot_ramdisk"  # Recovery mode type
```

### 2. Vendor Boot Configuration in BoardConfig.mk

The generated `BoardConfig.mk` now includes proper vendor_boot settings:

```makefile
# Vendor Boot section (when vendor_boot detected)
BOARD_VENDOR_BOOT_HEADER_VERSION := 4
BOARD_VENDOR_RAMDISK_OFFSET := 0x01000000
BOARD_VENDOR_KERNEL_TAGS_OFFSET := 0x00000100

# Vendor boot image arguments
BOARD_MKVENDORBOOTIMG_ARGS += --header_version $(BOARD_VENDOR_BOOT_HEADER_VERSION)
BOARD_MKVENDORBOOTIMG_ARGS += --ramdisk_offset $(BOARD_VENDOR_RAMDISK_OFFSET)
BOARD_MKVENDORBOOTIMG_ARGS += --tags_offset $(BOARD_VENDOR_KERNEL_TAGS_OFFSET)

# Recovery in vendor_boot
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
BOARD_VENDOR_RAMDISK_FRAGMENTS += recovery
```

### 3. TWRP-Specific Flags

New TWRP build flags are automatically set based on detected configuration:

```makefile
# TWRP flags for vendor_boot devices
TW_USE_VENDOR_BOOT := true                    # Enable vendor_boot support
TW_RECOVERY_IN_VENDOR_BOOT := true            # Recovery in vendor_boot ramdisk
TW_SUPPORT_GKI_BOOT := true                   # GKI boot support
```

### 4. Vendor Ramdisk Recovery Resources

When recovery resources are detected in vendor_boot:

- **Extraction**: All vendor_boot ramdisk files are extracted to `prebuilts/vendor_ramdisk/`
- **Makefile Generation**: Automatic `vendor_ramdisk/Android.mk` creation
- **Integration**: Seamless integration into TWRP build process

## Boot Configuration Modes

The tool now handles multiple recovery configurations:

### Mode 1: Separate Recovery Partition (Legacy)
```
recovery_mode = "separate_partition"
- Traditional devices with dedicated recovery partition
- Most pre-Android 13 devices
```

### Mode 2: Boot Ramdisk Recovery
```
recovery_mode = "boot_ramdisk"
- Recovery resources in boot.img ramdisk
- A/B devices without vendor_boot
```

### Mode 3: Vendor Boot Ramdisk Recovery (Android 13+)
```
recovery_mode = "vendor_boot_ramdisk"
- Recovery resources in vendor_boot.img ramdisk
- Most Android 13+ devices with GKI
- Requires vendor ramdisk fragment support
```

## Usage

### Basic Usage

The tool automatically detects and configures everything:

```bash
python3 -m twrpdtgen_v3 /path/to/firmware/dump
```

### Output Structure for Android 13+ Devices

```
output/
├── Android.bp
├── Android.mk
├── BoardConfig.mk              # Contains vendor_boot config
├── device.mk
├── twrp_<codename>.mk
├── prebuilts/
│   ├── kernel                  # GKI kernel
│   ├── dtb.img
│   ├── dtbo.img
│   └── vendor_ramdisk/         # Vendor_boot ramdisk (if applicable)
│       └── ... recovery files
├── rootdir/
│   ├── Android.bp
│   ├── Android.mk
│   └── etc/
│       └── fstab.<device>
└── vendor_ramdisk/             # Generated if recovery in vendor_boot
    └── Android.mk              # Vendor ramdisk makefile

```

## Technical Details

### GKI Detection

GKI boot is detected by checking:
1. Boot header version >= 4
2. Presence of vendor_boot partition
3. Generic kernel image characteristics

### Recovery Resource Detection

The tool searches for recovery indicators in vendor_boot ramdisk:
- `sbin/recovery`
- `system/bin/recovery`
- `init.recovery.*.rc` files

### Vendor Boot Header Versions

| Version | Android | Features |
|---------|---------|----------|
| 3 | 12 | Basic vendor_boot |
| 4 | 13+ | GKI, vendor ramdisk fragments |

## Build Flags Reference

### Core Flags

```makefile
BOARD_USES_GENERIC_KERNEL_IMAGE := true
# Enables GKI support in build system

BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
# Moves recovery resources to vendor_boot during build

BOARD_VENDOR_RAMDISK_FRAGMENTS += recovery
# Adds recovery as vendor ramdisk fragment
```

### TWRP Flags

```makefile
TW_USE_VENDOR_BOOT := true
# Tells TWRP to use vendor_boot partition

TW_RECOVERY_IN_VENDOR_BOOT := true
# Indicates recovery is in vendor_boot ramdisk

TW_SUPPORT_GKI_BOOT := true
# Enables GKI boot support in TWRP
```

## Troubleshooting

### Issue: Recovery not booting on Android 13+ device

**Solution**: Verify BoardConfig.mk contains:
```makefile
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
TW_RECOVERY_IN_VENDOR_BOOT := true
```

### Issue: Vendor ramdisk files not included

**Solution**: Check that `prebuilts/vendor_ramdisk/` directory exists and contains files

### Issue: GKI kernel not detected

**Solution**: Verify boot header version:
```bash
# Check boot.img header
file boot.img
# Should show "version: 4" or higher for GKI
```

## Migration from Legacy twrpdtgen

If migrating from the old twrpdtgen:

1. **Re-generate device tree**: Use new twrpdtgen_v3 with your firmware dump
2. **Review BoardConfig.mk**: Check vendor_boot and GKI flags
3. **Update makefiles**: Use generated vendor_ramdisk makefiles if present
4. **Test recovery**: Build and test TWRP recovery thoroughly

## Examples

### Example 1: Pixel 7 (Android 13, GKI)

```makefile
# BoardConfig.mk (auto-generated)
BOARD_BOOT_HEADER_VERSION := 4
BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_VENDOR_BOOT_HEADER_VERSION := 4
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
BOARD_VENDOR_RAMDISK_FRAGMENTS += recovery
TW_USE_VENDOR_BOOT := true
TW_RECOVERY_IN_VENDOR_BOOT := true
TW_SUPPORT_GKI_BOOT := true
```

### Example 2: OnePlus 11 (Android 13)

```makefile
# BoardConfig.mk (auto-generated)
BOARD_BOOT_HEADER_VERSION := 4
BOARD_VENDOR_BOOT_HEADER_VERSION := 4
BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
TW_USE_VENDOR_BOOT := true
TW_RECOVERY_IN_VENDOR_BOOT := true
```

## References

- [Android Boot Image Header](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
- [GKI Documentation](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)
- [Vendor Boot Partition](https://source.android.com/docs/core/architecture/bootloader/partitions/vendor-boot-partitions)
- [TWRP GitHub](https://github.com/TeamWin/Team-Win-Recovery-Project)

## Contributing

When contributing improvements for Android 13+ support:

1. Test with multiple devices (different manufacturers)
2. Verify both GKI and non-GKI configurations
3. Test recovery boot on actual hardware
4. Update this documentation with new findings

## License

Copyright (C) 2025 The LineageOS Project
Copyright (C) 2025 xXHenneBXx
SPDX-License-Identifier: Apache-2.0
