# Developer Guide - Android 13+ Vendor Boot Support

Quick reference for developers working with the enhanced twrpdtgen_v3.

## Quick Start

### For Android 13+ Device Trees

```bash
# Generate device tree
python3 -m twrpdtgen_v3 /path/to/dumpyara/output

# Check generated files
cd output
ls -la

# Key files to review:
# - BoardConfig.mk (vendor_boot config)
# - prebuilts/vendor_ramdisk/ (if present)
# - vendor_ramdisk/Android.mk (if recovery in vendor_boot)
```

## Key Classes and Methods

### BootConfiguration Class

#### New Attributes

```python
# Detection flags
self.is_gki                    # bool: GKI boot detected
self.uses_vendor_boot          # bool: vendor_boot partition present
self.recovery_in_vendor_boot   # bool: recovery in vendor_boot ramdisk
self.recovery_mode             # str: recovery mode type

# Vendor boot specific
self.vendor_ramdisk_offset     # str/None: vendor ramdisk offset
self.vendor_tags_offset        # str/None: vendor tags offset
```

#### New Methods

```python
def _detect_boot_type(self) -> None:
    """
    Detects boot configuration type (GKI, vendor_boot, recovery location).
    Called automatically during initialization.
    """

def get_recovery_ramdisk_path(self) -> Optional[Path]:
    """
    Returns path to ramdisk containing recovery resources.
    Priority: recovery > vendor_boot > boot

    Returns:
        Path to recovery ramdisk or None
    """

def copy_files_to_folder(self, folder: Path) -> None:
    """
    Copies all prebuilt files including vendor_boot ramdisk.
    Enhanced to handle vendor_ramdisk/ directory.
    """
```

## Boot Configuration Modes

### Detection Logic

```python
# Mode determination in _detect_boot_type()
if self.recovery:
    self.recovery_mode = "separate_partition"
elif self.uses_vendor_boot:
    if self.recovery_in_vendor_boot:
        self.recovery_mode = "vendor_boot_ramdisk"  # Android 13+
    else:
        self.recovery_mode = "boot_ramdisk"
else:
    self.recovery_mode = "boot_ramdisk"
```

### Mode Characteristics

| Mode | Recovery Location | Typical Devices | TWRP Flags |
|------|------------------|-----------------|------------|
| `separate_partition` | recovery.img | Pre-Android 13 | Standard |
| `boot_ramdisk` | boot.img ramdisk | A/B devices < 13 | `BOARD_USES_RECOVERY_AS_BOOT` |
| `vendor_boot_ramdisk` | vendor_boot.img ramdisk | Android 13+ GKI | `TW_RECOVERY_IN_VENDOR_BOOT` |

## Template Variables

### BoardConfig.mk Template

#### New Variables Available

```jinja2
{% if boot_configuration.is_gki %}
    BOARD_USES_GENERIC_KERNEL_IMAGE := true
{% endif %}

{% if boot_configuration.vendor_boot_image_info %}
    # Vendor boot detected
    BOARD_VENDOR_BOOT_HEADER_VERSION := {{ boot_configuration.vendor_boot_image_info.header_version }}
{% endif %}

{% if boot_configuration.recovery_in_vendor_boot %}
    # Recovery in vendor_boot
    BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
    BOARD_VENDOR_RAMDISK_FRAGMENTS += recovery
    TW_RECOVERY_IN_VENDOR_BOOT := true
{% endif %}
```

### Vendor Ramdisk Template

```jinja2
# vendor_ramdisk_Android.mk.jinja2
{% if boot_configuration.recovery_in_vendor_boot %}
    # Automatic vendor ramdisk recovery setup
{% endif %}
```

## Testing Your Changes

### Unit Test Coverage

```python
# test_boot_configuration.py (example)
def test_gki_detection():
    """Test GKI boot detection"""
    boot_config = BootConfiguration(gki_dump_path)
    assert boot_config.is_gki == True
    assert boot_config.boot_image_info.header_version >= "4"

def test_vendor_boot_recovery():
    """Test vendor_boot recovery detection"""
    boot_config = BootConfiguration(android13_dump_path)
    assert boot_config.recovery_in_vendor_boot == True
    assert boot_config.recovery_mode == "vendor_boot_ramdisk"

def test_recovery_ramdisk_path():
    """Test recovery ramdisk path resolution"""
    boot_config = BootConfiguration(dump_path)
    ramdisk_path = boot_config.get_recovery_ramdisk_path()
    assert ramdisk_path is not None
    assert ramdisk_path.exists()
```

### Manual Testing

```bash
# 1. Test with Android 13+ dump
python3 -m twrpdtgen_v3 /path/to/android13/dump

# 2. Verify BoardConfig.mk
grep "BOARD_VENDOR_BOOT_HEADER_VERSION" output/BoardConfig.mk
grep "TW_RECOVERY_IN_VENDOR_BOOT" output/BoardConfig.mk
grep "BOARD_USES_GENERIC_KERNEL_IMAGE" output/BoardConfig.mk

# 3. Check vendor_ramdisk extraction
ls -la output/prebuilts/vendor_ramdisk/

# 4. Build TWRP
cd /path/to/twrp/source
. build/envsetup.sh
lunch twrp_<device>-eng
mka recoveryimage

# 5. Flash and test
fastboot flash recovery recovery.img
fastboot reboot recovery
```

## Common Development Patterns

### Adding New Boot Detection Logic

```python
# In BootConfiguration._detect_boot_type()
def _detect_boot_type(self):
    # Existing logic...

    # Add new detection
    if self.boot_image_info and hasattr(self.boot_image_info, 'new_feature'):
        self.has_new_feature = bool(self.boot_image_info.new_feature)
        logger.info("Detected new feature: %s", self.has_new_feature)
```

### Adding New Template Variables

```python
# In device_tree.py _render_template()
def _render_template(self, *args, **kwargs):
    return render_template(
        *args,
        boot_configuration=self.boot_configuration,
        # ... existing vars ...
        new_variable=self.new_value,  # Add new variable
        **kwargs,
    )
```

### Adding New TWRP Flags

```jinja2
# In BoardConfig.mk.jinja2
{% if boot_configuration.new_feature %}
TW_NEW_FEATURE := true
BOARD_NEW_FEATURE_ENABLED := true
{% endif %}
```

## Debugging Tips

### Enable Verbose Logging

```python
# In device_tree.py or boot_configuration.py
import logging
logger.setLevel(logging.DEBUG)

# Check specific detection
logger.debug("Boot header version: %s", boot_image_info.header_version)
logger.debug("GKI detected: %s", is_gki)
logger.debug("Recovery mode: %s", recovery_mode)
```

### Inspect Boot Images

```bash
# Using AIK (Android Image Kitchen)
unpackimg boot.img
cat split_img/boot.img-header
cat split_img/boot.img-board

# Check vendor_boot
unpackimg vendor_boot.img
ls -la ramdisk/
```

### Common Issues and Solutions

#### Issue: GKI not detected
```python
# Check boot header version
boot_image_info.header_version  # Should be >= "4"

# Manual override if needed (testing only)
boot_configuration.is_gki = True
```

#### Issue: Recovery ramdisk not found
```python
# Check all potential locations
recovery_path = boot_configuration.get_recovery_ramdisk_path()
logger.debug("Recovery ramdisk: %s", recovery_path)

# Verify ramdisk contents
if recovery_path:
    for item in recovery_path.rglob('*'):
        logger.debug("Ramdisk file: %s", item)
```

#### Issue: Vendor ramdisk not extracted
```python
# Check extraction in copy_files_to_folder()
if self.recovery_in_vendor_boot:
    logger.debug("Extracting vendor_boot ramdisk")
    # ... extraction logic
```

## Performance Considerations

### Ramdisk Extraction
- Vendor ramdisk extraction happens during `copy_files_to_folder()`
- Large ramdisks (>10MB) may take a few seconds
- Progress logging available via debug mode

### Image Parsing
- AIK unpacking is CPU intensive
- Multiple images parsed sequentially
- Consider caching for development

## API Stability

### Stable APIs (Safe to Use)
- `BootConfiguration.__init__()`
- `BootConfiguration.get_recovery_ramdisk_path()`
- `BootConfiguration.copy_files_to_folder()`
- All public attributes (is_gki, uses_vendor_boot, etc.)

### Internal APIs (May Change)
- `BootConfiguration._detect_boot_type()`
- `BootConfiguration._extract_if_exists()`
- Template rendering internals

## Contributing Guidelines

### Adding New Features

1. **Detect in BootConfiguration**: Add detection logic in `_detect_boot_type()`
2. **Update Templates**: Add necessary template variables and conditionals
3. **Document**: Update ANDROID13_VENDOR_BOOT.md with usage details
4. **Test**: Test with real devices (multiple manufacturers if possible)
5. **Changelog**: Update CHANGELOG.md

### Code Style

```python
# Follow existing patterns
# Use descriptive variable names
# Add docstrings for public methods
# Use type hints where possible

def new_method(self, param: str) -> Optional[Path]:
    """
    Short description.

    Args:
        param: Parameter description

    Returns:
        Return value description
    """
    # Implementation
```

### Testing Requirements

- Test with multiple device dumps
- Verify backward compatibility
- Check all recovery modes
- Test TWRP build and boot

## Resources

- [Android Boot Image Header Spec](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
- [GKI Documentation](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)
- [TWRP Build Guide](https://twrp.me/faq/builtwrp.html)
- [Dumpyara](https://github.com/SebaUbuntu/dumpyara)

## Support

For questions or issues:
1. Check [ANDROID13_VENDOR_BOOT.md](ANDROID13_VENDOR_BOOT.md)
2. Review [CHANGELOG.md](CHANGELOG.md)
3. Search existing issues on GitHub
4. Create a new issue with:
   - Device information
   - Android version
   - Generated BoardConfig.mk
   - Build logs (if applicable)
