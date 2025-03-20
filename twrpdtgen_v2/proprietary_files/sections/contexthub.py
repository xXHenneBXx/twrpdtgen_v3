#
#
# Copyright (C) 2025 The LineageOS Project
# Copyright (C) 2025 xXHenneBXx
# SPDX-License-Identifier: Apache-2.0
#

from twrpdtgen_v2.proprietary_files.section import Section, register_section

class ContextHubSection(Section):
	name = "Context hub"
	interfaces = [
		"android.hardware.contexthub",
	]

register_section(ContextHubSection)
