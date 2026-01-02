# Changelog

All notable changes to this project will be documented in this file.

## [3.2.0] - 2025-01-02

### Added - Android 13+ Vendor Boot Support

#### Major Features
- **GKI (Generic Kernel Image) Detection**: Automatic detection of GKI boot configurations (boot header v4+)
- **Vendor Boot Support**: Full support for vendor_boot partition handling
- **Recovery Location Detection**: Smart detection of recovery resources in boot, vendor_boot, or separate partitions
- **Vendor Ramdisk Fragments**: Automatic extraction and configuration of vendor_boot ramdisk recovery resources

#### Boot Configuration Enhancements
- New `_detect_boot_type()` method in `BootConfiguration` class
  - Detects GKI boot configurations
  - Identifies vendor_boot usage
  - Determines recovery resource location
  - Sets appropriate recovery mode
- New `get_recovery_ramdisk_path()` method for unified ramdisk access
- Automatic vendor_boot ramdisk extraction to `prebuilts/vendor_ramdisk/`
- Recovery mode detection with three modes:
  - `separate_partition`: Traditional recovery partition
  - `boot_ramdisk`: Recovery in boot.img ramdisk
  - `vendor_boot_ramdisk`: Recovery in vendor_boot.img ramdisk (Android 13+)

#### BoardConfig.mk Template Updates
- Vendor boot header version configuration
- Vendor ramdisk offset parameters
- Vendor kernel tags offset
- `BOARD_MKVENDORBOOTIMG_ARGS` generation
- `BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT` flag
- `BOARD_VENDOR_RAMDISK_FRAGMENTS` configuration
- `BOARD_USES_GENERIC_KERNEL_IMAGE` for GKI devices

#### TWRP Build Flags
- `TW_USE_VENDOR_BOOT`: Enable vendor_boot support in TWRP
- `TW_RECOVERY_IN_VENDOR_BOOT`: Indicate recovery in vendor_boot ramdisk
- `TW_SUPPORT_GKI_BOOT`: Enable GKI boot support in TWRP

#### New Templates
- `vendor_ramdisk_Android.mk.jinja2`: Makefile for vendor ramdisk recovery resources
- Automatic generation when recovery resources detected in vendor_boot

#### Documentation
- Comprehensive `ANDROID13_VENDOR_BOOT.md` guide covering:
  - Boot configuration modes
  - GKI detection and handling
  - Vendor boot ramdisk recovery
  - TWRP build flags
  - Troubleshooting guide
  - Device-specific examples
- Updated `README.md` with Android 13+ features

#### Device Tree Generation
- Enhanced fstab location detection using `get_recovery_ramdisk_path()`
- Automatic vendor_ramdisk makefile generation for Android 13+ devices
- Improved recovery resource collection from vendor_boot

### Changed
- Version bumped to 3.2.0
- Main script now displays "Android 13+ Vendor Boot Support Enabled"
- Improved logging for boot configuration detection
- Enhanced ramdisk path detection logic

### Technical Improvements
- Better separation of concerns between boot and vendor_boot configuration
- More robust recovery resource detection
- Improved error handling for vendor_boot ramdisk extraction
- Cleaner boot configuration property management

### Compatibility
- Fully backward compatible with pre-Android 13 devices
- Maintains support for all existing recovery configurations
- No breaking changes to existing functionality

## [3.1.0] - Previous Release

### Features
- Initial TWRP device tree generation
- Support for Treble-enabled devices (Android 8.0+)
- Boot image analysis and extraction
- Fstab generation
- Proprietary files list generation
- Build property extraction

---

## Migration Notes

### From 3.1.0 to 3.2.0

No migration required. The new version is fully backward compatible.

For Android 13+ devices:
1. Simply re-run the tool with your firmware dump
2. The tool will automatically detect and configure vendor_boot
3. Review the generated `BoardConfig.mk` for new vendor_boot flags
4. Check for `vendor_ramdisk/` directory if recovery is in vendor_boot

### Testing Checklist

When using the new version:
- [ ] Device tree generates without errors
- [ ] `BoardConfig.mk` contains appropriate boot configuration
- [ ] TWRP builds successfully
- [ ] Recovery boots on device
- [ ] All partitions mount correctly
- [ ] Backup/restore functions work
- [ ] ADB sideload works

## Known Issues

None reported for 3.2.0.

## Future Enhancements

Planned features for upcoming releases:
- Automatic super partition size detection
- Enhanced dynamic partition handling
- Boot.img v5 support (Android 14+)
- Additional device-specific optimizations
- Automated testing framework

## Contributors

- xXHenneBXx - Android 13+ vendor boot support
- SebaUbuntu - Original twrpdtgen framework
- LineageOS Project - Build system integration

## License

Apache-2.0
