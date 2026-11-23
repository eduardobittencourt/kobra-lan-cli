"""Offline tests for local job history reconstruction, observations, and safety boundaries."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unicodedata
import unittest
from unittest.mock import patch

from kobra_lan.cli import main
from kobra_lan.config import ProtocolError
from kobra_lan.jobs import COVERAGE, job_info, list_jobs
from kobra_lan.profiles import ProfileLocalError, Registry
from kobra_lan.start import attempt_id, review_digest
from kobra_lan.upload import atomic_json
from kobra_lan.watch import persist_observation
from test_client import config
from test_profiles import fixture


def make_plan(device_digest, file_sha256, filename="test.gcode", slot=1,
              auto_leveling=True, vibration=False, flow=False, material="PLA High Speed"):
    payload = {
        "taskid": "-1",
        "url": "",
        "filename": filename,
        "md5": "b" * 32,
        "filepath": None,
        "filetype": 1,
        "project_type": 1,
        "filesize": 1234,
        "ams_settings": {
            "use_ams": True,
            "ams_box_mapping": [{
                "paint_index": 0,
                "ams_index": slot - 1,
                "paint_color": [138, 148, 158],
                "ams_color": [255, 255, 255, 255],
                "material_type": material,
            }],
        },
        "task_settings": {
            "auto_leveling": int(auto_leveling),
            "vibration_compensation": int(vibration),
            "flow_calibration": int(flow),
            "dry_mode": 0,
            "ai_settings": {"status": 0, "count": 0, "type": 0},
            "timelapse": {"status": 0, "count": 0, "type": 0},
            "drying_settings": {"status": 0, "target_temp": 0, "duration": 0, "remain_time": 0},
            "model_objects_skip_parts": [],
        },
    }
    plan = {
        "file_sha256": file_sha256,
        "device_digest": device_digest,
        "model": "Anycubic Kobra X",
        "firmware": "2.0.2.2",
        "payload": payload,
    }
    return {
        **plan,
        "plan_sha256": review_digest(plan),
        "dry_run": True,
        "experimental": True,
        "hardware_start_validated": (slot in (1, 2, 4) and material == "PLA High Speed"
                                     and auto_leveling and not vibration and not flow),
        "selected_slot": slot,
        "upload_performed": False,
    }


class JobsStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state_dir = self.root / "state"
        self.cfg = config()
        self.device_digest = hashlib.sha256(self.cfg.printer_id.encode()).hexdigest()
        self.device16 = self.device_digest[:16]

    def _private_dir(self, path):
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.chmod(0o700)
        return path

    def _write_upload(self, file_sha256, filename="test.gcode", status="uploaded_verified_by_listing_and_metadata",
                      timestamp=1700000000):
        directory = self._private_dir(self.state_dir / self.device16)
        path = directory / f"{file_sha256}.json"
        atomic_json(path, {
            "sha256": file_sha256,
            "md5": "b" * 32,
            "size_bytes": 1234,
            "remote_filename": filename,
            "layer_count": 460,
            "slicer_version": "2.0.0.5",
            "operation": "upload_only",
            "starts_print": False,
            "timestamp": timestamp,
            "host": "192.0.2.10",
            "status": status,
            "remote_byte_hash_verified": False,
        })
        return path

    def _write_start(self, file_sha256, *, previous=None, legacy=False, status="start_observed_active",
                     filename="test.gcode", timestamp=1700000100, slot=1, active=True,
                     write_marker=True, write_receipt=True, receipt_overrides=None, marker_overrides=None):
        starts_dir = self._private_dir(self.state_dir / "starts" / self.device16)
        plan = make_plan(self.device_digest, file_sha256, filename=filename, slot=slot)
        identity = attempt_id(self.device_digest, file_sha256, previous)
        digest = review_digest(plan, previous)
        key = file_sha256 if previous is None else identity

        receipt = {**plan, "plan_sha256": digest, "dry_run": False, "status": status}
        if timestamp is not None:
            receipt["timestamp"] = timestamp
        if active:
            receipt["after"] = {"state": "printing"}
            receipt["project"] = {"filename": filename}
        if not legacy:
            receipt["attempt_id"] = identity
            if previous is not None:
                receipt["previous_attempt_id"] = previous
            marker = {
                "attempt_id": identity,
                "device_digest": self.device_digest,
                "plan_sha256": digest,
                "sha256": file_sha256,
                "previous_attempt_id": previous,
            }
        else:
            marker = {"sha256": file_sha256, "plan_sha256": digest}

        if marker_overrides:
            marker.update(marker_overrides)
        if receipt_overrides:
            receipt.update(receipt_overrides)

        marker_path = starts_dir / f"{key}.attempt"
        receipt_path = starts_dir / f"{key}.json"
        if write_marker:
            atomic_json(marker_path, marker)
        if write_receipt:
            atomic_json(receipt_path, receipt)
        return identity, marker_path, receipt_path

    def _snapshot(self):
        if not self.state_dir.exists():
            return {}
        return {
            path.relative_to(self.state_dir): (
                stat.S_IMODE(path.lstat().st_mode),
                path.read_bytes() if path.is_file() and not path.is_symlink() else None,
            )
            for path in sorted(self.state_dir.rglob("*"))
        }

    def test_empty_state_returns_empty_history_and_creates_nothing(self):
        report = list_jobs(self.cfg, self.state_dir)
        self.assertEqual(report, {
            "device_digest": self.device_digest,
            "kind": "all",
            "limit": 50,
            "total_count": 0,
            "returned_count": 0,
            "incomplete_count": 0,
            "truncated": False,
            "jobs": [],
            "coverage": COVERAGE,
        })
        self.assertFalse(self.state_dir.exists())
        with self.assertRaises(ProtocolError):
            job_info(self.cfg, self.state_dir, "a" * 64)
        self.assertFalse(self.state_dir.exists())

    def test_legacy_and_current_starts_and_multi_step_reprint_chain_preserve_files(self):
        legacy_sha = "1" * 64
        self._write_upload(legacy_sha, filename="legacy.gcode", timestamp=1700000010)
        legacy_id, _, _ = self._write_start(
            legacy_sha, legacy=True, filename="legacy.gcode", timestamp=None, status="start_observed_active"
        )

        chain_sha = "2" * 64
        self._write_upload(chain_sha, filename="chain.gcode", timestamp=1700000020)
        root_id, _, _ = self._write_start(
            chain_sha, previous=None, filename="chain.gcode", timestamp=1700000100, status="start_observed_active"
        )
        reprint1_id, _, _ = self._write_start(
            chain_sha, previous=root_id, filename="chain.gcode", timestamp=1700000200, status="start_observed_active",
            slot=3,
        )
        reprint2_id, _, _ = self._write_start(
            chain_sha, previous=reprint1_id, filename="chain.gcode", timestamp=1700000300, status="start_observed_active",
            slot=1,
        )

        ack_sha = "3" * 64
        self._write_upload(ack_sha, filename="ack.gcode", timestamp=1700000030)
        ack_id, _, _ = self._write_start(
            ack_sha, filename="ack.gcode", timestamp=1700000250, status="start_acknowledged_not_confirmed", active=False
        )

        no_upload_sha = "4" * 64
        no_upload_id, _, _ = self._write_start(
            no_upload_sha, filename="noupload.gcode", timestamp=1700000150, status="start_observed_active"
        )

        before = self._snapshot()
        listed = list_jobs(self.cfg, self.state_dir)
        self.assertEqual(listed["total_count"], 6)
        self.assertEqual(listed["returned_count"], 6)
        self.assertEqual(listed["incomplete_count"], 0)
        self.assertFalse(listed["truncated"])
        # Newest-first ordering; legacy without timestamp sorts last.
        self.assertEqual(
            [item["record_id"] for item in listed["jobs"]],
            [reprint2_id, ack_id, reprint1_id, no_upload_id, root_id, legacy_id],
        )

        legacy_detail = job_info(self.cfg, self.state_dir, legacy_id)
        self.assertEqual(legacy_detail["record_format"], "legacy")
        self.assertEqual(legacy_detail["completeness"], "complete")
        self.assertEqual(legacy_detail["reprint_eligibility"], "eligible_for_plan")
        self.assertEqual(legacy_detail["terminal_outcome"], "unknown")
        self.assertTrue(legacy_detail["upload_provenance"]["verified"])
        self.assertFalse(legacy_detail["upload_provenance"]["remote_byte_hash_verified"])

        root_detail = job_info(self.cfg, self.state_dir, root_id)
        self.assertEqual(root_detail["record_format"], "current")
        self.assertIsNone(root_detail["previous_attempt_id"])
        self.assertEqual(root_detail["next_attempt_id"], reprint1_id)
        self.assertEqual(root_detail["reprint_eligibility"], "superseded")
        self.assertEqual(root_detail["terminal_outcome"], "unknown")
        self.assertEqual(root_detail["preparation"], {
            "auto_leveling": True, "vibration_compensation": False, "flow_calibration": False
        })
        self.assertEqual(root_detail["selected_slot"], 1)
        self.assertEqual(root_detail["material_type"], "PLA High Speed")
        self.assertTrue(root_detail["hardware_start_validated"])

        reprint1_detail = job_info(self.cfg, self.state_dir, reprint1_id)
        self.assertEqual(reprint1_detail["previous_attempt_id"], root_id)
        self.assertEqual(reprint1_detail["next_attempt_id"], reprint2_id)
        self.assertEqual(reprint1_detail["reprint_eligibility"], "superseded")
        self.assertEqual(reprint1_detail["selected_slot"], 3)
        self.assertFalse(reprint1_detail["hardware_start_validated"])

        reprint2_detail = job_info(self.cfg, self.state_dir, reprint2_id)
        self.assertEqual(reprint2_detail["previous_attempt_id"], reprint1_id)
        self.assertIsNone(reprint2_detail["next_attempt_id"])
        self.assertEqual(reprint2_detail["reprint_eligibility"], "eligible_for_plan")

        self.assertEqual(
            job_info(self.cfg, self.state_dir, ack_id)["reprint_eligibility"],
            "blocked_not_observed_active",
        )
        self.assertEqual(
            job_info(self.cfg, self.state_dir, no_upload_id)["reprint_eligibility"],
            "blocked_missing_upload_provenance",
        )
        self.assertEqual(self._snapshot(), before)

    def test_incomplete_mismatched_orphan_cross_device_and_corrupt_starts(self):
        starts_dir = self._private_dir(self.state_dir / "starts" / self.device16)

        # 1. Valid root superseded by a marker-only successor
        valid_sha = "1" * 64
        self._write_upload(valid_sha, filename="ok.gcode")
        root_id, _, _ = self._write_start(valid_sha, filename="ok.gcode", timestamp=1700000100)
        marker_only_succ_id, _, _ = self._write_start(
            valid_sha, previous=root_id, filename="ok.gcode", write_receipt=False
        )

        # 2. Receipt-only root
        receipt_only_sha = "2" * 64
        receipt_only_id, _, _ = self._write_start(
            receipt_only_sha, filename="ro.gcode", timestamp=1700000200, write_marker=False
        )

        # 3. Mismatched marker/receipt (wrong plan_sha256)
        mismatch_sha = "3" * 64
        mismatch_id, _, _ = self._write_start(
            mismatch_sha, filename="mm.gcode", timestamp=1700000300,
            receipt_overrides={"plan_sha256": "f" * 64},
        )

        # 4. Unverified active evidence (project filename mismatch)
        unverified_sha = "4" * 64
        unverified_id, _, _ = self._write_start(
            unverified_sha, filename="uv.gcode", timestamp=1700000400,
            receipt_overrides={"project": {"filename": "other.gcode"}},
        )

        # 5. Orphan successor (predecessor does not exist)
        orphan_prev = "9" * 64
        orphan_id, _, _ = self._write_start(
            "5" * 64, previous=orphan_prev, filename="orphan.gcode", timestamp=1700000500
        )

        # 6. Cross-device mismatch placed in this device16 directory
        cross_sha = "6" * 64
        other_digest = "e" * 64
        cross_plan = make_plan(other_digest, cross_sha, filename="cross.gcode")
        atomic_json(starts_dir / f"{cross_sha}.attempt", {
            "attempt_id": attempt_id(other_digest, cross_sha, None),
            "device_digest": other_digest,
            "plan_sha256": cross_plan["plan_sha256"],
            "sha256": cross_sha,
            "previous_attempt_id": None,
        })
        atomic_json(starts_dir / f"{cross_sha}.json", {**cross_plan, "dry_run": False, "status": "start_reserved"})

        # 7. Corrupt unreadable pair
        corrupt_key = "7" * 64
        (starts_dir / f"{corrupt_key}.attempt").write_text("{broken")
        (starts_dir / f"{corrupt_key}.attempt").chmod(0o600)
        (starts_dir / f"{corrupt_key}.json").write_text("not json")
        (starts_dir / f"{corrupt_key}.json").chmod(0o600)

        # Stray lock/tmp files must be ignored
        (starts_dir / ".start.lock").write_text("")
        (starts_dir / ".start.lock").chmod(0o600)
        (starts_dir / f"{corrupt_key}.json.1234.tmp").write_text("{")
        (starts_dir / f"{corrupt_key}.json.1234.tmp").chmod(0o600)

        before = self._snapshot()
        listed = list_jobs(self.cfg, self.state_dir)
        by_id = {item["record_id"]: item for item in listed["jobs"]}
        self.assertEqual(listed["total_count"], 8)
        self.assertEqual(listed["incomplete_count"], 7)

        self.assertEqual(by_id[root_id]["completeness"], "complete")
        self.assertEqual(by_id[root_id]["reprint_eligibility"], "superseded")

        self.assertEqual(by_id[marker_only_succ_id]["completeness"], "incomplete")
        self.assertIn("missing_receipt", by_id[marker_only_succ_id]["issues"])
        self.assertEqual(by_id[marker_only_succ_id]["reprint_eligibility"], "blocked_incomplete")

        self.assertEqual(by_id[receipt_only_id]["completeness"], "incomplete")
        self.assertIn("missing_marker", by_id[receipt_only_id]["issues"])
        self.assertEqual(by_id[receipt_only_id]["reprint_eligibility"], "blocked_incomplete")

        self.assertEqual(by_id[mismatch_id]["completeness"], "incomplete")
        self.assertIn("receipt_mismatch", by_id[mismatch_id]["issues"])

        self.assertEqual(by_id[unverified_id]["completeness"], "incomplete")
        self.assertIn("unverified_active_evidence", by_id[unverified_id]["issues"])

        self.assertEqual(by_id[orphan_id]["completeness"], "incomplete")
        self.assertIn("missing_predecessor", by_id[orphan_id]["issues"])

        cross_ref = f"unreadable-{cross_sha}"
        self.assertIn(cross_ref, by_id)
        self.assertIn("device_mismatch", by_id[cross_ref]["issues"])
        self.assertIsNone(by_id[cross_ref]["filename"])
        with self.assertRaises(ProtocolError):
            job_info(self.cfg, self.state_dir, attempt_id(other_digest, cross_sha, None))

        corrupt_ref = f"unreadable-{corrupt_key}"
        self.assertIn(corrupt_ref, by_id)
        self.assertEqual(by_id[corrupt_ref]["issues"], ["unreadable_marker", "unreadable_receipt"])
        corrupt_detail = job_info(self.cfg, self.state_dir, corrupt_ref)
        self.assertIsNone(corrupt_detail["attempt_id"])
        self.assertEqual(corrupt_detail["storage_key"], corrupt_key)
        self.assertEqual(self._snapshot(), before)

    def test_corrupt_successor_slot_blocks_root_reprint_eligibility(self):
        starts_dir = self._private_dir(self.state_dir / "starts" / self.device16)
        blocked_sha = "a" * 64
        self._write_upload(blocked_sha, filename="blocked.gcode")
        blocked_root, _, _ = self._write_start(blocked_sha, filename="blocked.gcode", timestamp=1700000100)
        succ_key = attempt_id(self.device_digest, blocked_sha, blocked_root)
        corrupt_succ = starts_dir / f"{succ_key}.attempt"
        corrupt_succ.write_text("{corrupt")
        corrupt_succ.chmod(0o600)

        free_sha = "b" * 64
        self._write_upload(free_sha, filename="free.gcode")
        free_root, _, _ = self._write_start(free_sha, filename="free.gcode", timestamp=1700000200)

        listed = list_jobs(self.cfg, self.state_dir, kind="start")
        by_id = {item["record_id"]: item for item in listed["jobs"]}
        self.assertEqual(by_id[blocked_root]["completeness"], "complete")
        self.assertEqual(by_id[blocked_root]["reprint_eligibility"], "superseded")
        self.assertEqual(by_id[free_root]["reprint_eligibility"], "eligible_for_plan")
        unreadable_ref = f"unreadable-{succ_key}"
        self.assertIn(unreadable_ref, by_id)
        self.assertEqual(by_id[unreadable_ref]["issues"], ["unreadable_marker", "missing_receipt"])
        self.assertEqual(job_info(self.cfg, self.state_dir, unreadable_ref)["storage_key"], succ_key)
        self.assertEqual(job_info(self.cfg, self.state_dir, blocked_root)["reprint_eligibility"], "superseded")

    def test_wrong_type_and_foreign_observations_degrade_safely(self):
        obs_dir = self._private_dir(self.state_dir / "observations" / self.device16)
        valid_obs = persist_observation(
            self.state_dir, self.device_digest, 1700000300, "good.gcode",
            {"outcome": "unknown", "reason": "deadline_expired", "phase": "printing", "progress": 10},
        )
        # Wrong-type unhashable fields (list/dict) must not raise TypeError; test each enum independently
        base_obs = {
            "version": 1, "device_digest": self.device_digest,
            "observed_at": 1700000200, "ended_at": 1700000210, "observed_filename": "bad.gcode",
            "client_attribution": "unattributed", "outcome": "unknown", "reason": "deadline_expired",
            "phase": "printing",
        }
        bad_enum_ids = {}
        for idx, (field, bad_value) in enumerate((
            ("outcome", ["unknown"]),
            ("reason", []),
            ("phase", {}),
        ), start=1):
            obs_id = f"obs-{str(idx) * 32}"
            bad_enum_ids[field] = obs_id
            atomic_json(obs_dir / f"{obs_id}.json", {**base_obs, "observation_id": obs_id, field: bad_value})
        # Malformed local observation missing device_digest stays inspectable as invalid_observation
        missing_dev_obs = "obs-" + "4" * 32
        atomic_json(obs_dir / f"{missing_dev_obs}.json", {"version": 1, "observation_id": missing_dev_obs})
        # Foreign device observation copied into this device's directory
        foreign_obs = "obs-" + "5" * 32
        atomic_json(obs_dir / f"{foreign_obs}.json", {
            "version": 1, "observation_id": foreign_obs, "device_digest": "e" * 64,
            "observed_at": 1700000250, "ended_at": 1700000260, "observed_filename": "foreign.gcode",
            "client_attribution": "unattributed", "outcome": "unknown", "reason": "job_disappeared",
            "phase": "printing",
        })

        listed = list_jobs(self.cfg, self.state_dir, kind="observation")
        by_id = {item["record_id"]: item for item in listed["jobs"]}
        self.assertEqual(by_id[valid_obs]["completeness"], "complete")
        for field, obs_id in bad_enum_ids.items():
            with self.subTest(field=field):
                self.assertEqual(by_id[obs_id]["completeness"], "incomplete")
                self.assertEqual(by_id[obs_id]["issues"], ["invalid_observation"])
                self.assertEqual(job_info(self.cfg, self.state_dir, obs_id)["issues"], ["invalid_observation"])
        self.assertEqual(by_id[missing_dev_obs]["completeness"], "incomplete")
        self.assertEqual(by_id[missing_dev_obs]["issues"], ["invalid_observation"])
        self.assertEqual(by_id[foreign_obs]["completeness"], "incomplete")
        self.assertEqual(by_id[foreign_obs]["issues"], ["device_mismatch"])

        self.assertEqual(job_info(self.cfg, self.state_dir, valid_obs)["observed_filename"], "good.gcode")
        self.assertEqual(job_info(self.cfg, self.state_dir, missing_dev_obs)["issues"], ["invalid_observation"])
        with self.assertRaises(ProtocolError):
            job_info(self.cfg, self.state_dir, foreign_obs)

    def test_observations_filtering_pagination_and_unattributed_correlation(self):
        sha = "a" * 64
        self._write_upload(sha, filename="sample.gcode", timestamp=1700000000)
        att_id, _, _ = self._write_start(sha, filename="sample.gcode", timestamp=1700000100)

        obs_dir = self._private_dir(self.state_dir / "observations" / self.device16)
        # Observation before start (should NOT correlate)
        obs_early = "obs-" + "1" * 32
        atomic_json(obs_dir / f"{obs_early}.json", {
            "version": 1, "observation_id": obs_early, "device_digest": self.device_digest,
            "observed_at": 1700000050, "ended_at": 1700000060, "observed_filename": "sample.gcode",
            "client_attribution": "unattributed", "outcome": "unknown", "reason": "job_disappeared",
            "phase": "printing", "progress": 50, "current_layer": 50, "total_layers": 100,
        })
        # Observation after start with matching filename (SHOULD correlate as unattributed)
        obs_match = "obs-" + "2" * 32
        atomic_json(obs_dir / f"{obs_match}.json", {
            "version": 1, "observation_id": obs_match, "device_digest": self.device_digest,
            "observed_at": 1700000200, "ended_at": 1700000300, "observed_filename": "sample.gcode",
            "client_attribution": "unattributed", "outcome": "unknown", "reason": "deadline_expired",
            "phase": "printing", "progress": 12, "current_layer": 8, "total_layers": 100,
        })
        # Observation of another client's job with different filename
        obs_other = persist_observation(
            self.state_dir, self.device_digest, 1700000400, "other-client.gcode",
            {"outcome": "unknown", "reason": "job_disappeared", "phase": "preparing"},
        )
        self.assertIsNotNone(obs_other)
        # Malformed observation file alongside valid ones
        obs_bad = "obs-" + "f" * 32
        bad_path = obs_dir / f"{obs_bad}.json"
        bad_path.write_text("{corrupt")
        bad_path.chmod(0o600)

        # All records
        all_jobs = list_jobs(self.cfg, self.state_dir)
        self.assertEqual(all_jobs["total_count"], 5)
        self.assertEqual(all_jobs["returned_count"], 5)
        self.assertEqual(all_jobs["incomplete_count"], 1)
        self.assertFalse(all_jobs["truncated"])
        self.assertEqual(
            [j["record_id"] for j in all_jobs["jobs"]],
            [obs_other, obs_match, att_id, obs_early, obs_bad],
        )

        # Filter --kind observation --limit 1
        filtered = list_jobs(self.cfg, self.state_dir, kind="observation", limit=1)
        self.assertEqual(filtered["kind"], "observation")
        self.assertEqual(filtered["limit"], 1)
        self.assertEqual(filtered["total_count"], 4)
        self.assertEqual(filtered["returned_count"], 1)
        self.assertEqual(filtered["incomplete_count"], 1)
        self.assertTrue(filtered["truncated"])
        self.assertEqual(filtered["jobs"][0]["record_id"], obs_other)
        self.assertEqual(filtered["jobs"][0]["client_attribution"], "unattributed")

        # Filter --kind start
        starts_only = list_jobs(self.cfg, self.state_dir, kind="start")
        self.assertEqual(starts_only["total_count"], 1)
        self.assertEqual(starts_only["jobs"][0]["record_id"], att_id)

        # Correlation in jobs info <attempt_id>
        detail = job_info(self.cfg, self.state_dir, att_id)
        self.assertEqual(detail["terminal_outcome"], "unknown")
        self.assertEqual(len(detail["unattributed_matching_observations"]), 1)
        matched = detail["unattributed_matching_observations"][0]
        self.assertEqual(matched["observation_id"], obs_match)
        self.assertEqual(matched["attribution"], "unattributed_filename_match")
        self.assertEqual(detail["coverage"], COVERAGE)

        # Inspect valid and unreadable observations
        obs_detail = job_info(self.cfg, self.state_dir, obs_other)
        self.assertEqual(obs_detail["client_attribution"], "unattributed")
        self.assertEqual(obs_detail["observed_filename"], "other-client.gcode")
        self.assertEqual(obs_detail["phase"], "preparing")
        self.assertEqual(obs_detail["coverage"], COVERAGE)

        bad_detail = job_info(self.cfg, self.state_dir, obs_bad)
        self.assertEqual(bad_detail["completeness"], "incomplete")
        self.assertEqual(bad_detail["issues"], ["unreadable_observation"])

    def test_private_directory_safety_and_individual_non_private_degradation(self):
        starts_dir = self._private_dir(self.state_dir / "starts" / self.device16)
        obs_dir = self._private_dir(self.state_dir / "observations" / self.device16)
        valid_sha = "1" * 64
        self._write_upload(valid_sha, filename="ok.gcode")
        valid_id, _, _ = self._write_start(valid_sha, filename="ok.gcode", timestamp=1700000100)

        # Non-private (0644) and symlinked individual files inside valid 0700 dirs degrade to incomplete
        bad_mode_sha = "2" * 64
        bad_mode_id, _, bad_receipt = self._write_start(bad_mode_sha, filename="badmode.gcode", timestamp=1700000200)
        bad_receipt.chmod(0o644)

        decoy = self.root / "decoy.json"
        decoy.write_text('{"secret":"never_read"}')
        decoy.chmod(0o600)
        sym_obs = "obs-" + "a" * 32
        os.symlink(decoy, obs_dir / f"{sym_obs}.json")

        # Oversized observation file (> 1 MiB) degrades to incomplete
        big_obs = "obs-" + "b" * 32
        big_path = obs_dir / f"{big_obs}.json"
        big_path.write_text("{" + " " * (1024 * 1024 + 10) + "}")
        big_path.chmod(0o600)

        listed = list_jobs(self.cfg, self.state_dir)
        by_id = {item["record_id"]: item for item in listed["jobs"]}
        self.assertEqual(by_id[valid_id]["completeness"], "complete")
        self.assertEqual(by_id[bad_mode_id]["completeness"], "incomplete")
        self.assertIn("unreadable_receipt", by_id[bad_mode_id]["issues"])
        self.assertEqual(stat.S_IMODE(bad_receipt.stat().st_mode), 0o644)
        self.assertEqual(by_id[sym_obs]["completeness"], "incomplete")
        self.assertEqual(by_id[sym_obs]["issues"], ["unreadable_observation"])
        self.assertEqual(by_id[big_obs]["completeness"], "incomplete")
        self.assertEqual(by_id[big_obs]["issues"], ["unreadable_observation"])

        # Permissive (0755) device directories fail with ProfileLocalError without changing modes
        for directory in (starts_dir, obs_dir, self.state_dir / self.device16):
            with self.subTest(permissive=directory):
                directory.chmod(0o755)
                with self.assertRaises(ProfileLocalError):
                    list_jobs(self.cfg, self.state_dir)
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
                directory.chmod(0o700)

        # Symlinked device directory fails with ProfileLocalError without following symlink
        real_starts = self.root / "real_starts"
        starts_dir.rename(real_starts)
        os.symlink(real_starts, starts_dir)
        with self.assertRaises(ProfileLocalError):
            list_jobs(self.cfg, self.state_dir)
        with self.assertRaises(ProfileLocalError):
            job_info(self.cfg, self.state_dir, valid_id)
        self.assertTrue(starts_dir.is_symlink())

    def test_cross_profile_consistency_and_sanitization(self):
        def walk_strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for key, item in value.items():
                    yield from walk_strings(key)
                    yield from walk_strings(item)
            elif isinstance(value, list):
                for item in value:
                    yield from walk_strings(item)

        # Control-only fixture (no URL) verifies terminal-control sanitization independently
        ctrl_sha = "c" * 64
        self._write_upload(ctrl_sha, filename="clean.gcode")
        ctrl_id, _, _ = self._write_start(
            ctrl_sha,
            filename="clean.gcode",
            timestamp=1700000100,
            receipt_overrides={"model": "Anycubic\x1b[31m Kobra X\x07"},
        )
        # Separate URL/credential fixture verifies secret redaction
        url_sha = "d" * 64
        self._write_upload(url_sha, filename="url.gcode")
        url_id, _, _ = self._write_start(
            url_sha,
            filename="url.gcode",
            timestamp=1700000150,
            receipt_overrides={"model": "https://example.test/?token=SECRET"},
        )
        # Hostile observation file with URL + ESC filename is rejected as invalid_observation
        obs_dir = self._private_dir(self.state_dir / "observations" / self.device16)
        hostile_obs = "obs-" + "d" * 32
        atomic_json(obs_dir / f"{hostile_obs}.json", {
            "version": 1, "observation_id": hostile_obs, "device_digest": self.device_digest,
            "observed_at": 1700000200, "ended_at": 1700000210,
            "observed_filename": "https://example.test/?token=SYNTHETIC_SECRET\x1b[31m",
            "client_attribution": "unattributed", "outcome": "unknown", "reason": "job_disappeared",
            "phase": "printing",
        })

        other_profile_cfg = config()
        other_profile_cfg.host = "192.0.2.99"  # Same printer_id, different profile config
        first = list_jobs(self.cfg, self.state_dir)
        second = list_jobs(other_profile_cfg, self.state_dir)
        self.assertEqual(first, second)

        ctrl_detail = job_info(self.cfg, self.state_dir, ctrl_id)
        self.assertIsNotNone(ctrl_detail["model"])
        self.assertNotIn("\x1b", ctrl_detail["model"])
        self.assertNotIn("\x07", ctrl_detail["model"])
        url_detail = job_info(self.cfg, self.state_dir, url_id)
        self.assertIsNone(url_detail["model"])
        obs_detail = job_info(self.cfg, self.state_dir, hostile_obs)
        self.assertEqual(obs_detail["completeness"], "incomplete")
        self.assertEqual(obs_detail["issues"], ["invalid_observation"])
        for payload in (first, ctrl_detail, url_detail, obs_detail):
            for text in walk_strings(payload):
                self.assertNotIn("SECRET", text)
                self.assertFalse(any(unicodedata.category(c).startswith("C") for c in text), repr(text))


class JobsCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state_dir = self.root / "state"
        self.registry = Registry(self.root / "private")
        with self.registry.lock():
            for name, device in (
                ("default", "SyntheticDefault"),
                ("alias", "SyntheticDefault"),
                ("other", "SyntheticOther"),
            ):
                fixture(self.registry.reserve(name), device=device)
                self.registry.register(name, "2.0.2.2")
        self.registry.select("default")
        self.explicit = self.root / "explicit.json"
        fixture(self.explicit, device="SyntheticDefault")
        self.enterContext(patch("kobra_lan.cli.Registry", return_value=self.registry))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("network forbidden")))

    def invoke(self, args, expected):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(args), expected)
        self.assertEqual(err.getvalue(), "")
        return out.getvalue()

    def test_invalid_arguments_exit_2_before_target_selection_without_echoing_input(self):
        secret = "https://example.test/?token=SYNTHETIC_PRIVATE\x1b[31m"
        cases = (
            ["jobs", "list", "--kind", "invalid"],
            ["jobs", "list", "--kind", secret],
            ["jobs", "list", "--limit", "0"],
            ["jobs", "list", "--limit", "-5"],
            ["jobs", "list", "--limit", "501"],
            ["jobs", "list", "--limit", "1.5"],
            ["jobs", "list", "--limit", "1_0"],
            ["jobs", "list", "--limit", secret],
            ["jobs", "info", "not-a-valid-id"],
            ["jobs", "info", "A" * 64],
            ["jobs", "info", "obs-" + "a" * 31],
            ["jobs", "info", secret],
        )
        for argv in cases:
            for fmt in ([], ["--json"]):
                with self.subTest(argv=argv, fmt=fmt), patch("kobra_lan.cli.Registry") as registry:
                    rendered = self.invoke([*fmt, *argv], 2)
                    registry.assert_not_called()
                    self.assertNotIn("SYNTHETIC_PRIVATE", rendered)
                    self.assertNotIn("\x1b", rendered)
                    if fmt:
                        self.assertEqual(json.loads(rendered)["error"]["code"], "invalid_arguments")

    def test_target_selectors_text_and_json_and_cross_device_refusal(self):
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        other_digest = hashlib.sha256(b"SyntheticOther").hexdigest()

        obs_id = persist_observation(
            self.state_dir, digest, 1700000200, "watched.gcode",
            {"outcome": "unknown", "reason": "deadline_expired", "phase": "printing", "progress": 42},
        )
        other_obs_id = persist_observation(
            self.state_dir, other_digest, 1700000250, "other.gcode",
            {"outcome": "unknown", "reason": "job_disappeared", "phase": "preparing"},
        )
        self.assertIsNotNone(obs_id)
        self.assertIsNotNone(other_obs_id)

        # Default, named alias, and explicit --config for same printer_id produce identical JSON results.
        results = []
        for selector in ([], ["--printer", "alias"], ["--config", str(self.explicit)]):
            raw = self.invoke(["--json", *selector, "--state-dir", str(self.state_dir), "jobs", "list"], 0)
            envelope = json.loads(raw)
            self.assertTrue(envelope["ok"])
            self.assertEqual(envelope["schema_version"], 1)
            results.append(envelope["result"])
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0], results[2])
        self.assertEqual(results[0]["total_count"], 1)
        self.assertEqual(results[0]["jobs"][0]["record_id"], obs_id)
        self.assertEqual(results[0]["coverage"], COVERAGE)

        # Text output exposes equivalent fields and coverage metadata.
        text_list = self.invoke(["--state-dir", str(self.state_dir), "jobs", "list"], 0)
        self.assertIn(obs_id, text_list)
        self.assertIn("watched.gcode", text_list)
        self.assertIn("local_state_only", text_list)
        self.assertIn("only_when_watched_unattributed", text_list)

        json_info = json.loads(self.invoke(
            ["--json", "--state-dir", str(self.state_dir), "jobs", "info", obs_id], 0
        ))
        self.assertEqual(json_info["result"]["observation_id"], obs_id)
        self.assertEqual(json_info["result"]["client_attribution"], "unattributed")
        self.assertEqual(json_info["result"]["coverage"], COVERAGE)

        text_info = self.invoke(["--state-dir", str(self.state_dir), "jobs", "info", obs_id], 0)
        self.assertIn(obs_id, text_info)
        self.assertIn("unattributed", text_info)
        self.assertIn("watched.gcode", text_info)
        self.assertIn("local_state_only", text_info)

        # Unknown and cross-device IDs exit 2 in both modes.
        for bad_id in ("a" * 64, other_obs_id):
            for fmt in ([], ["--json"]):
                rendered = self.invoke([*fmt, "--state-dir", str(self.state_dir), "jobs", "info", bad_id], 2)
                if fmt:
                    self.assertEqual(json.loads(rendered)["error"]["code"], "validation_failed")

        # Permissive device directory exits 3 with operation_failed.
        obs_dir = self.state_dir / "observations" / digest[:16]
        obs_dir.chmod(0o755)
        try:
            rendered = self.invoke(["--json", "--state-dir", str(self.state_dir), "jobs", "list"], 3)
            self.assertEqual(json.loads(rendered)["error"]["code"], "operation_failed")
            self.assertEqual(stat.S_IMODE(obs_dir.stat().st_mode), 0o755)
        finally:
            obs_dir.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
