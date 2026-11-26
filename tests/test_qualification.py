"""Offline unit tests for the centralized hardware qualification registry."""
from dataclasses import FrozenInstanceError
import unittest

from kobra_lan import qualification as q


class QualificationRegistryTests(unittest.TestCase):
    def test_profile_and_registry_are_immutable(self):
        self.assertEqual(q.KOBRA_X.model_id, 20030)
        self.assertEqual(q.KOBRA_X.model_name, "Anycubic Kobra X")
        self.assertEqual(q.KOBRA_X.short_name, "Kobra X")
        self.assertEqual(q.QUALIFIED_FIRMWARE, "2.0.2.2")
        self.assertEqual(q.KOBRA_X.firmware_versions, frozenset({"2.0.2.2"}))
        self.assertEqual(q.QUALIFICATION_SUMMARY, "Kobra X model 20030 / firmware 2.0.2.2")
        self.assertIs(q.QUALIFIED_PRINTERS[20030], q.KOBRA_X)

        with self.assertRaises(TypeError):
            q.QUALIFIED_PRINTERS[20031] = q.KOBRA_X
        with self.assertRaises(FrozenInstanceError):
            q.KOBRA_X.model_id = 20031
        with self.assertRaises(FrozenInstanceError):
            q.KOBRA_X.onboard_box.slot_count = 8
        with self.assertRaises(FrozenInstanceError):
            q.KOBRA_X.start_evidence[0].slot_maps = frozenset()

    def test_model_id_lookup_and_normalization(self):
        self.assertIs(q.qualification_for_model_id(20030), q.KOBRA_X)
        for bad in (20031, "20030", None, True, False, 20030.0):
            with self.subTest(bad=bad):
                self.assertIsNone(q.qualification_for_model_id(bad))

        for values in ([20030], ["20030"], [20030, "20030"], ("20030", 20030)):
            with self.subTest(values=values):
                self.assertEqual(q.normalize_qualified_model_id(values), 20030)

        for values in (
            [],
            [20031],
            ["20031"],
            ["020030"],
            [" 20030 "],
            [20030, 20031],
            [20030, "20031"],
            [True],
            [20030.0],
            [None],
        ):
            with self.subTest(values=values):
                self.assertIsNone(q.normalize_qualified_model_id(values))

    def test_profile_firmware_validation(self):
        self.assertTrue(q.is_qualified_profile_firmware(None))
        self.assertTrue(q.is_qualified_profile_firmware("2.0.2.2"))
        for bad in ("2.0.2.3", "", " 2.0.2.2", 2022, True):
            with self.subTest(bad=bad):
                self.assertFalse(q.is_qualified_profile_firmware(bad))

    def test_info_compatibility_issue_and_precedence(self):
        base = {
            "model": "Anycubic Kobra X",
            "version": "2.0.2.2",
            "state": "free",
            "deviceId": "Synthetic01",
            "modelId": 20030,
            "modeId": "20030",
        }
        self.assertIsNone(q.info_compatibility_issue(20030, "Synthetic01", base))
        # Optional IDs may be omitted cleanly.
        self.assertIsNone(
            q.info_compatibility_issue(
                20030,
                "Synthetic01",
                {"model": "Anycubic Kobra X", "version": "2.0.2.2", "state": "printing"},
            )
        )

        # Missing required fields without conflict -> qualification_incomplete.
        for missing in ("model", "version", "state"):
            with self.subTest(missing=missing):
                partial = {k: v for k, v in base.items() if k != missing}
                self.assertEqual(
                    q.info_compatibility_issue(20030, "Synthetic01", partial),
                    "qualification_incomplete",
                )
                partial_none = {**base, missing: None}
                self.assertEqual(
                    q.info_compatibility_issue(20030, "Synthetic01", partial_none),
                    "qualification_incomplete",
                )

        # Conflicts always take precedence over missing required fields.
        conflicts = (
            {**base, "model": "Other Printer", "version": None},
            {**base, "version": "2.0.2.3", "state": None},
            {**base, "version": 2022},
            {**base, "deviceId": "Other01", "state": None},
            {**base, "deviceId": None},
            {**base, "modelId": 20031, "version": None},
            {**base, "modelId": None},
            {**base, "modelId": True},
            {**base, "modeId": "20031", "model": None},
            {**base, "state": ""},
            {**base, "state": "\x1b[31m"},
            {**base, "state": "x" * 81},
            {**base, "state": 123},
        )
        for info in conflicts:
            with self.subTest(info=info):
                self.assertEqual(
                    q.info_compatibility_issue(20030, "Synthetic01", info),
                    "outside_qualification",
                )

        # Unqualified model_id or non-mapping info -> outside_qualification.
        self.assertEqual(q.info_compatibility_issue(20031, "Synthetic01", base), "outside_qualification")
        self.assertEqual(q.info_compatibility_issue(20030, "Synthetic01", None), "outside_qualification")

    def test_remote_model_and_slicer_marker_checks(self):
        self.assertTrue(q.is_qualified_remote_model(20030, "Anycubic Kobra X"))
        self.assertFalse(q.is_qualified_remote_model(20030, "Other"))
        self.assertFalse(q.is_qualified_remote_model(20030, None))
        self.assertFalse(q.is_qualified_remote_model(20031, "Anycubic Kobra X"))

        valid = b"; header\n; printer_model = Anycubic Kobra X\nG1 X0\n"
        self.assertTrue(q.matches_slicer_model_marker(valid))
        self.assertTrue(q.matches_slicer_model_marker(valid, 20030))
        self.assertFalse(q.matches_slicer_model_marker(valid, 20031))
        self.assertFalse(q.matches_slicer_model_marker(b"; printer_model = Other\n"))
        self.assertFalse(q.matches_slicer_model_marker("; printer_model = Anycubic Kobra X"))

    def test_onboard_topology_and_slot_bounds(self):
        topo = q.onboard_topology(20030)
        self.assertEqual(topo, q.OnboardBoxTopology(box_id=-1, box_kind="onboard", slot_count=4))
        self.assertEqual(q.onboard_topology(), topo)
        self.assertIsNone(q.onboard_topology(20031))
        self.assertIsNone(q.onboard_topology(None))

        for slot in (1, 2, 3, 4):
            self.assertTrue(q.is_valid_onboard_slot(20030, slot))
        for bad_slot in (0, 5, -1, "1", True, False, None, 1.0):
            with self.subTest(bad_slot=bad_slot):
                self.assertFalse(q.is_valid_onboard_slot(20030, bad_slot))
        self.assertFalse(q.is_valid_onboard_slot(20031, 1))

    def test_start_control_and_delete_hardware_validation_predicates(self):
        # Observed baseline-prep (auto=on, vib=off, flow=off) PLA High Speed across all onboard mapping classes.
        observed_baseline_pla_maps = (
            ("slot 1 single", {0: 1}),
            ("slot 2 single", {0: 2}),
            ("slot 3 single", {0: 3}),
            ("slot 4 single", {0: 4}),
            ("non-zero single paint_index", {2: 3}),
            ("4-color contiguous 1:1", {0: 1, 1: 2, 2: 3, 3: 4}),
            ("4-color reordered dict", {3: 4, 0: 1, 2: 3, 1: 2}),
            ("2-color cross-remapped subset", {0: 2, 1: 1}),
            ("2-color sparse indices", {0: 1, 2: 3}),
            ("3-color cross-remapped subset", {0: 4, 1: 2, 2: 1}),
            ("shared physical slot 2-color", {0: 1, 1: 1}),
            ("shared physical slot 4-color", {0: 1, 1: 1, 2: 3, 3: 4}),
        )
        for label, slot_map in observed_baseline_pla_maps:
            materials = {paint_index: "PLA High Speed" for paint_index in slot_map}
            with self.subTest(case=label):
                self.assertTrue(
                    q.is_start_hardware_validated(
                        20030,
                        "2.0.2.2",
                        slot_map=slot_map,
                        materials=materials,
                        auto_leveling=True,
                        vibration_compensation=False,
                        flow_calibration=False,
                    )
                )

        # Observed single-filament slot 1 PLA High Speed across alternative single-flag prep tuples.
        for auto, vib, flow in ((False, False, False), (False, True, False), (False, False, True)):
            with self.subTest(alt_prep=(auto, vib, flow)):
                self.assertTrue(
                    q.is_start_hardware_validated(
                        20030,
                        "2.0.2.2",
                        slot_map={0: 1},
                        materials={0: "PLA High Speed"},
                        auto_leveling=auto,
                        vibration_compensation=vib,
                        flow_calibration=flow,
                    )
                )

        # Observed single-filament PETG on onboard slot 4 with baseline prep flags.
        self.assertTrue(
            q.is_start_hardware_validated(
                20030,
                "2.0.2.2",
                slot_map={0: 4},
                materials={0: "PETG"},
                auto_leveling=True,
                vibration_compensation=False,
                flow_calibration=False,
            )
        )

        four_color_materials = {0: "PLA High Speed", 1: "PLA High Speed", 2: "PLA High Speed", 3: "PLA High Speed"}
        # Unobserved combinations must remain False.
        negative_cases = (
            ("alt prep unobserved slot 3 off/off/off", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 3}, materials={0: "PLA High Speed"}, auto_leveling=False, vibration_compensation=False, flow_calibration=False)),
            ("alt prep shared slot off/on/off", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 1}, materials={0: "PLA High Speed", 1: "PLA High Speed"}, auto_leveling=False, vibration_compensation=True, flow_calibration=False)),
            ("alt prep shared slot off/off/on", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 1}, materials={0: "PLA High Speed", 1: "PLA High Speed"}, auto_leveling=False, vibration_compensation=False, flow_calibration=True)),
            ("alt prep multicolor off/off/off", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials=four_color_materials, auto_leveling=False, vibration_compensation=False, flow_calibration=False)),
            ("alt prep multicolor off/on/off", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials=four_color_materials, auto_leveling=False, vibration_compensation=True, flow_calibration=False)),
            ("alt prep multicolor off/off/on", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials=four_color_materials, auto_leveling=False, vibration_compensation=False, flow_calibration=True)),
            ("unobserved prep auto+vib", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=True, vibration_compensation=True, flow_calibration=False)),
            ("unobserved prep auto+flow", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=True, vibration_compensation=False, flow_calibration=True)),
            ("unobserved prep vib+flow", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=False, vibration_compensation=True, flow_calibration=True)),
            ("unobserved prep all on", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=True, vibration_compensation=True, flow_calibration=True)),
            ("PETG untested slot 1", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PETG"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("PETG untested non-zero index", dict(model_id=20030, firmware="2.0.2.2", slot_map={2: 4}, materials={2: "PETG"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("PETG untested multicolor", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 4, 1: 4}, materials={0: "PETG", 1: "PETG"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("PETG untested prep off/off/off", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 4}, materials={0: "PETG"}, auto_leveling=False, vibration_compensation=False, flow_calibration=False)),
            ("PETG untested prep vib on", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 4}, materials={0: "PETG"}, auto_leveling=False, vibration_compensation=True, flow_calibration=False)),
            ("PETG untested prep flow on", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 4}, materials={0: "PETG"}, auto_leveling=False, vibration_compensation=False, flow_calibration=True)),
            ("mixed PLA High Speed + PETG", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 2: 4}, materials={0: "PLA High Speed", 2: "PETG"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("material plain PLA", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("material TPU", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "TPU"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("multicolor mixed material", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials={0: "PLA High Speed", 1: "PLA High Speed", 2: "PLA High Speed", 3: "PLA"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("multicolor unobserved prep auto+vib", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials=four_color_materials, auto_leveling=True, vibration_compensation=True, flow_calibration=False)),
            ("multicolor unobserved prep auto+flow", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials=four_color_materials, auto_leveling=True, vibration_compensation=False, flow_calibration=True)),
            ("multicolor unqualified firmware", dict(model_id=20030, firmware="2.0.2.3", slot_map={0: 1, 1: 2, 2: 3, 3: 4}, materials=four_color_materials, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("negative paint_index", dict(model_id=20030, firmware="2.0.2.2", slot_map={-1: 1}, materials={-1: "PLA High Speed"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("bool paint_index", dict(model_id=20030, firmware="2.0.2.2", slot_map={True: 1}, materials={True: "PLA High Speed"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("empty mapping", dict(model_id=20030, firmware="2.0.2.2", slot_map={}, materials={}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("mismatched keys", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={1: "PLA High Speed"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("unqualified firmware", dict(model_id=20030, firmware="2.0.2.3", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("unqualified model", dict(model_id=20031, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=True, vibration_compensation=False, flow_calibration=False)),
            ("non-bool prep flag", dict(model_id=20030, firmware="2.0.2.2", slot_map={0: 1}, materials={0: "PLA High Speed"}, auto_leveling=1, vibration_compensation=False, flow_calibration=False)),
        )
        for label, kwargs in negative_cases:
            with self.subTest(case=label):
                self.assertFalse(q.is_start_hardware_validated(**kwargs))

        # Distinct-only evidence helper refuses shared physical slots unless explicitly allowed.
        distinct_only = q.StartHardwareEvidence(
            slot_maps=frozenset(),
            materials=frozenset({"PLA High Speed"}),
            auto_leveling=True,
            vibration_compensation=False,
            flow_calibration=False,
            allow_any_distinct_onboard_slot_map=True,
            allow_shared_onboard_slots=False,
        )
        self.assertTrue(q._evidence_matches_slot_map(distinct_only, ((0, 2), (1, 1))))
        self.assertFalse(q._evidence_matches_slot_map(distinct_only, ((0, 1), (1, 1))))

        self.assertTrue(q.is_control_hardware_validated(20030, "2.0.2.2"))
        self.assertFalse(q.is_control_hardware_validated(20030, "2.0.2.3"))
        self.assertFalse(q.is_control_hardware_validated(20031, "2.0.2.2"))

        self.assertTrue(q.KOBRA_X.delete_hardware_validated)
        self.assertTrue(q.is_delete_hardware_validated(20030, "2.0.2.2"))
        self.assertFalse(q.is_delete_hardware_validated(20030, "2.0.2.3"))
        self.assertFalse(q.is_delete_hardware_validated(20031, "2.0.2.2"))
        self.assertFalse(q.is_delete_hardware_validated(20030, None))
        self.assertFalse(q.is_delete_hardware_validated(True, "2.0.2.2"))

        self.assertTrue(q.KOBRA_X.camera_hardware_validated)
        self.assertTrue(q.is_camera_hardware_validated(20030, "2.0.2.2"))
        self.assertFalse(q.is_camera_hardware_validated(20030, "2.0.2.3"))
        self.assertFalse(q.is_camera_hardware_validated(20031, "2.0.2.2"))
        self.assertFalse(q.is_camera_hardware_validated(20030, None))
        self.assertFalse(q.is_camera_hardware_validated(True, "2.0.2.2"))

        self.assertTrue(q.KOBRA_X.discovery_hardware_validated)
        self.assertTrue(q.is_discovery_hardware_validated(20030, "2.0.2.2"))
        self.assertFalse(q.is_discovery_hardware_validated(20030, "2.0.2.3"))
        self.assertFalse(q.is_discovery_hardware_validated(20031, "2.0.2.2"))
        self.assertFalse(q.is_discovery_hardware_validated(20030, None))
        self.assertFalse(q.is_discovery_hardware_validated(True, "2.0.2.2"))

        default_profile = q.PrinterQualification(
            model_id=99999,
            model_name="Synthetic",
            short_name="Synthetic",
            firmware_versions=frozenset({"1.0.0"}),
            slicer_name="Slicer",
            gcode_model_marker=b"; printer_model = Synthetic",
            onboard_box=q.KOBRA_X.onboard_box,
            start_evidence=(),
            control_hardware_validated=False,
            delete_hardware_validated=False,
        )
        self.assertFalse(default_profile.camera_hardware_validated)
        self.assertFalse(default_profile.discovery_hardware_validated)


if __name__ == "__main__":
    unittest.main()
