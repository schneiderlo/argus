from __future__ import annotations

import unittest

from argus.models import NodeLifecycleStatus
from argus.observe import _annotate_nodes_with_termination_reason, _node_termination_reason


class ObserverTerminationReasonTests(unittest.TestCase):
    def test_rejected_node_prefers_novelty_summary(self) -> None:
        reason = _node_termination_reason(
            {
                "lifecycle_status": NodeLifecycleStatus.REJECTED.value,
                "metadata": {
                    "novelty": {
                        "summary": "Near-duplicate of node-0001 with matching mechanism and rollout.",
                    }
                },
            }
        )
        self.assertEqual(
            reason,
            (
                "Rejected by novelty gate: Near-duplicate of node-0001 "
                "with matching mechanism and rollout."
            ),
        )

    def test_rejected_node_falls_back_to_similarity_details(self) -> None:
        reason = _node_termination_reason(
            {
                "lifecycle_status": NodeLifecycleStatus.REJECTED.value,
                "metadata": {
                    "novelty": {
                        "nearest_neighbor_id": "node-0001",
                        "max_similarity": 0.95,
                    }
                },
            }
        )
        self.assertEqual(
            reason,
            "Rejected by novelty gate due to near-duplicate overlap with node-0001 (similarity 0.95).",
        )

    def test_failed_node_uses_hard_constraint_reasons(self) -> None:
        reason = _node_termination_reason(
            {
                "lifecycle_status": NodeLifecycleStatus.FAILED.value,
                "score": {
                    "hard_constraint_reasons": [
                        "Exceeds memory envelope.",
                        "Cannot meet latency bound.",
                    ]
                },
            }
        )
        self.assertEqual(
            reason,
            "Failed hard constraints: Exceeds memory envelope.; Cannot meet latency bound.",
        )

    def test_pruned_node_has_manual_reason(self) -> None:
        reason = _node_termination_reason(
            {"lifecycle_status": NodeLifecycleStatus.PRUNED.value}
        )
        self.assertEqual(reason, "Terminated manually by operator.")

    def test_annotation_adds_reason_for_terminal_nodes_only(self) -> None:
        payload = {
            "node-0001": {
                "lifecycle_status": NodeLifecycleStatus.ADMITTED.value,
                "metadata": {},
            },
            "node-0002": {
                "lifecycle_status": NodeLifecycleStatus.REJECTED.value,
                "metadata": {
                    "novelty": {"summary": "Near-duplicate of node-0001."},
                },
            },
        }
        annotated = _annotate_nodes_with_termination_reason(payload)
        self.assertIsInstance(annotated, dict)
        self.assertNotIn("termination_reason", annotated["node-0001"])
        self.assertEqual(
            annotated["node-0002"]["termination_reason"],
            "Rejected by novelty gate: Near-duplicate of node-0001.",
        )


if __name__ == "__main__":
    unittest.main()
