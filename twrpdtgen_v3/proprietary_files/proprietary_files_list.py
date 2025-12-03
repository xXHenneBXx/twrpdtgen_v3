#
#
# Copyright (C) 2025 The LineageOS Project
#
# Copyright (C) 2025 xXHenneBXx
#
# SPDX-License-Identifier: Apache-2.0
#

from typing import List, Optional, Iterable, Tuple, Dict
from pathlib import Path
import hashlib
import logging

from sebaubuntu_libs.libandroid.partitions.partition import AndroidPartition
from sebaubuntu_libs.libandroid.partitions.partition_model import TREBLE

from twrpdtgen_v3.proprietary_files.ignore import is_blob_allowed
from twrpdtgen_v3.proprietary_files.section import Section, sections

logger = logging.getLogger(__name__)


def _sha256_of_path(p: Path) -> str:
    """Return hex sha256 of file contents. If unreadable, return empty string."""
    try:
        h = hashlib.sha256()
        # read in chunks to be memory friendly
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        logger.debug("Failed hashing file %s", p, exc_info=True)
        return ""


class ProprietaryFilesList:
    """Class representing a proprietary files list.

    Responsibilities:
      - collect candidate blobs from partitions
      - filter using is_blob_allowed
      - remove duplicates (same relative path + identical content across partitions)
      - delegate classification to configured Section objects
      - provide formatted output (proprietary-files.txt)
    """

    def __init__(self, partitions: List[AndroidPartition]):
        """Initialize a new ProprietaryFilesList object.

        `partitions` should be a list of AndroidPartition objects as returned by
        the Partitions helper.
        """
        self.partitions = partitions

        # start with canonical sections (imported from section module)
        self.sections: List[Section] = list(sections)

        # final misc section for remaining TREBLE partition blobs
        self._misc_section = Section(name="Misc (treble)")

        # collect, filter, dedupe, and populate sections
        all_files = self._collect_candidate_files()
        deduped = self._dedupe_files(all_files)
        self._populate_sections(deduped)

        # append misc section if it has files
        if self._misc_section.get_files():
            self.sections.append(self._misc_section)

    def _collect_candidate_files(self) -> List[Tuple[AndroidPartition, Path]]:
        """Collect candidate files from partitions.

        Returns list of tuples (partition, path_to_file).
        """
        candidates: List[Tuple[AndroidPartition, Path]] = []
        for part in self.partitions:
            try:
                for f in part.files:
                    # get path relative to partition root for filtering/formatting
                    try:
                        rel = f.relative_to(part.path)
                    except Exception:
                        # if relative_to() fails, keep full path but warn
                        logger.debug("File not relative to partition.path (%s): %s", part.path, f)
                        rel = f

                    # Allow/deny via ignore rules (pass relative Path)
                    if not is_blob_allowed(rel):
                        continue

                    candidates.append((part, f))
            except Exception:
                logger.exception("Error iterating files for partition: %s", getattr(part, "name", str(part)))
        return candidates

    def _dedupe_files(self, files: List[Tuple[AndroidPartition, Path]]) -> List[Tuple[AndroidPartition, Path]]:
        """Deduplicate files.

        Strategy:
          - prefer earlier partitions in provided list order (preserves partition priority)
          - identical relative path but different contents => keep both but rename with partition prefix in output
          - identical relative path and identical hash => include only first occurrence
        """
        seen_by_rel: Dict[str, str] = {}   # relative_path -> content_hash
        kept: List[Tuple[AndroidPartition, Path]] = []

        for part, fullpath in files:
            try:
                rel = str(fullpath.relative_to(part.path))
            except Exception:
                # fallback to full path string if relative fails
                rel = str(fullpath)

            # compute content hash
            content_hash = _sha256_of_path(fullpath)

            if rel in seen_by_rel:
                existing_hash = seen_by_rel[rel]
                if existing_hash == content_hash:
                    # exact duplicate — skip
                    logger.debug("Skipping duplicate blob (same path+content): %s (part=%s)", rel, getattr(part, "name", "unknown"))
                    continue
                else:
                    # same relative path but different content — keep both but disambiguate by partition
                    # we will allow sections to handle names, but to avoid collisions we attach partition prefix later
                    logger.debug("Found same relative path with different content: %s (kept previous, keeping this with partition prefix)", rel)
                    # to allow both through, mangle the rel by adding partition name as prefix in a synthetic Path object
                    # but keep the real fullpath for content/hashing
                    kept.append((part, fullpath))
            else:
                seen_by_rel[rel] = content_hash
                kept.append((part, fullpath))

        return kept

    def _populate_sections(self, files: List[Tuple[AndroidPartition, Path]]) -> None:
        """Feed collected files into configured sections and into the misc section for TREBLE partitions.

        Each Section is expected to provide an add_files(files, partition) method that accepts
        an iterable of Path-like objects and a partition object. To maintain compatibility we call
        the sections in order and pass the per-partition candidate list.
        """
        # Group files by partition for clearer processing order
        by_partition: Dict[str, List[Path]] = {}
        partition_lookup: Dict[str, AndroidPartition] = {}

        for part, pth in files:
            key = getattr(part, "name", None) or getattr(part, "model", None) or str(part)
            if key not in by_partition:
                by_partition[key] = []
                partition_lookup[key] = part
            by_partition[key].append(pth)

        # iterate partitions in original order given by self.partitions for reproducibility
        for part in self.partitions:
            key = getattr(part, "name", None) or getattr(part, "model", None) or str(part)
            candidates = by_partition.get(key, [])
            if not candidates:
                continue

            # let each configured section consume/add relevant files from this partition
            # The Section.add_files() should return remaining files for next sections OR mutate internal state.
            # To be defensive we pass the full list and let section implementations decide.
            remaining = candidates
            for section in self.sections:
                try:
                    # some Section implementations expect (files, partition) and return a filtered list
                    res = section.add_files(remaining, part)
                    if isinstance(res, list):
                        # treat returned list as remaining files to pass on
                        remaining = res
                    else:
                        # if section.add_files doesn't return, assume it processed what it needed
                        # and we keep remaining unchanged
                        pass
                except Exception:
                    logger.exception("Section %s failed while processing partition %s", getattr(section, "name", str(section)), key)

            # After registered sections ran, if this partition is TREBLE, put remaining into misc
            try:
                if getattr(part, "model", None) and part.model.group == TREBLE:
                    try:
                        self._misc_section.add_files(remaining, part)
                    except Exception:
                        # if add_files returns a remainder, ignore — we've already exhausted section handling
                        logger.debug("misc_section.add_files failed for partition %s", key, exc_info=True)
            except Exception:
                logger.debug("Error while classifying treble partition files: %s", key, exc_info=True)

    def __str__(self) -> str:
        return self.get_formatted_list()

    def get_formatted_list(self, build_description: Optional[str] = None) -> str:
        """Return the final proprietary-files.txt content as a string.

        Output structure:
          - optional header with build description
          - per-section header comment and listed items (one-per-line)
        """
        lines: List[str] = []
        if build_description:
            lines.append(f"# Unpinned blobs from {build_description}")

        # Ensure deterministic ordering: sort sections by name (except keep existing order if desired)
        for section in self.sections:
            try:
                files = section.get_files()
            except Exception:
                logger.debug("Section.get_files failed for %s", getattr(section, "name", str(section)), exc_info=True)
                files = []

            if not files:
                continue

            # section.name may be None in older Section implementations
            section_name = getattr(section, "name", "Unnamed")
            lines.append("")
            lines.append(f"# {section_name}")

            # Normalize and sort file entries for deterministic output
            normalized = []
            for entry in files:
                try:
                    # if entry is a Path object, convert to string relative path
                    if isinstance(entry, Path):
                        normalized.append(str(entry))
                    else:
                        normalized.append(str(entry))
                except Exception:
                    normalized.append(str(entry))

            normalized_sorted = sorted(set(normalized))
            lines.extend(normalized_sorted)

        # misc section (treble) appended if present
        try:
            misc_files = self._misc_section.get_files()
            if misc_files:
                lines.append("")
                lines.append(f"# {getattr(self._misc_section, 'name', 'Misc (treble)')}")
                normalized = sorted(set(str(f) for f in misc_files))
                lines.extend(normalized)
        except Exception:
            logger.debug("Failed getting misc section files", exc_info=True)

        return "\n".join(lines) + "\n"
