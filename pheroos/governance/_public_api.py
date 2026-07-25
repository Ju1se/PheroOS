"""Generated static declarations for the Governance public facade.

Regenerate with ``scripts/generate_governance_public_api.py --write``.
"""

from types import MappingProxyType


PUBLIC_API_ORDER_SHA256 = (
    "607d19b60814e1486080a405460163a94752caa384974625f06738f480b4a85e"
)
PUBLIC_API = MappingProxyType(
    {
        "AUTHORITY_LEDGER_VERSION": (
            "pheroos.governance.authority_domain",
            "AUTHORITY_LEDGER_VERSION",
        ),
        "ActionPermission": ("pheroos.governance.permission", "ActionPermission"),
        "AuthorityDomain": ("pheroos.governance.authority_domain", "AuthorityDomain"),
        "AuthorityScope": ("pheroos.governance.commit_state", "AuthorityScope"),
        "AuthorityLevel": ("pheroos.governance.authority", "AuthorityLevel"),
        "Candidate": ("pheroos.governance.candidate", "Candidate"),
        "CandidateSet": ("pheroos.governance.candidate", "CandidateSet"),
        "CanonicalTarget": ("pheroos.governance.target", "CanonicalTarget"),
        "CollectiveDecisionState": (
            "pheroos.governance.collective",
            "CollectiveDecisionState",
        ),
        "CollectiveDecisionStep": (
            "pheroos.governance.collective",
            "CollectiveDecisionStep",
        ),
        "GovernanceCommitBatch": (
            "pheroos.governance.authority_domain",
            "GovernanceCommitBatch",
        ),
        "GovernanceCommitReceipt": (
            "pheroos.governance.authority_domain",
            "GovernanceCommitReceipt",
        ),
        "GovernanceHead": ("pheroos.governance.authority_domain", "GovernanceHead"),
        "GovernanceStateStore": (
            "pheroos.governance.authority_domain",
            "GovernanceStateStore",
        ),
        "InMemoryGovernanceStateStore": (
            "pheroos.governance._authority.ledger",
            "InMemoryGovernanceStateStore",
        ),
        "COMMIT_CANONICAL_VERSION": (
            "pheroos.governance.commit_numeric",
            "COMMIT_CANONICAL_VERSION",
        ),
        "COMMIT_WIRE_VERSION": (
            "pheroos.governance.commit_numeric",
            "COMMIT_WIRE_VERSION",
        ),
        "CommitAssurance": ("pheroos.governance.commit_state", "CommitAssurance"),
        "CommitReplayState": ("pheroos.governance.commit_state", "CommitReplayState"),
        "CommitWindowState": ("pheroos.governance.commit_state", "CommitWindowState"),
        "CommitAction": ("pheroos.governance.stop_signal", "CommitAction"),
        "DecisionOutcome": ("pheroos.governance.commit_state", "DecisionOutcome"),
        "DecisionOutcomeKind": (
            "pheroos.governance.commit_state",
            "DecisionOutcomeKind",
        ),
        "DecisionPhase": ("pheroos.governance.commit_state", "DecisionPhase"),
        "DecisionProgress": ("pheroos.governance.commit_state", "DecisionProgress"),
        "ReplayNamespace": ("pheroos.governance.commit_state_v2", "ReplayNamespace"),
        "ReplayReceipt": ("pheroos.governance.commit_state", "ReplayReceipt"),
        "EvidenceEdge": ("pheroos.governance.evidence", "EvidenceEdge"),
        "EvidenceGraph": ("pheroos.governance.evidence", "EvidenceGraph"),
        "EvidenceNode": ("pheroos.governance.evidence", "EvidenceNode"),
        "HybridCollectiveStep": (
            "pheroos.governance.collective",
            "HybridCollectiveStep",
        ),
        "HybridReplayState": ("pheroos.governance.collective", "HybridReplayState"),
        "InhibitionSignal": ("pheroos.governance.collective", "InhibitionSignal"),
        "LayerCoordinationPolicy": (
            "pheroos.governance.layer_coordination",
            "LayerCoordinationPolicy",
        ),
        "LayerCoordinationState": (
            "pheroos.governance.layer_coordination",
            "LayerCoordinationState",
        ),
        "LayerPerformanceSnapshot": (
            "pheroos.governance.layer_coordination",
            "LayerPerformanceSnapshot",
        ),
        "LayerProposal": ("pheroos.governance.layer_coordination", "LayerProposal"),
        "MAX_AUTHORITY_INTEGER": (
            "pheroos.governance.commit_numeric",
            "MAX_AUTHORITY_INTEGER",
        ),
        "OutputAuthorizationResult": (
            "pheroos.governance.output",
            "OutputAuthorizationResult",
        ),
        "OutputContract": ("pheroos.governance.output", "OutputContract"),
        "PHEROMONE_EXTENSION_PREFIXES": (
            "pheroos.governance.pheromone",
            "PHEROMONE_EXTENSION_PREFIXES",
        ),
        "PHEROMONE_KIND_PROFILE_MAP_VERSION": (
            "pheroos.governance.pheromone",
            "PHEROMONE_KIND_PROFILE_MAP_VERSION",
        ),
        "PheromoneBatchResult": (
            "pheroos.governance.pheromone",
            "PheromoneBatchResult",
        ),
        "PheromoneBudgetState": (
            "pheroos.governance.pheromone",
            "PheromoneBudgetState",
        ),
        "PheromoneDiffusionPolicy": (
            "pheroos.governance.pheromone",
            "PheromoneDiffusionPolicy",
        ),
        "PheromoneEdge": ("pheroos.governance.pheromone", "PheromoneEdge"),
        "PheromoneExplorationObservation": (
            "pheroos.governance.pheromone",
            "PheromoneExplorationObservation",
        ),
        "PheromoneFeedback": (
            "pheroos.governance.pheromone_feedback",
            "PheromoneFeedback",
        ),
        "PheromoneKindProfile": ("pheroos.protocol.models", "PheromoneKindProfile"),
        "PreparedGovernanceTransition": (
            "pheroos.governance.authority_domain",
            "PreparedGovernanceTransition",
        ),
        "PheromoneLifecycleRecord": (
            "pheroos.governance.pheromone",
            "PheromoneLifecycleRecord",
        ),
        "PheromoneNeighborhood": (
            "pheroos.governance.pheromone",
            "PheromoneNeighborhood",
        ),
        "PheromoneNormalizationRecord": (
            "pheroos.governance.pheromone",
            "PheromoneNormalizationRecord",
        ),
        "PheromonePolicy": ("pheroos.governance.pheromone", "PheromonePolicy"),
        "PheromoneReinforcementResult": (
            "pheroos.governance.pheromone_feedback",
            "PheromoneReinforcementResult",
        ),
        "PheromoneScoreResult": (
            "pheroos.governance.pheromone",
            "PheromoneScoreResult",
        ),
        "PheromoneSubject": ("pheroos.governance.pheromone", "PheromoneSubject"),
        "PheromoneTrail": ("pheroos.governance.pheromone", "PheromoneTrail"),
        "PolicyAdjustmentBatchResult": (
            "pheroos.governance.policy_adjustment",
            "PolicyAdjustmentBatchResult",
        ),
        "PolicyAdjustmentProposal": (
            "pheroos.governance.policy_adjustment",
            "PolicyAdjustmentProposal",
        ),
        "PrincipalAttestation": (
            "pheroos.governance.principal",
            "PrincipalAttestation",
        ),
        "PrincipalVerification": (
            "pheroos.governance.principal",
            "PrincipalVerification",
        ),
        "QuorumDecision": ("pheroos.governance.quorum", "QuorumDecision"),
        "QuorumSignal": ("pheroos.governance.quorum", "QuorumSignal"),
        "RecruitmentSignal": ("pheroos.governance.collective", "RecruitmentSignal"),
        "RecoveryTrace": ("pheroos.governance.recovery", "RecoveryTrace"),
        "RunScopedPolicyOverlay": (
            "pheroos.governance.policy_adjustment",
            "RunScopedPolicyOverlay",
        ),
        "SUPPORTED_PHEROMONE_KINDS": (
            "pheroos.governance.pheromone",
            "SUPPORTED_PHEROMONE_KINDS",
        ),
        "SUPPORTED_PHEROMONE_SUBJECT_TYPES": (
            "pheroos.governance.pheromone",
            "SUPPORTED_PHEROMONE_SUBJECT_TYPES",
        ),
        "ScoutReport": ("pheroos.governance.collective", "ScoutReport"),
        "Signal": ("pheroos.governance.signal", "Signal"),
        "SignalStatus": ("pheroos.governance.signal", "SignalStatus"),
        "SignalVerification": ("pheroos.governance.signal", "SignalVerification"),
        "StopResolution": ("pheroos.governance.stop_signal", "StopResolution"),
        "StopResolutionVerification": (
            "pheroos.governance.stop_signal",
            "StopResolutionVerification",
        ),
        "StopSignal": ("pheroos.governance.stop_signal", "StopSignal"),
        "StrategyBias": ("pheroos.governance.layer_coordination", "StrategyBias"),
        "TraceEvent": ("pheroos.governance.trace", "TraceEvent"),
        "WEIGHT_SCALE": ("pheroos.governance.commit_numeric", "WEIGHT_SCALE"),
        "allocate_layer_weights": (
            "pheroos.governance.layer_coordination",
            "allocate_layer_weights",
        ),
        "advance_commit_window_state": (
            "pheroos.governance.commit_state",
            "advance_commit_window_state",
        ),
        "action_permission_is_authoritative": (
            "pheroos.governance.permission",
            "action_permission_is_authoritative",
        ),
        "action_permission_fingerprint": (
            "pheroos.governance.permission",
            "action_permission_fingerprint",
        ),
        "action_permission_matches": (
            "pheroos.governance.permission",
            "action_permission_matches",
        ),
        "action_permission_payload": (
            "pheroos.governance.permission",
            "action_permission_payload",
        ),
        "apply_policy_adjustment_overlay": (
            "pheroos.governance.policy_adjustment",
            "apply_policy_adjustment_overlay",
        ),
        "can_verify": ("pheroos.governance.authority", "can_verify"),
        "canonical_pheromone_kind_profiles": (
            "pheroos.governance.pheromone",
            "canonical_pheromone_kind_profiles",
        ),
        "canonical_commit_payload": (
            "pheroos.governance.commit_numeric",
            "canonical_commit_payload",
        ),
        "canonical_commit_set": (
            "pheroos.governance.commit_numeric",
            "canonical_commit_set",
        ),
        "checked_add": ("pheroos.governance.commit_numeric", "checked_add"),
        "checked_multiply": ("pheroos.governance.commit_numeric", "checked_multiply"),
        "checked_subtract": ("pheroos.governance.commit_numeric", "checked_subtract"),
        "candidate_score_lineage": (
            "pheroos.governance.collective",
            "candidate_score_lineage",
        ),
        "clip_pheromone_deposit_strength": (
            "pheroos.governance.pheromone",
            "clip_pheromone_deposit_strength",
        ),
        "clip_pheromone_strength": (
            "pheroos.governance.pheromone",
            "clip_pheromone_strength",
        ),
        "ceil_scaled_count": ("pheroos.governance.commit_numeric", "ceil_scaled_count"),
        "collect_pheromone_source_diversity": (
            "pheroos.governance.pheromone",
            "collect_pheromone_source_diversity",
        ),
        "commit_candidate": ("pheroos.governance.quorum", "commit_candidate"),
        "commit_schema": ("pheroos.governance.schema", "commit_schema"),
        "commit_replay_state_fingerprint": (
            "pheroos.governance.commit_state",
            "commit_replay_state_fingerprint",
        ),
        "commit_replay_state_contains": (
            "pheroos.governance.commit_state",
            "commit_replay_state_contains",
        ),
        "commit_replay_state_is_authoritative": (
            "pheroos.governance.commit_state",
            "commit_replay_state_is_authoritative",
        ),
        "commit_replay_state_is_current": (
            "pheroos.governance.commit_state",
            "commit_replay_state_is_current",
        ),
        "commit_replay_state_matches": (
            "pheroos.governance.commit_state",
            "commit_replay_state_matches",
        ),
        "commit_replay_state_payload": (
            "pheroos.governance.commit_state",
            "commit_replay_state_payload",
        ),
        "commit_window_ready": (
            "pheroos.governance.commit_state",
            "commit_window_ready",
        ),
        "commit_window_state_fingerprint": (
            "pheroos.governance.commit_state",
            "commit_window_state_fingerprint",
        ),
        "commit_window_state_is_authoritative": (
            "pheroos.governance.commit_state",
            "commit_window_state_is_authoritative",
        ),
        "commit_window_state_payload": (
            "pheroos.governance.commit_state",
            "commit_window_state_payload",
        ),
        "commit_payload_fingerprint": (
            "pheroos.governance.commit_numeric",
            "commit_payload_fingerprint",
        ),
        "deposit_pheromone": ("pheroos.governance.pheromone", "deposit_pheromone"),
        "deposit_pheromone_trails": (
            "pheroos.governance.pheromone",
            "deposit_pheromone_trails",
        ),
        "diffuse_pheromone_trails": (
            "pheroos.governance.pheromone",
            "diffuse_pheromone_trails",
        ),
        "diffuse_pheromone_trails_with_records": (
            "pheroos.governance.pheromone",
            "diffuse_pheromone_trails_with_records",
        ),
        "diffusion_policy_from_collective": (
            "pheroos.governance.pheromone",
            "diffusion_policy_from_collective",
        ),
        "evaluate_collective_decision": (
            "pheroos.governance.collective",
            "evaluate_collective_decision",
        ),
        "evaluate_collective_decision_step": (
            "pheroos.governance.collective",
            "evaluate_collective_decision_step",
        ),
        "evaluate_hybrid_collective_step": (
            "pheroos.governance.collective",
            "evaluate_hybrid_collective_step",
        ),
        "hybrid_collective_step_is_authoritative": (
            "pheroos.governance.collective",
            "hybrid_collective_step_is_authoritative",
        ),
        "hybrid_replay_state_is_authoritative": (
            "pheroos.governance.collective",
            "hybrid_replay_state_is_authoritative",
        ),
        "evaluate_layer_coordination": (
            "pheroos.governance.layer_coordination",
            "evaluate_layer_coordination",
        ),
        "evaluate_output_authorization": (
            "pheroos.governance.output",
            "evaluate_output_authorization",
        ),
        "evaluate_quorum_decision": (
            "pheroos.governance.quorum",
            "evaluate_quorum_decision",
        ),
        "evaporate_trails": ("pheroos.governance.pheromone", "evaporate_trails"),
        "evaporate_trails_with_records": (
            "pheroos.governance.pheromone",
            "evaporate_trails_with_records",
        ),
        "is_extension_pheromone_value": (
            "pheroos.governance.pheromone",
            "is_extension_pheromone_value",
        ),
        "issue_action_permission": (
            "pheroos.governance.permission",
            "issue_action_permission",
        ),
        "initialize_commit_replay_state": (
            "pheroos.governance.commit_state",
            "initialize_commit_replay_state",
        ),
        "initialize_commit_window_state": (
            "pheroos.governance.commit_state",
            "initialize_commit_window_state",
        ),
        "layer_coordination_policy_from_collective": (
            "pheroos.governance.layer_coordination",
            "layer_coordination_policy_from_collective",
        ),
        "layer_action_effect": (
            "pheroos.governance.layer_coordination",
            "layer_action_effect",
        ),
        "materialize_layer_pheromone_proposals": (
            "pheroos.governance.layer_coordination",
            "materialize_layer_pheromone_proposals",
        ),
        "multiply_scaled": ("pheroos.governance.commit_numeric", "multiply_scaled"),
        "require_authority_integer": (
            "pheroos.governance.commit_numeric",
            "require_authority_integer",
        ),
        "proposal_score_delta": (
            "pheroos.governance.layer_coordination",
            "proposal_score_delta",
        ),
        "principal_attestation_fingerprint": (
            "pheroos.governance.principal",
            "principal_attestation_fingerprint",
        ),
        "principal_attestation_payload": (
            "pheroos.governance.principal",
            "principal_attestation_payload",
        ),
        "principal_verification_fingerprint": (
            "pheroos.governance.principal",
            "principal_verification_fingerprint",
        ),
        "principal_verification_is_authoritative": (
            "pheroos.governance.principal",
            "principal_verification_is_authoritative",
        ),
        "principal_verification_matches": (
            "pheroos.governance.principal",
            "principal_verification_matches",
        ),
        "principal_verification_payload": (
            "pheroos.governance.principal",
            "principal_verification_payload",
        ),
        "normalize_legacy_pheromone_trail": (
            "pheroos.governance.pheromone",
            "normalize_legacy_pheromone_trail",
        ),
        "observe_pheromone_exploration": (
            "pheroos.governance.pheromone",
            "observe_pheromone_exploration",
        ),
        "output_authorized": ("pheroos.governance.output", "output_authorized"),
        "output_gate_lineage": ("pheroos.governance.output", "output_gate_lineage"),
        "pheromone_lineage": ("pheroos.governance.pheromone", "pheromone_lineage"),
        "pheromone_policy_from_collective": (
            "pheroos.governance.pheromone",
            "pheromone_policy_from_collective",
        ),
        "pheromone_subject_id": (
            "pheroos.governance.pheromone",
            "pheromone_subject_id",
        ),
        "pheromone_subject_type": (
            "pheroos.governance.pheromone",
            "pheromone_subject_type",
        ),
        "reinforce_pheromone_trails": (
            "pheroos.governance.pheromone_feedback",
            "reinforce_pheromone_trails",
        ),
        "reinforce_pheromone_trails_with_records": (
            "pheroos.governance.pheromone_feedback",
            "reinforce_pheromone_trails_with_records",
        ),
        "resolve_stop_signal": (
            "pheroos.governance.stop_signal",
            "resolve_stop_signal",
        ),
        "record_commit_replay_receipts": (
            "pheroos.governance.commit_state",
            "record_commit_replay_receipts",
        ),
        "replay_receipt_fingerprint": (
            "pheroos.governance.commit_state",
            "replay_receipt_fingerprint",
        ),
        "replay_receipt_payload": (
            "pheroos.governance.commit_state",
            "replay_receipt_payload",
        ),
        "restart_commit_window_epoch": (
            "pheroos.governance.commit_state",
            "restart_commit_window_epoch",
        ),
        "replay_state_from_hybrid_step": (
            "pheroos.governance.collective",
            "replay_state_from_hybrid_step",
        ),
        "require_scaled_integer": (
            "pheroos.governance.commit_numeric",
            "require_scaled_integer",
        ),
        "score_candidates": ("pheroos.governance.collective", "score_candidates"),
        "score_pheromone_trails": (
            "pheroos.governance.pheromone",
            "score_pheromone_trails",
        ),
        "score_pheromone_trails_result": (
            "pheroos.governance.pheromone",
            "score_pheromone_trails_result",
        ),
        "score_pheromone_trails_with_breakdown": (
            "pheroos.governance.pheromone",
            "score_pheromone_trails_with_breakdown",
        ),
        "select_terminal_outcome_kind": (
            "pheroos.governance.commit_semantics",
            "select_terminal_outcome_kind",
        ),
        "scaled_ratio": ("pheroos.governance.commit_numeric", "scaled_ratio"),
        "strategy_bias_score_delta": (
            "pheroos.governance.layer_coordination",
            "strategy_bias_score_delta",
        ),
        "stop_resolution_verification_is_authoritative": (
            "pheroos.governance.stop_signal",
            "stop_resolution_verification_is_authoritative",
        ),
        "stop_resolution_verification_fingerprint": (
            "pheroos.governance.stop_signal",
            "stop_resolution_verification_fingerprint",
        ),
        "stop_resolution_verification_matches": (
            "pheroos.governance.stop_signal",
            "stop_resolution_verification_matches",
        ),
        "stop_resolution_verification_payload": (
            "pheroos.governance.stop_signal",
            "stop_resolution_verification_payload",
        ),
        "validate_layer_coordination_policy": (
            "pheroos.governance.layer_coordination",
            "validate_layer_coordination_policy",
        ),
        "validate_commit_wire_record": (
            "pheroos.governance.schema",
            "validate_commit_wire_record",
        ),
        "validate_layer_performance_snapshot": (
            "pheroos.governance.layer_coordination",
            "validate_layer_performance_snapshot",
        ),
        "validate_layer_proposal": (
            "pheroos.governance.layer_coordination",
            "validate_layer_proposal",
        ),
        "validate_pheromone_budget_state": (
            "pheroos.governance.pheromone",
            "validate_pheromone_budget_state",
        ),
        "validate_pheromone_feedback": (
            "pheroos.governance.pheromone_feedback",
            "validate_pheromone_feedback",
        ),
        "validate_pheromone_policy": (
            "pheroos.governance.pheromone",
            "validate_pheromone_policy",
        ),
        "validate_pheromone_topology": (
            "pheroos.governance.pheromone",
            "validate_pheromone_topology",
        ),
        "validate_pheromone_trail": (
            "pheroos.governance.pheromone",
            "validate_pheromone_trail",
        ),
        "validate_policy_adjustment_proposal": (
            "pheroos.governance.policy_adjustment",
            "validate_policy_adjustment_proposal",
        ),
        "validate_policy_adjustment_proposals": (
            "pheroos.governance.policy_adjustment",
            "validate_policy_adjustment_proposals",
        ),
        "validate_score_breakdown": (
            "pheroos.governance.collective",
            "validate_score_breakdown",
        ),
        "validate_strategy_bias": (
            "pheroos.governance.layer_coordination",
            "validate_strategy_bias",
        ),
        "decision_outcome_is_authoritative": (
            "pheroos.governance.commit_state",
            "decision_outcome_is_authoritative",
        ),
        "decision_outcome_fingerprint": (
            "pheroos.governance.commit_state",
            "decision_outcome_fingerprint",
        ),
        "decision_outcome_payload": (
            "pheroos.governance.commit_state",
            "decision_outcome_payload",
        ),
        "decision_progress_is_authoritative": (
            "pheroos.governance.commit_state",
            "decision_progress_is_authoritative",
        ),
        "decision_progress_fingerprint": (
            "pheroos.governance.commit_state",
            "decision_progress_fingerprint",
        ),
        "decision_progress_payload": (
            "pheroos.governance.commit_state",
            "decision_progress_payload",
        ),
        "verify_principal_attestation": (
            "pheroos.governance.principal",
            "verify_principal_attestation",
        ),
        "verify_signal_input": ("pheroos.governance.signal", "verify_signal_input"),
        "verify_stop_resolution": (
            "pheroos.governance.stop_signal",
            "verify_stop_resolution",
        ),
        "ChallengeAttestation": (
            "pheroos.governance.challenge",
            "ChallengeAttestation",
        ),
        "ChallengeCoverage": ("pheroos.governance.challenge", "ChallengeCoverage"),
        "ChallengeResult": ("pheroos.governance.challenge", "ChallengeResult"),
        "CommitThresholdSnapshot": (
            "pheroos.governance.risk",
            "CommitThresholdSnapshot",
        ),
        "CounterevidenceDisposition": (
            "pheroos.governance.observation",
            "CounterevidenceDisposition",
        ),
        "CounterevidenceDispositionKind": (
            "pheroos.governance.observation",
            "CounterevidenceDispositionKind",
        ),
        "EVIDENCE_BINDING_VERSION": (
            "pheroos.governance.evidence_binding",
            "EVIDENCE_BINDING_VERSION",
        ),
        "EligiblePrincipal": ("pheroos.governance.support_lease", "EligiblePrincipal"),
        "EligiblePrincipalCluster": (
            "pheroos.governance.support_lease",
            "EligiblePrincipalCluster",
        ),
        "EligiblePrincipalSnapshot": (
            "pheroos.governance.support_lease",
            "EligiblePrincipalSnapshot",
        ),
        "EvidenceBinding": ("pheroos.governance.evidence_binding", "EvidenceBinding"),
        "EvidenceGroupContribution": (
            "pheroos.governance.evidence_binding",
            "EvidenceGroupContribution",
        ),
        "EvidenceSummary": ("pheroos.governance.evidence_binding", "EvidenceSummary"),
        "ObservationAttestation": (
            "pheroos.governance.observation",
            "ObservationAttestation",
        ),
        "ObservationPolarity": (
            "pheroos.governance.observation",
            "ObservationPolarity",
        ),
        "RiskAssessment": ("pheroos.governance.risk", "RiskAssessment"),
        "RiskBand": ("pheroos.governance.risk_v2", "RiskBand"),
        "SourceDomainContribution": (
            "pheroos.governance.evidence_binding",
            "SourceDomainContribution",
        ),
        "SupportEquivocationFinding": (
            "pheroos.governance.support_lease",
            "SupportEquivocationFinding",
        ),
        "SupportLease": ("pheroos.governance.support_lease", "SupportLease"),
        "SupportLeaseEvaluation": (
            "pheroos.governance.support_lease",
            "SupportLeaseEvaluation",
        ),
        "SupportLeaseExpiration": (
            "pheroos.governance.support_lease",
            "SupportLeaseExpiration",
        ),
        "SupportLeaseProposal": (
            "pheroos.governance.support_lease",
            "SupportLeaseProposal",
        ),
        "SupportLeaseRevocation": (
            "pheroos.governance.support_lease",
            "SupportLeaseRevocation",
        ),
        "SupportLeaseStatus": (
            "pheroos.governance.support_lease",
            "SupportLeaseStatus",
        ),
        "SupportLeaseSwitch": (
            "pheroos.governance.support_lease",
            "SupportLeaseSwitch",
        ),
        "VerifiedChallenge": ("pheroos.governance.challenge", "VerifiedChallenge"),
        "VerifiedObservation": (
            "pheroos.governance.observation",
            "VerifiedObservation",
        ),
        "bind_evidence": ("pheroos.governance.evidence_binding", "bind_evidence"),
        "challenge_attestation_fingerprint": (
            "pheroos.governance.challenge",
            "challenge_attestation_fingerprint",
        ),
        "challenge_attestation_payload": (
            "pheroos.governance.challenge",
            "challenge_attestation_payload",
        ),
        "challenge_coverage_fingerprint": (
            "pheroos.governance.challenge",
            "challenge_coverage_fingerprint",
        ),
        "challenge_coverage_payload": (
            "pheroos.governance.challenge",
            "challenge_coverage_payload",
        ),
        "commit_threshold_snapshot_fingerprint": (
            "pheroos.governance.risk",
            "commit_threshold_snapshot_fingerprint",
        ),
        "commit_threshold_snapshot_is_authoritative": (
            "pheroos.governance.risk",
            "commit_threshold_snapshot_is_authoritative",
        ),
        "commit_threshold_snapshot_matches": (
            "pheroos.governance.risk",
            "commit_threshold_snapshot_matches",
        ),
        "commit_threshold_snapshot_payload": (
            "pheroos.governance.risk",
            "commit_threshold_snapshot_payload",
        ),
        "commit_threshold_transition_requires_reset": (
            "pheroos.governance.risk",
            "commit_threshold_transition_requires_reset",
        ),
        "counterevidence_disposition_fingerprint": (
            "pheroos.governance.observation",
            "counterevidence_disposition_fingerprint",
        ),
        "counterevidence_disposition_is_authoritative": (
            "pheroos.governance.observation",
            "counterevidence_disposition_is_authoritative",
        ),
        "counterevidence_disposition_matches": (
            "pheroos.governance.observation",
            "counterevidence_disposition_matches",
        ),
        "counterevidence_disposition_payload": (
            "pheroos.governance.observation",
            "counterevidence_disposition_payload",
        ),
        "counterevidence_is_material_critical": (
            "pheroos.governance.observation",
            "counterevidence_is_material_critical",
        ),
        "eligible_principal_snapshot_fingerprint": (
            "pheroos.governance.support_lease",
            "eligible_principal_snapshot_fingerprint",
        ),
        "eligible_principal_snapshot_is_authoritative": (
            "pheroos.governance.support_lease",
            "eligible_principal_snapshot_is_authoritative",
        ),
        "eligible_principal_snapshot_matches": (
            "pheroos.governance.support_lease",
            "eligible_principal_snapshot_matches",
        ),
        "eligible_principal_snapshot_payload": (
            "pheroos.governance.support_lease",
            "eligible_principal_snapshot_payload",
        ),
        "evidence_binding_fingerprint": (
            "pheroos.governance.evidence_binding",
            "evidence_binding_fingerprint",
        ),
        "evidence_binding_is_authoritative": (
            "pheroos.governance.evidence_binding",
            "evidence_binding_is_authoritative",
        ),
        "evidence_binding_matches": (
            "pheroos.governance.evidence_binding",
            "evidence_binding_matches",
        ),
        "evidence_binding_payload": (
            "pheroos.governance.evidence_binding",
            "evidence_binding_payload",
        ),
        "evidence_summary_fingerprint": (
            "pheroos.governance.evidence_binding",
            "evidence_summary_fingerprint",
        ),
        "evidence_summary_payload": (
            "pheroos.governance.evidence_binding",
            "evidence_summary_payload",
        ),
        "evaluate_challenge_coverage": (
            "pheroos.governance.challenge",
            "evaluate_challenge_coverage",
        ),
        "evaluate_evidence_binding": (
            "pheroos.governance.evidence_binding",
            "evaluate_evidence_binding",
        ),
        "evaluate_support_leases": (
            "pheroos.governance.support_lease",
            "evaluate_support_leases",
        ),
        "expire_support_lease": (
            "pheroos.governance.support_lease",
            "expire_support_lease",
        ),
        "issue_commit_threshold_snapshot": (
            "pheroos.governance.risk",
            "issue_commit_threshold_snapshot",
        ),
        "issue_counterevidence_disposition": (
            "pheroos.governance.observation",
            "issue_counterevidence_disposition",
        ),
        "issue_eligible_principal_snapshot": (
            "pheroos.governance.support_lease",
            "issue_eligible_principal_snapshot",
        ),
        "issue_risk_assessment": ("pheroos.governance.risk", "issue_risk_assessment"),
        "issue_support_lease": (
            "pheroos.governance.support_lease",
            "issue_support_lease",
        ),
        "observation_attestation_fingerprint": (
            "pheroos.governance.observation",
            "observation_attestation_fingerprint",
        ),
        "observation_attestation_payload": (
            "pheroos.governance.observation",
            "observation_attestation_payload",
        ),
        "observation_weight_ppm": (
            "pheroos.governance.observation",
            "observation_weight_ppm",
        ),
        "rebuild_evidence_binding_roots": (
            "pheroos.governance.evidence_binding",
            "rebuild_evidence_binding_roots",
        ),
        "revoke_support_lease": (
            "pheroos.governance.support_lease",
            "revoke_support_lease",
        ),
        "risk_assessment_fingerprint": (
            "pheroos.governance.risk",
            "risk_assessment_fingerprint",
        ),
        "risk_assessment_is_authoritative": (
            "pheroos.governance.risk",
            "risk_assessment_is_authoritative",
        ),
        "risk_assessment_matches": (
            "pheroos.governance.risk",
            "risk_assessment_matches",
        ),
        "risk_assessment_payload": (
            "pheroos.governance.risk",
            "risk_assessment_payload",
        ),
        "risk_policy_root": ("pheroos.governance.risk", "risk_policy_root"),
        "risk_transition_is_monotonic": (
            "pheroos.governance.risk",
            "risk_transition_is_monotonic",
        ),
        "support_lease_fingerprint": (
            "pheroos.governance.support_lease",
            "support_lease_fingerprint",
        ),
        "support_lease_is_authoritative": (
            "pheroos.governance.support_lease",
            "support_lease_is_authoritative",
        ),
        "support_lease_payload": (
            "pheroos.governance.support_lease",
            "support_lease_payload",
        ),
        "support_lease_proposal_fingerprint": (
            "pheroos.governance.support_lease",
            "support_lease_proposal_fingerprint",
        ),
        "support_lease_proposal_payload": (
            "pheroos.governance.support_lease",
            "support_lease_proposal_payload",
        ),
        "support_lease_revocation_fingerprint": (
            "pheroos.governance.support_lease",
            "support_lease_revocation_fingerprint",
        ),
        "support_lease_revocation_is_authoritative": (
            "pheroos.governance.support_lease",
            "support_lease_revocation_is_authoritative",
        ),
        "support_lease_revocation_matches": (
            "pheroos.governance.support_lease",
            "support_lease_revocation_matches",
        ),
        "support_lease_revocation_payload": (
            "pheroos.governance.support_lease",
            "support_lease_revocation_payload",
        ),
        "support_lease_status": (
            "pheroos.governance.support_lease",
            "support_lease_status",
        ),
        "switch_support_lease": (
            "pheroos.governance.support_lease",
            "switch_support_lease",
        ),
        "verified_challenge_fingerprint": (
            "pheroos.governance.challenge",
            "verified_challenge_fingerprint",
        ),
        "verified_challenge_is_authoritative": (
            "pheroos.governance.challenge",
            "verified_challenge_is_authoritative",
        ),
        "verified_challenge_matches": (
            "pheroos.governance.challenge",
            "verified_challenge_matches",
        ),
        "verified_challenge_payload": (
            "pheroos.governance.challenge",
            "verified_challenge_payload",
        ),
        "verified_observation_fingerprint": (
            "pheroos.governance.observation",
            "verified_observation_fingerprint",
        ),
        "verified_observation_is_authoritative": (
            "pheroos.governance.observation",
            "verified_observation_is_authoritative",
        ),
        "verified_observation_matches": (
            "pheroos.governance.observation",
            "verified_observation_matches",
        ),
        "verified_observation_payload": (
            "pheroos.governance.observation",
            "verified_observation_payload",
        ),
        "verify_challenge_attestation": (
            "pheroos.governance.challenge",
            "verify_challenge_attestation",
        ),
        "verify_observation_attestation": (
            "pheroos.governance.observation",
            "verify_observation_attestation",
        ),
        "ATTENTION_AUTHORITY_SCOPE": (
            "pheroos.governance.attention",
            "ATTENTION_AUTHORITY_SCOPE",
        ),
        "ATTENTION_CHANNEL": ("pheroos.governance.attention", "ATTENTION_CHANNEL"),
        "CERTIFICATE_HASH_ALGORITHM": (
            "pheroos.governance.certificate",
            "CERTIFICATE_HASH_ALGORITHM",
        ),
        "COMMIT_AUTHORITY_SOURCE": (
            "pheroos.governance.hybrid_commit",
            "COMMIT_AUTHORITY_SOURCE",
        ),
        "EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR": (
            "pheroos.governance.certificate",
            "EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR",
        ),
        "EVIDENCE_COMMIT_CERTIFICATE_VERSION": (
            "pheroos.governance.certificate",
            "EVIDENCE_COMMIT_CERTIFICATE_VERSION",
        ),
        "HYBRID_ATTENTION_PROFILE": (
            "pheroos.governance.attention",
            "HYBRID_ATTENTION_PROFILE",
        ),
        "HYBRID_COMMIT_BINDING_PROFILE": (
            "pheroos.governance.hybrid_commit",
            "HYBRID_COMMIT_BINDING_PROFILE",
        ),
        "HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION": (
            "pheroos.governance.hybrid_commit",
            "HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION",
        ),
        "HYBRID_COMMIT_EVALUATION_REQUEST_VERSION": (
            "pheroos.governance.hybrid_commit",
            "HYBRID_COMMIT_EVALUATION_REQUEST_VERSION",
        ),
        "HYBRID_COMMIT_EVALUATION_VERSION": (
            "pheroos.governance.hybrid_commit",
            "HYBRID_COMMIT_EVALUATION_VERSION",
        ),
        "LOCAL_COMMIT_RECEIPT_DISCRIMINATOR": (
            "pheroos.governance.certificate",
            "LOCAL_COMMIT_RECEIPT_DISCRIMINATOR",
        ),
        "LOCAL_COMMIT_RECEIPT_VERSION": (
            "pheroos.governance.certificate",
            "LOCAL_COMMIT_RECEIPT_VERSION",
        ),
        "OUTCOME_CERTIFICATE_DISCRIMINATOR": (
            "pheroos.governance.certificate",
            "OUTCOME_CERTIFICATE_DISCRIMINATOR",
        ),
        "OUTCOME_CERTIFICATE_VERSION": (
            "pheroos.governance.certificate",
            "OUTCOME_CERTIFICATE_VERSION",
        ),
        "AttentionBreakdown": ("pheroos.governance.attention", "AttentionBreakdown"),
        "AttentionCandidatePriority": (
            "pheroos.governance.attention",
            "AttentionCandidatePriority",
        ),
        "AttentionReopenEligibility": (
            "pheroos.governance.attention",
            "AttentionReopenEligibility",
        ),
        "AttentionSubjectPriority": (
            "pheroos.governance.attention",
            "AttentionSubjectPriority",
        ),
        "CandidateClaimBinding": ("pheroos.governance.commit", "CandidateClaimBinding"),
        "CandidateCommitInput": ("pheroos.governance.commit", "CandidateCommitInput"),
        "CandidateCommitMetrics": (
            "pheroos.governance.commit",
            "CandidateCommitMetrics",
        ),
        "CommitAssessment": ("pheroos.governance.commit", "CommitAssessment"),
        "CommitAssessmentStatus": (
            "pheroos.governance.commit",
            "CommitAssessmentStatus",
        ),
        "CommitEvaluationContext": (
            "pheroos.governance.commit",
            "CommitEvaluationContext",
        ),
        "CommitEvaluationError": ("pheroos.governance.commit", "CommitEvaluationError"),
        "CommitEvaluationFailureKind": (
            "pheroos.governance.commit",
            "CommitEvaluationFailureKind",
        ),
        "CommitFinalityStatus": (
            "pheroos.governance.commit_state",
            "CommitFinalityStatus",
        ),
        "CommitFinalityVerification": (
            "pheroos.governance.commit_state",
            "CommitFinalityVerification",
        ),
        "CommitLivenessInput": (
            "pheroos.governance.commit_state",
            "CommitLivenessInput",
        ),
        "CommitOutputAction": ("pheroos.governance.output", "CommitOutputAction"),
        "CommitOutputAuthorization": (
            "pheroos.governance.output",
            "CommitOutputAuthorization",
        ),
        "CommitReasonCode": ("pheroos.governance.commit", "CommitReasonCode"),
        "CommitWindowSeal": ("pheroos.governance.commit_state", "CommitWindowSeal"),
        "EligibleMembershipEpochState": (
            "pheroos.governance.support_lease",
            "EligibleMembershipEpochState",
        ),
        "EvidenceCommitCertificate": (
            "pheroos.governance.historical_certificate",
            "EvidenceCommitCertificate",
        ),
        "ExplorationDirective": (
            "pheroos.governance.attention",
            "ExplorationDirective",
        ),
        "HybridCommitAttentionStatus": (
            "pheroos.governance.hybrid_commit",
            "HybridCommitAttentionStatus",
        ),
        "HybridCommitDiagnostic": (
            "pheroos.governance.hybrid_commit",
            "HybridCommitDiagnostic",
        ),
        "HybridCommitDiagnosticSeverity": (
            "pheroos.governance.hybrid_commit",
            "HybridCommitDiagnosticSeverity",
        ),
        "HybridCommitEvaluation": (
            "pheroos.governance.hybrid_commit",
            "HybridCommitEvaluation",
        ),
        "HybridCommitEvaluationRequest": (
            "pheroos.governance.hybrid_commit",
            "HybridCommitEvaluationRequest",
        ),
        "HybridCommitEvaluationStatus": (
            "pheroos.governance.hybrid_commit",
            "HybridCommitEvaluationStatus",
        ),
        "HybridCommitStep": ("pheroos.governance.hybrid_commit", "HybridCommitStep"),
        "LocalCommitReceipt": ("pheroos.governance.certificate", "LocalCommitReceipt"),
        "OutcomeCertificate": ("pheroos.governance.certificate", "OutcomeCertificate"),
        "RiskAssessmentChainState": (
            "pheroos.governance.risk",
            "RiskAssessmentChainState",
        ),
        "SupportLeaseReplayReceipt": (
            "pheroos.governance.support_lease",
            "SupportLeaseReplayReceipt",
        ),
        "SupportLeaseReplayState": (
            "pheroos.governance.support_lease",
            "SupportLeaseReplayState",
        ),
        "assess_optimal_commit": ("pheroos.governance.commit", "assess_optimal_commit"),
        "attention_breakdown_fingerprint": (
            "pheroos.governance.attention",
            "attention_breakdown_fingerprint",
        ),
        "attention_breakdown_is_authoritative": (
            "pheroos.governance.attention",
            "attention_breakdown_is_authoritative",
        ),
        "attention_breakdown_payload": (
            "pheroos.governance.attention",
            "attention_breakdown_payload",
        ),
        "authorize_terminal_execution": (
            "pheroos.governance.output",
            "authorize_terminal_execution",
        ),
        "authorize_terminal_publication": (
            "pheroos.governance.output",
            "authorize_terminal_publication",
        ),
        "bind_hybrid_commit_channels": (
            "pheroos.governance.hybrid_commit",
            "bind_hybrid_commit_channels",
        ),
        "build_commit_replay_receipts": (
            "pheroos.governance.commit",
            "build_commit_replay_receipts",
        ),
        "candidate_commit_metrics_fingerprint": (
            "pheroos.governance.commit",
            "candidate_commit_metrics_fingerprint",
        ),
        "candidate_commit_metrics_payload": (
            "pheroos.governance.commit",
            "candidate_commit_metrics_payload",
        ),
        "commit_assessment_fingerprint": (
            "pheroos.governance.commit",
            "commit_assessment_fingerprint",
        ),
        "commit_assessment_is_authoritative": (
            "pheroos.governance.commit",
            "commit_assessment_is_authoritative",
        ),
        "commit_assessment_payload": (
            "pheroos.governance.commit",
            "commit_assessment_payload",
        ),
        "commit_evaluation_context_fingerprint": (
            "pheroos.governance.commit",
            "commit_evaluation_context_fingerprint",
        ),
        "commit_evaluation_context_is_authoritative": (
            "pheroos.governance.commit",
            "commit_evaluation_context_is_authoritative",
        ),
        "commit_evaluation_context_payload": (
            "pheroos.governance.commit",
            "commit_evaluation_context_payload",
        ),
        "commit_finality_verification_fingerprint": (
            "pheroos.governance.commit_state",
            "commit_finality_verification_fingerprint",
        ),
        "commit_finality_verification_is_authoritative": (
            "pheroos.governance.commit_state",
            "commit_finality_verification_is_authoritative",
        ),
        "commit_finality_verification_payload": (
            "pheroos.governance.commit_state",
            "commit_finality_verification_payload",
        ),
        "commit_liveness_input_fingerprint": (
            "pheroos.governance.commit_state",
            "commit_liveness_input_fingerprint",
        ),
        "commit_liveness_input_is_authoritative": (
            "pheroos.governance.commit_state",
            "commit_liveness_input_is_authoritative",
        ),
        "commit_liveness_input_payload": (
            "pheroos.governance.commit_state",
            "commit_liveness_input_payload",
        ),
        "commit_output_authorization_fingerprint": (
            "pheroos.governance.output",
            "commit_output_authorization_fingerprint",
        ),
        "commit_output_authorization_is_authoritative": (
            "pheroos.governance.output",
            "commit_output_authorization_is_authoritative",
        ),
        "commit_output_authorization_payload": (
            "pheroos.governance.output",
            "commit_output_authorization_payload",
        ),
        "commit_window_seal_fingerprint": (
            "pheroos.governance.commit_state",
            "commit_window_seal_fingerprint",
        ),
        "commit_window_seal_for_state": (
            "pheroos.governance.commit_state",
            "commit_window_seal_for_state",
        ),
        "commit_window_seal_is_authoritative": (
            "pheroos.governance.commit_state",
            "commit_window_seal_is_authoritative",
        ),
        "commit_window_seal_is_current": (
            "pheroos.governance.commit_state",
            "commit_window_seal_is_current",
        ),
        "commit_window_seal_matches_receipt": (
            "pheroos.governance.commit_state",
            "commit_window_seal_matches_receipt",
        ),
        "commit_window_seal_payload": (
            "pheroos.governance.commit_state",
            "commit_window_seal_payload",
        ),
        "commit_window_state_is_current": (
            "pheroos.governance.commit_state",
            "commit_window_state_is_current",
        ),
        "deliver_terminal_outcome": (
            "pheroos.governance.output",
            "deliver_terminal_outcome",
        ),
        "derive_attention_breakdown": (
            "pheroos.governance.attention",
            "derive_attention_breakdown",
        ),
        "derive_exploration_directive": (
            "pheroos.governance.attention",
            "derive_exploration_directive",
        ),
        "eligible_membership_epoch_state_fingerprint": (
            "pheroos.governance.support_lease",
            "eligible_membership_epoch_state_fingerprint",
        ),
        "eligible_membership_epoch_state_is_authoritative": (
            "pheroos.governance.support_lease",
            "eligible_membership_epoch_state_is_authoritative",
        ),
        "eligible_membership_epoch_state_is_current": (
            "pheroos.governance.support_lease",
            "eligible_membership_epoch_state_is_current",
        ),
        "eligible_membership_epoch_state_payload": (
            "pheroos.governance.support_lease",
            "eligible_membership_epoch_state_payload",
        ),
        "evidence_commit_certificate_body_root": (
            "pheroos.governance.certificate",
            "evidence_commit_certificate_body_root",
        ),
        "evidence_commit_certificate_fingerprint": (
            "pheroos.governance.historical_certificate",
            "evidence_commit_certificate_fingerprint",
        ),
        "evidence_commit_certificate_from_payload": (
            "pheroos.governance.historical_certificate",
            "evidence_commit_certificate_from_payload",
        ),
        "evidence_commit_certificate_payload": (
            "pheroos.governance.historical_certificate",
            "evidence_commit_certificate_payload",
        ),
        "evaluate_hybrid_attention_step": (
            "pheroos.governance.attention",
            "evaluate_hybrid_attention_step",
        ),
        "evaluate_hybrid_commit_evaluation": (
            "pheroos.governance.hybrid_commit",
            "evaluate_hybrid_commit_evaluation",
        ),
        "evaluate_hybrid_commit_step": (
            "pheroos.governance.hybrid_commit",
            "evaluate_hybrid_commit_step",
        ),
        "exploration_directive_fingerprint": (
            "pheroos.governance.attention",
            "exploration_directive_fingerprint",
        ),
        "exploration_directive_is_authoritative": (
            "pheroos.governance.attention",
            "exploration_directive_is_authoritative",
        ),
        "exploration_directive_payload": (
            "pheroos.governance.attention",
            "exploration_directive_payload",
        ),
        "hybrid_attention_projection": (
            "pheroos.governance.hybrid_commit",
            "hybrid_attention_projection",
        ),
        "hybrid_commit_diagnostic_payload": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_diagnostic_payload",
        ),
        "hybrid_commit_evaluation_fingerprint": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_evaluation_fingerprint",
        ),
        "hybrid_commit_evaluation_is_authoritative": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_evaluation_is_authoritative",
        ),
        "hybrid_commit_evaluation_payload": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_evaluation_payload",
        ),
        "hybrid_commit_evaluation_request_fingerprint": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_evaluation_request_fingerprint",
        ),
        "hybrid_commit_evaluation_request_payload": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_evaluation_request_payload",
        ),
        "hybrid_commit_step_fingerprint": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_step_fingerprint",
        ),
        "hybrid_commit_step_is_authoritative": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_step_is_authoritative",
        ),
        "hybrid_commit_step_payload": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_step_payload",
        ),
        "hybrid_commit_truth_projection": (
            "pheroos.governance.hybrid_commit",
            "hybrid_commit_truth_projection",
        ),
        "initialize_risk_assessment_chain": (
            "pheroos.governance.risk",
            "initialize_risk_assessment_chain",
        ),
        "initialize_support_lease_replay_state": (
            "pheroos.governance.support_lease",
            "initialize_support_lease_replay_state",
        ),
        "issue_commit_evaluation_context": (
            "pheroos.governance.commit",
            "issue_commit_evaluation_context",
        ),
        "issue_commit_liveness_input": (
            "pheroos.governance.commit_state",
            "issue_commit_liveness_input",
        ),
        "issue_evidence_commit_certificate": (
            "pheroos.governance.certificate",
            "issue_evidence_commit_certificate",
        ),
        "issue_local_commit_receipt": (
            "pheroos.governance.certificate",
            "issue_local_commit_receipt",
        ),
        "issue_outcome_certificate": (
            "pheroos.governance.certificate",
            "issue_outcome_certificate",
        ),
        "local_commit_receipt_fingerprint": (
            "pheroos.governance.certificate",
            "local_commit_receipt_fingerprint",
        ),
        "local_commit_receipt_is_authoritative": (
            "pheroos.governance.certificate",
            "local_commit_receipt_is_authoritative",
        ),
        "local_commit_receipt_matches": (
            "pheroos.governance.certificate",
            "local_commit_receipt_matches",
        ),
        "local_commit_receipt_payload": (
            "pheroos.governance.certificate",
            "local_commit_receipt_payload",
        ),
        "outcome_certificate_body_root": (
            "pheroos.governance.certificate",
            "outcome_certificate_body_root",
        ),
        "outcome_certificate_fingerprint": (
            "pheroos.governance.certificate",
            "outcome_certificate_fingerprint",
        ),
        "outcome_certificate_from_payload": (
            "pheroos.governance.certificate",
            "outcome_certificate_from_payload",
        ),
        "outcome_certificate_is_authoritative": (
            "pheroos.governance.certificate",
            "outcome_certificate_is_authoritative",
        ),
        "outcome_certificate_payload": (
            "pheroos.governance.certificate",
            "outcome_certificate_payload",
        ),
        "output_payload_fingerprint": (
            "pheroos.governance.certificate",
            "output_payload_fingerprint",
        ),
        "rebuild_commit_assessment_roots": (
            "pheroos.governance.commit",
            "rebuild_commit_assessment_roots",
        ),
        "reduce_commit_liveness": (
            "pheroos.governance.commit_state",
            "reduce_commit_liveness",
        ),
        "reset_commit_window_state": (
            "pheroos.governance.commit_state",
            "reset_commit_window_state",
        ),
        "risk_assessment_chain_state_fingerprint": (
            "pheroos.governance.risk",
            "risk_assessment_chain_state_fingerprint",
        ),
        "risk_assessment_chain_state_is_authoritative": (
            "pheroos.governance.risk",
            "risk_assessment_chain_state_is_authoritative",
        ),
        "risk_assessment_chain_state_is_current": (
            "pheroos.governance.risk",
            "risk_assessment_chain_state_is_current",
        ),
        "risk_assessment_chain_state_payload": (
            "pheroos.governance.risk",
            "risk_assessment_chain_state_payload",
        ),
        "risk_assessment_is_latest": (
            "pheroos.governance.risk",
            "risk_assessment_is_latest",
        ),
        "support_lease_replay_receipt_payload": (
            "pheroos.governance.support_lease",
            "support_lease_replay_receipt_payload",
        ),
        "support_lease_replay_state_fingerprint": (
            "pheroos.governance.support_lease",
            "support_lease_replay_state_fingerprint",
        ),
        "support_lease_replay_state_is_authoritative": (
            "pheroos.governance.support_lease",
            "support_lease_replay_state_is_authoritative",
        ),
        "support_lease_replay_state_is_current": (
            "pheroos.governance.support_lease",
            "support_lease_replay_state_is_current",
        ),
        "support_lease_replay_state_payload": (
            "pheroos.governance.support_lease",
            "support_lease_replay_state_payload",
        ),
        "verify_evidence_commit_certificate": (
            "pheroos.governance.historical_certificate",
            "verify_evidence_commit_certificate",
        ),
        "verify_evidence_commit_finality": (
            "pheroos.governance.certificate",
            "verify_evidence_commit_finality",
        ),
        "verify_local_commit_finality": (
            "pheroos.governance.certificate",
            "verify_local_commit_finality",
        ),
        "verify_outcome_certificate": (
            "pheroos.governance.certificate",
            "verify_outcome_certificate",
        ),
        "DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR": (
            "pheroos.governance.distributed_commit",
            "DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR",
        ),
        "DISTRIBUTED_COMMIT_CERTIFICATE_VERSION": (
            "pheroos.governance.distributed_commit",
            "DISTRIBUTED_COMMIT_CERTIFICATE_VERSION",
        ),
        "DISTRIBUTED_COMMIT_VALUE_VERSION": (
            "pheroos.governance.distributed_commit",
            "DISTRIBUTED_COMMIT_VALUE_VERSION",
        ),
        "DISTRIBUTED_FINALITY_DECISION_VERSION": (
            "pheroos.governance.distributed_commit",
            "DISTRIBUTED_FINALITY_DECISION_VERSION",
        ),
        "DISTRIBUTED_PROPOSAL_VERSION": (
            "pheroos.governance.distributed_commit",
            "DISTRIBUTED_PROPOSAL_VERSION",
        ),
        "DISTRIBUTED_STATE_VERSION": (
            "pheroos.governance.distributed_commit",
            "DISTRIBUTED_STATE_VERSION",
        ),
        "EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR": (
            "pheroos.governance.distributed_commit",
            "EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR",
        ),
        "EPOCH_TRANSITION_CERTIFICATE_VERSION": (
            "pheroos.governance.distributed_commit",
            "EPOCH_TRANSITION_CERTIFICATE_VERSION",
        ),
        "QUORUM_WITNESS_VERSION": (
            "pheroos.governance.distributed_commit",
            "QUORUM_WITNESS_VERSION",
        ),
        "WITNESS_VERIFICATION_VERSION": (
            "pheroos.governance.distributed_commit",
            "WITNESS_VERIFICATION_VERSION",
        ),
        "CertificateConflictFinding": (
            "pheroos.governance.distributed_commit",
            "CertificateConflictFinding",
        ),
        "DistributedCertificateStatus": (
            "pheroos.governance.distributed_commit",
            "DistributedCertificateStatus",
        ),
        "DistributedCommitCertificate": (
            "pheroos.governance.distributed_commit",
            "DistributedCommitCertificate",
        ),
        "DistributedCommitProposal": (
            "pheroos.governance.distributed_commit",
            "DistributedCommitProposal",
        ),
        "DistributedCommitState": (
            "pheroos.governance.distributed_commit",
            "DistributedCommitState",
        ),
        "DistributedFinalityDecision": (
            "pheroos.governance.distributed_commit",
            "DistributedFinalityDecision",
        ),
        "DistributedFinalityKind": (
            "pheroos.governance.distributed_commit",
            "DistributedFinalityKind",
        ),
        "EpochTransitionCertificate": (
            "pheroos.governance.distributed_commit",
            "EpochTransitionCertificate",
        ),
        "FinalCertificateRegistration": (
            "pheroos.governance.distributed_commit",
            "FinalCertificateRegistration",
        ),
        "PortableEligibleCluster": (
            "pheroos.governance.distributed_commit",
            "PortableEligibleCluster",
        ),
        "PortableEligiblePrincipal": (
            "pheroos.governance.distributed_commit",
            "PortableEligiblePrincipal",
        ),
        "PortableMembershipSnapshot": (
            "pheroos.governance.distributed_commit",
            "PortableMembershipSnapshot",
        ),
        "QuorumWitness": ("pheroos.governance.distributed_commit", "QuorumWitness"),
        "WitnessEquivocationFinding": (
            "pheroos.governance.distributed_commit",
            "WitnessEquivocationFinding",
        ),
        "WitnessReplayReceipt": (
            "pheroos.governance.distributed_commit",
            "WitnessReplayReceipt",
        ),
        "WitnessVerification": (
            "pheroos.governance.distributed_commit",
            "WitnessVerification",
        ),
        "assemble_portable_distributed_commit_certificate": (
            "pheroos.governance.distributed_commit",
            "assemble_portable_distributed_commit_certificate",
        ),
        "distributed_commit_certificate_fingerprint": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_certificate_fingerprint",
        ),
        "distributed_commit_certificate_from_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_certificate_from_payload",
        ),
        "distributed_commit_certificate_is_current_final": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_certificate_is_current_final",
        ),
        "distributed_commit_certificate_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_certificate_payload",
        ),
        "distributed_commit_value_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_value_payload",
        ),
        "distributed_commit_value_root": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_value_root",
        ),
        "distributed_commit_proposal_fingerprint": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_proposal_fingerprint",
        ),
        "distributed_commit_proposal_from_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_proposal_from_payload",
        ),
        "distributed_commit_proposal_is_authoritative": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_proposal_is_authoritative",
        ),
        "distributed_commit_proposal_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_proposal_payload",
        ),
        "distributed_commit_state_fingerprint": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_state_fingerprint",
        ),
        "distributed_commit_state_from_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_state_from_payload",
        ),
        "distributed_commit_state_is_authoritative": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_state_is_authoritative",
        ),
        "distributed_commit_state_is_current": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_state_is_current",
        ),
        "distributed_commit_state_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_commit_state_payload",
        ),
        "distributed_finality_decision_fingerprint": (
            "pheroos.governance.distributed_commit",
            "distributed_finality_decision_fingerprint",
        ),
        "distributed_finality_decision_from_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_finality_decision_from_payload",
        ),
        "distributed_finality_decision_is_authoritative": (
            "pheroos.governance.distributed_commit",
            "distributed_finality_decision_is_authoritative",
        ),
        "distributed_finality_decision_payload": (
            "pheroos.governance.distributed_commit",
            "distributed_finality_decision_payload",
        ),
        "epoch_transition_certificate_body_root": (
            "pheroos.governance.distributed_commit",
            "epoch_transition_certificate_body_root",
        ),
        "epoch_transition_certificate_fingerprint": (
            "pheroos.governance.distributed_commit",
            "epoch_transition_certificate_fingerprint",
        ),
        "epoch_transition_certificate_from_payload": (
            "pheroos.governance.distributed_commit",
            "epoch_transition_certificate_from_payload",
        ),
        "epoch_transition_certificate_payload": (
            "pheroos.governance.distributed_commit",
            "epoch_transition_certificate_payload",
        ),
        "epoch_transition_decision_ref": (
            "pheroos.governance.distributed_commit",
            "epoch_transition_decision_ref",
        ),
        "evaluate_distributed_finality": (
            "pheroos.governance.distributed_commit",
            "evaluate_distributed_finality",
        ),
        "initialize_distributed_commit_state": (
            "pheroos.governance.distributed_commit",
            "initialize_distributed_commit_state",
        ),
        "issue_distributed_commit_certificate": (
            "pheroos.governance.distributed_commit",
            "issue_distributed_commit_certificate",
        ),
        "issue_distributed_commit_proposal": (
            "pheroos.governance.distributed_commit",
            "issue_distributed_commit_proposal",
        ),
        "issue_epoch_transition_certificate": (
            "pheroos.governance.distributed_commit",
            "issue_epoch_transition_certificate",
        ),
        "portable_membership_root": (
            "pheroos.governance.distributed_commit",
            "portable_membership_root",
        ),
        "portable_membership_snapshot_fingerprint": (
            "pheroos.governance.distributed_commit",
            "portable_membership_snapshot_fingerprint",
        ),
        "portable_membership_snapshot_from_eligible": (
            "pheroos.governance.distributed_commit",
            "portable_membership_snapshot_from_eligible",
        ),
        "portable_membership_snapshot_from_payload": (
            "pheroos.governance.distributed_commit",
            "portable_membership_snapshot_from_payload",
        ),
        "portable_membership_snapshot_payload": (
            "pheroos.governance.distributed_commit",
            "portable_membership_snapshot_payload",
        ),
        "quorum_witness_fingerprint": (
            "pheroos.governance.distributed_commit",
            "quorum_witness_fingerprint",
        ),
        "quorum_witness_from_payload": (
            "pheroos.governance.distributed_commit",
            "quorum_witness_from_payload",
        ),
        "quorum_witness_payload": (
            "pheroos.governance.distributed_commit",
            "quorum_witness_payload",
        ),
        "quorum_witness_signing_payload": (
            "pheroos.governance.distributed_commit",
            "quorum_witness_signing_payload",
        ),
        "quorum_witness_signing_root": (
            "pheroos.governance.distributed_commit",
            "quorum_witness_signing_root",
        ),
        "record_witness_verifications": (
            "pheroos.governance.distributed_commit",
            "record_witness_verifications",
        ),
        "register_distributed_commit_certificate": (
            "pheroos.governance.distributed_commit",
            "register_distributed_commit_certificate",
        ),
        "transition_distributed_commit_epoch": (
            "pheroos.governance.distributed_commit",
            "transition_distributed_commit_epoch",
        ),
        "verify_distributed_commit_certificate": (
            "pheroos.governance.distributed_commit",
            "verify_distributed_commit_certificate",
        ),
        "verify_distributed_commit_finality": (
            "pheroos.governance.distributed_commit",
            "verify_distributed_commit_finality",
        ),
        "verify_distributed_commit_proposal": (
            "pheroos.governance.distributed_commit",
            "verify_distributed_commit_proposal",
        ),
        "verify_epoch_transition_certificate": (
            "pheroos.governance.distributed_commit",
            "verify_epoch_transition_certificate",
        ),
        "verify_portable_witness_verification": (
            "pheroos.governance.distributed_commit",
            "verify_portable_witness_verification",
        ),
        "verify_quorum_witness": (
            "pheroos.governance.distributed_commit",
            "verify_quorum_witness",
        ),
        "witness_replay_receipt": (
            "pheroos.governance.distributed_commit",
            "witness_replay_receipt",
        ),
        "witness_replay_receipt_fingerprint": (
            "pheroos.governance.distributed_commit",
            "witness_replay_receipt_fingerprint",
        ),
        "witness_replay_receipt_from_payload": (
            "pheroos.governance.distributed_commit",
            "witness_replay_receipt_from_payload",
        ),
        "witness_replay_receipt_payload": (
            "pheroos.governance.distributed_commit",
            "witness_replay_receipt_payload",
        ),
        "witness_verification_fingerprint": (
            "pheroos.governance.distributed_commit",
            "witness_verification_fingerprint",
        ),
        "witness_verification_from_payload": (
            "pheroos.governance.distributed_commit",
            "witness_verification_from_payload",
        ),
        "witness_verification_is_authoritative": (
            "pheroos.governance.distributed_commit",
            "witness_verification_is_authoritative",
        ),
        "witness_verification_payload": (
            "pheroos.governance.distributed_commit",
            "witness_verification_payload",
        ),
        "challenge_replay_receipt": (
            "pheroos.governance.replay",
            "challenge_replay_receipt",
        ),
        "counterevidence_disposition_replay_receipt": (
            "pheroos.governance.replay",
            "counterevidence_disposition_replay_receipt",
        ),
        "evidence_replay_inputs_are_recorded": (
            "pheroos.governance.replay",
            "evidence_replay_inputs_are_recorded",
        ),
        "missing_evidence_replay_input_refs": (
            "pheroos.governance.replay",
            "missing_evidence_replay_input_refs",
        ),
        "observation_replay_receipt": (
            "pheroos.governance.replay",
            "observation_replay_receipt",
        ),
        "record_evidence_replay_inputs": (
            "pheroos.governance.replay",
            "record_evidence_replay_inputs",
        ),
        "ATOMIC_HYBRID_COMMIT_VERSION": (
            "pheroos.governance.atomic_evaluation",
            "ATOMIC_HYBRID_COMMIT_VERSION",
        ),
        "AtomicHybridCommitResult": (
            "pheroos.governance.atomic_evaluation",
            "AtomicHybridCommitResult",
        ),
        "AtomicHybridCommitStatus": (
            "pheroos.governance.atomic_evaluation",
            "AtomicHybridCommitStatus",
        ),
        "PreparedHybridCommitTransition": (
            "pheroos.governance.atomic_evaluation",
            "PreparedHybridCommitTransition",
        ),
        "commit_prepared_hybrid_transition": (
            "pheroos.governance.atomic_evaluation",
            "commit_prepared_hybrid_transition",
        ),
        "evaluate_and_commit_hybrid_step": (
            "pheroos.governance.atomic_evaluation",
            "evaluate_and_commit_hybrid_step",
        ),
        "finalize_hybrid_commit_transition": (
            "pheroos.governance.atomic_evaluation",
            "finalize_hybrid_commit_transition",
        ),
        "hybrid_commit_stream": (
            "pheroos.governance.atomic_evaluation",
            "hybrid_commit_stream",
        ),
        "prepare_hybrid_commit_transition": (
            "pheroos.governance.atomic_evaluation",
            "prepare_hybrid_commit_transition",
        ),
        "AUTHORITY_AUTHENTICATED_PROFILE_V2": (
            "pheroos.governance.authority_store_v2",
            "AUTHORITY_AUTHENTICATED_PROFILE_V2",
        ),
        "AUTHORITY_DOMAIN_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "AUTHORITY_DOMAIN_SCHEMA_V2",
        ),
        "AUTHORITY_LEDGER_VERSION_V2": (
            "pheroos.governance.authority_store_v2",
            "AUTHORITY_LEDGER_VERSION_V2",
        ),
        "AUTHORITY_LOCAL_PROFILE_V2": (
            "pheroos.governance.authority_store_v2",
            "AUTHORITY_LOCAL_PROFILE_V2",
        ),
        "AUTHORITY_POLICY_VERSION_V2": (
            "pheroos.governance.authority_store_v2",
            "AUTHORITY_POLICY_VERSION_V2",
        ),
        "AUTHORITY_WIRE_VERSION_V2": (
            "pheroos.governance.authority_store_v2",
            "AUTHORITY_WIRE_VERSION_V2",
        ),
        "GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2",
        ),
        "GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2",
        ),
        "GOVERNANCE_COMMIT_BATCH_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMIT_BATCH_SCHEMA_V2",
        ),
        "GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2",
        ),
        "GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2",
        ),
        "GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2",
        ),
        "GOVERNANCE_COMMIT_VIEW_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_COMMIT_VIEW_SCHEMA_V2",
        ),
        "GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2",
        ),
        "GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2",
        ),
        "GOVERNANCE_FAILURE_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_FAILURE_SCHEMA_V2",
        ),
        "GOVERNANCE_GENESIS_PARENT_ROOT_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_GENESIS_PARENT_ROOT_V2",
        ),
        "GOVERNANCE_HEAD_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_HEAD_SCHEMA_V2",
        ),
        "GOVERNANCE_STATE_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_STATE_SCHEMA_V2",
        ),
        "GOVERNANCE_STATE_STORE_VERSION_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_STATE_STORE_VERSION_V2",
        ),
        "GOVERNANCE_TRACE_BATCH_VERSION_V2": (
            "pheroos.governance.authority_store_v2",
            "GOVERNANCE_TRACE_BATCH_VERSION_V2",
        ),
        "MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2": (
            "pheroos.governance.authority_store_v2",
            "MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2",
        ),
        "MAX_GOVERNANCE_TRACE_EVENTS_V2": (
            "pheroos.governance.authority_store_v2",
            "MAX_GOVERNANCE_TRACE_EVENTS_V2",
        ),
        "PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2": (
            "pheroos.governance.authority_store_v2",
            "PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2",
        ),
        "AuthorityDiagnosticCodeV2": (
            "pheroos.protocol.authority_v2",
            "AuthorityDiagnosticCodeV2",
        ),
        "AuthorityDomainV2": (
            "pheroos.governance.authority_store_v2",
            "AuthorityDomainV2",
        ),
        "GovernanceAuthorityReadSetV2": (
            "pheroos.protocol.authority_v2",
            "GovernanceAuthorityReadSetV2",
        ),
        "GovernanceCommitAttemptV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitAttemptV2",
        ),
        "GovernanceCommitBatchV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitBatchV2",
        ),
        "GovernanceCommitDispositionV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitDispositionV2",
        ),
        "GovernanceCommitInclusionProofV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitInclusionProofV2",
        ),
        "GovernanceCommitPositionObservationV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitPositionObservationV2",
        ),
        "GovernanceCommitPositionV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitPositionV2",
        ),
        "GovernanceCommitReceiptV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitReceiptV2",
        ),
        "GovernanceCommitViewV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommitViewV2",
        ),
        "GovernanceCommittedTransitionV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceCommittedTransitionV2",
        ),
        "GovernanceDomainSealV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceDomainSealV2",
        ),
        "GovernanceFailureStageV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceFailureStageV2",
        ),
        "GovernanceFailureV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceFailureV2",
        ),
        "GovernanceHeadV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceHeadV2",
        ),
        "GovernanceStateReaderV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceStateReaderV2",
        ),
        "GovernanceStateStoreV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceStateStoreV2",
        ),
        "GovernanceStateWriterV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceStateWriterV2",
        ),
        "GovernanceTraceBatchV2": (
            "pheroos.governance.authority_store_v2",
            "GovernanceTraceBatchV2",
        ),
        "PreparedGovernanceTransitionV2": (
            "pheroos.governance.authority_store_v2",
            "PreparedGovernanceTransitionV2",
        ),
        "governance_authority_state_root_v2": (
            "pheroos.governance.authority_store_v2",
            "governance_authority_state_root_v2",
        ),
        "GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2": (
            "pheroos.governance.authority_session_v2",
            "GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2",
        ),
        "GOVERNANCE_ISSUER_GRANT_SCHEMA_V2": (
            "pheroos.governance.authority_session_v2",
            "GOVERNANCE_ISSUER_GRANT_SCHEMA_V2",
        ),
        "GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2": (
            "pheroos.governance.authority_session_v2",
            "GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2",
        ),
        "GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2": (
            "pheroos.governance.authority_session_v2",
            "GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2",
        ),
        "GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2": (
            "pheroos.governance.authority_session_v2",
            "GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2",
        ),
        "ISSUER_GRANT_VERIFICATION_SCHEMA_V2": (
            "pheroos.governance.authority_session_v2",
            "ISSUER_GRANT_VERIFICATION_SCHEMA_V2",
        ),
        "GovernanceAuthorityBindingErrorV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceAuthorityBindingErrorV2",
        ),
        "GovernanceAuthoritySessionV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceAuthoritySessionV2",
        ),
        "GovernanceDomainRetirementRequestV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceDomainRetirementRequestV2",
        ),
        "GovernanceIssuerCapabilityV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceIssuerCapabilityV2",
        ),
        "GovernanceIssuerGrantV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceIssuerGrantV2",
        ),
        "GovernanceIssuerOperationV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceIssuerOperationV2",
        ),
        "GovernanceVerifiedSignalRequestV2": (
            "pheroos.governance.authority_session_v2",
            "GovernanceVerifiedSignalRequestV2",
        ),
        "IssuerGrantVerificationV2": (
            "pheroos.governance.authority_session_v2",
            "IssuerGrantVerificationV2",
        ),
        "IssuerGrantVerifierV2": (
            "pheroos.governance.authority_session_v2",
            "IssuerGrantVerifierV2",
        ),
        "activate_governance_issuer_grant_v2": (
            "pheroos.governance.authority_session_v2",
            "activate_governance_issuer_grant_v2",
        ),
        "bind_governance_issuer_capability_v2": (
            "pheroos.governance.authority_session_v2",
            "bind_governance_issuer_capability_v2",
        ),
        "commit_verified_signal_v2": (
            "pheroos.governance.authority_session_v2",
            "commit_verified_signal_v2",
        ),
        "governance_issuer_grant_stream_ref_v2": (
            "pheroos.governance.authority_session_v2",
            "governance_issuer_grant_stream_ref_v2",
        ),
        "governance_verified_signal_stream_ref_v2": (
            "pheroos.governance.authority_session_v2",
            "governance_verified_signal_stream_ref_v2",
        ),
        "open_governance_authority_session_v2": (
            "pheroos.governance.authority_session_v2",
            "open_governance_authority_session_v2",
        ),
        "retire_governance_domain_v2": (
            "pheroos.governance.authority_session_v2",
            "retire_governance_domain_v2",
        ),
        "revoke_governance_issuer_grant_v2": (
            "pheroos.governance.authority_session_v2",
            "revoke_governance_issuer_grant_v2",
        ),
        "ACTION_PERMISSION_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "ACTION_PERMISSION_SCHEMA_V2",
        ),
        "BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2",
        ),
        "BASELINE_DECISION_STATE_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_DECISION_STATE_SCHEMA_V2",
        ),
        "BASELINE_EVIDENCE_STATE_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_EVIDENCE_STATE_SCHEMA_V2",
        ),
        "BASELINE_MANIFEST_STATE_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_MANIFEST_STATE_SCHEMA_V2",
        ),
        "BASELINE_OUTPUT_REQUEST_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_OUTPUT_REQUEST_SCHEMA_V2",
        ),
        "BASELINE_OUTPUT_RESULT_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_OUTPUT_RESULT_SCHEMA_V2",
        ),
        "BASELINE_OUTPUT_STATE_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_OUTPUT_STATE_SCHEMA_V2",
        ),
        "BASELINE_STOP_STATE_SCHEMA_V2": (
            "pheroos.governance.baseline_output_v2",
            "BASELINE_STOP_STATE_SCHEMA_V2",
        ),
        "ActionPermissionDispositionV2": (
            "pheroos.governance.baseline_output_v2",
            "ActionPermissionDispositionV2",
        ),
        "ActionPermissionV2": (
            "pheroos.governance.baseline_output_v2",
            "ActionPermissionV2",
        ),
        "BaselineOutputActionDispositionV2": (
            "pheroos.governance.baseline_output_v2",
            "BaselineOutputActionDispositionV2",
        ),
        "BaselineOutputDeliveryDispositionV2": (
            "pheroos.governance.baseline_output_v2",
            "BaselineOutputDeliveryDispositionV2",
        ),
        "BaselineOutputRequestV2": (
            "pheroos.governance.baseline_output_v2",
            "BaselineOutputRequestV2",
        ),
        "BaselineOutputResultV2": (
            "pheroos.governance.baseline_output_v2",
            "BaselineOutputResultV2",
        ),
        "BaselineOutputTerminalStatusV2": (
            "pheroos.governance.baseline_output_v2",
            "BaselineOutputTerminalStatusV2",
        ),
        "baseline_action_permission_stream_ref_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_action_permission_stream_ref_v2",
        ),
        "baseline_decision_stream_ref_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_decision_stream_ref_v2",
        ),
        "baseline_evidence_stream_ref_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_evidence_stream_ref_v2",
        ),
        "baseline_manifest_stream_ref_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_manifest_stream_ref_v2",
        ),
        "baseline_output_result_root_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_output_result_root_v2",
        ),
        "baseline_output_stream_ref_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_output_stream_ref_v2",
        ),
        "baseline_stop_stream_ref_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_stop_stream_ref_v2",
        ),
        "baseline_verified_signal_proposal_root_v2": (
            "pheroos.governance.baseline_output_v2",
            "baseline_verified_signal_proposal_root_v2",
        ),
        "evaluate_and_commit_baseline_output_v2": (
            "pheroos.governance.baseline_output_v2",
            "evaluate_and_commit_baseline_output_v2",
        ),
        "issue_action_permission_v2": (
            "pheroos.governance.baseline_output_v2",
            "issue_action_permission_v2",
        ),
        "open_baseline_output_authority_session_v2": (
            "pheroos.governance.baseline_output_v2",
            "open_baseline_output_authority_session_v2",
        ),
        "HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.hybrid_replay_v2",
            "HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2",
        ),
        "HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2": (
            "pheroos.governance.hybrid_replay_v2",
            "HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2",
        ),
        "HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.hybrid_replay_v2",
            "HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2": (
            "pheroos.governance.hybrid_replay_v2",
            "HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2",
        ),
        "HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.hybrid_replay_v2",
            "HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2",
        ),
        "HYBRID_REPLAY_STATE_SCHEMA_V2": (
            "pheroos.governance.hybrid_replay_v2",
            "HYBRID_REPLAY_STATE_SCHEMA_V2",
        ),
        "HybridReplayAdvanceRequestV2": (
            "pheroos.governance.hybrid_replay_v2",
            "HybridReplayAdvanceRequestV2",
        ),
        "HybridReplaySnapshotV2": (
            "pheroos.governance.hybrid_replay_v2",
            "HybridReplaySnapshotV2",
        ),
        "VerifiedHybridReplayStateV2": (
            "pheroos.governance.hybrid_replay_v2",
            "VerifiedHybridReplayStateV2",
        ),
        "VerifiedHybridSourceStepV2": (
            "pheroos.governance.hybrid_replay_v2",
            "VerifiedHybridSourceStepV2",
        ),
        "advance_hybrid_replay_state_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "advance_hybrid_replay_state_v2",
        ),
        "build_hybrid_replay_advance_request_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "build_hybrid_replay_advance_request_v2",
        ),
        "evaluate_hybrid_collective_step_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "evaluate_hybrid_collective_step_v2",
        ),
        "hybrid_replay_diffusion_source_trail_root_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "hybrid_replay_diffusion_source_trail_root_v2",
        ),
        "hybrid_replay_state_is_current_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "hybrid_replay_state_is_current_v2",
        ),
        "hybrid_replay_stream_ref_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "hybrid_replay_stream_ref_v2",
        ),
        "hybrid_replay_transition_id_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "hybrid_replay_transition_id_v2",
        ),
        "open_hybrid_replay_authority_session_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "open_hybrid_replay_authority_session_v2",
        ),
        "rehydrate_hybrid_replay_state_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "rehydrate_hybrid_replay_state_v2",
        ),
        "require_current_hybrid_replay_state_v2": (
            "pheroos.governance.hybrid_replay_v2",
            "require_current_hybrid_replay_state_v2",
        ),
        "COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2",
        ),
        "COMMIT_REPLAY_EMPTY_RECEIPT_ROOT_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_EMPTY_RECEIPT_ROOT_V2",
        ),
        "COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2",
        ),
        "COMMIT_REPLAY_RECEIPT_SCHEMA_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_RECEIPT_SCHEMA_V2",
        ),
        "COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2",
        ),
        "COMMIT_REPLAY_STATE_SCHEMA_V2": (
            "pheroos.governance.commit_state_v2",
            "COMMIT_REPLAY_STATE_SCHEMA_V2",
        ),
        "CommitReplayAdvanceRequestV2": (
            "pheroos.governance.commit_state_v2",
            "CommitReplayAdvanceRequestV2",
        ),
        "CommitReplayReceiptV2": (
            "pheroos.governance.commit_state_v2",
            "CommitReplayReceiptV2",
        ),
        "CommitReplaySnapshotV2": (
            "pheroos.governance.commit_state_v2",
            "CommitReplaySnapshotV2",
        ),
        "VerifiedCommitReplaySourceV2": (
            "pheroos.governance.commit_state_v2",
            "VerifiedCommitReplaySourceV2",
        ),
        "VerifiedCommitReplayStateV2": (
            "pheroos.governance.commit_state_v2",
            "VerifiedCommitReplayStateV2",
        ),
        "advance_commit_replay_state_v2": (
            "pheroos.governance.commit_state_v2",
            "advance_commit_replay_state_v2",
        ),
        "canonical_commit_replay_receipts_v2": (
            "pheroos.governance.commit_state_v2",
            "canonical_commit_replay_receipts_v2",
        ),
        "commit_replay_receipt_set_root_v2": (
            "pheroos.governance.commit_state_v2",
            "commit_replay_receipt_set_root_v2",
        ),
        "commit_replay_state_is_current_v2": (
            "pheroos.governance.commit_state_v2",
            "commit_replay_state_is_current_v2",
        ),
        "commit_replay_stream_ref_v2": (
            "pheroos.governance.commit_state_v2",
            "commit_replay_stream_ref_v2",
        ),
        "commit_replay_transition_id_v2": (
            "pheroos.governance.commit_state_v2",
            "commit_replay_transition_id_v2",
        ),
        "open_commit_replay_authority_session_v2": (
            "pheroos.governance.commit_state_v2",
            "open_commit_replay_authority_session_v2",
        ),
        "prepare_commit_replay_advance_v2": (
            "pheroos.governance.commit_state_v2",
            "prepare_commit_replay_advance_v2",
        ),
        "rehydrate_commit_replay_state_v2": (
            "pheroos.governance.commit_state_v2",
            "rehydrate_commit_replay_state_v2",
        ),
        "require_current_commit_replay_state_v2": (
            "pheroos.governance.commit_state_v2",
            "require_current_commit_replay_state_v2",
        ),
        "MAX_RISK_INPUT_ROOTS_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_INPUT_ROOTS_V2",
        ),
        "MAX_RISK_RATIONALE_CODES_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_RATIONALE_CODES_V2",
        ),
        "MAX_RISK_RESOURCE_DEPTH_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_RESOURCE_DEPTH_V2",
        ),
        "MAX_RISK_RESOURCE_NODES_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_RESOURCE_NODES_V2",
        ),
        "MAX_RISK_RESOURCE_TEXT_BYTES_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_RESOURCE_TEXT_BYTES_V2",
        ),
        "MAX_RISK_SNAPSHOT_BYTES_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_SNAPSHOT_BYTES_V2",
        ),
        "MAX_RISK_SOURCE_TRACE_ROOTS_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_SOURCE_TRACE_ROOTS_V2",
        ),
        "MAX_RISK_TEXT_BYTES_V2": (
            "pheroos.governance.risk_v2",
            "MAX_RISK_TEXT_BYTES_V2",
        ),
        "RISK_ASSESSMENT_RECORD_SCHEMA_V2": (
            "pheroos.governance.risk_v2",
            "RISK_ASSESSMENT_RECORD_SCHEMA_V2",
        ),
        "RISK_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.risk_v2",
            "RISK_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "RISK_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.risk_v2",
            "RISK_GENESIS_TRANSITION_ID_V2",
        ),
        "RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.risk_v2",
            "RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2",
        ),
        "RISK_STATE_SCHEMA_V2": ("pheroos.governance.risk_v2", "RISK_STATE_SCHEMA_V2"),
        "RISK_STATE_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.risk_v2",
            "RISK_STATE_SNAPSHOT_SCHEMA_V2",
        ),
        "RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.risk_v2",
            "RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2",
        ),
        "RiskAssessmentRecordV2": (
            "pheroos.governance.risk_v2",
            "RiskAssessmentRecordV2",
        ),
        "RiskStateAdvanceRequestV2": (
            "pheroos.governance.risk_v2",
            "RiskStateAdvanceRequestV2",
        ),
        "RiskStateSnapshotV2": ("pheroos.governance.risk_v2", "RiskStateSnapshotV2"),
        "RiskThresholdSnapshotV2": (
            "pheroos.governance.risk_v2",
            "RiskThresholdSnapshotV2",
        ),
        "VerifiedRiskSourceV2": ("pheroos.governance.risk_v2", "VerifiedRiskSourceV2"),
        "VerifiedRiskStateV2": ("pheroos.governance.risk_v2", "VerifiedRiskStateV2"),
        "advance_risk_state_v2": (
            "pheroos.governance.risk_v2",
            "advance_risk_state_v2",
        ),
        "open_risk_authority_session_v2": (
            "pheroos.governance.risk_v2",
            "open_risk_authority_session_v2",
        ),
        "prepare_risk_state_advance_v2": (
            "pheroos.governance.risk_v2",
            "prepare_risk_state_advance_v2",
        ),
        "rehydrate_risk_state_v2": (
            "pheroos.governance.risk_v2",
            "rehydrate_risk_state_v2",
        ),
        "require_current_risk_state_v2": (
            "pheroos.governance.risk_v2",
            "require_current_risk_state_v2",
        ),
        "risk_state_is_current_v2": (
            "pheroos.governance.risk_v2",
            "risk_state_is_current_v2",
        ),
        "risk_state_stream_ref_v2": (
            "pheroos.governance.risk_v2",
            "risk_state_stream_ref_v2",
        ),
        "risk_state_transition_id_v2": (
            "pheroos.governance.risk_v2",
            "risk_state_transition_id_v2",
        ),
        "verify_risk_state_request_source_v2": (
            "pheroos.governance.risk_v2",
            "verify_risk_state_request_source_v2",
        ),
        "MAX_MEMBERSHIP_CLUSTERS_V2": (
            "pheroos.governance.support_v2",
            "MAX_MEMBERSHIP_CLUSTERS_V2",
        ),
        "MAX_MEMBERSHIP_PRINCIPALS_V2": (
            "pheroos.governance.support_v2",
            "MAX_MEMBERSHIP_PRINCIPALS_V2",
        ),
        "MAX_MEMBERSHIP_SNAPSHOT_BYTES_V2": (
            "pheroos.governance.support_v2",
            "MAX_MEMBERSHIP_SNAPSHOT_BYTES_V2",
        ),
        "MAX_PRINCIPAL_VERIFICATIONS_V2": (
            "pheroos.governance.support_v2",
            "MAX_PRINCIPAL_VERIFICATIONS_V2",
        ),
        "MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2": (
            "pheroos.governance.support_v2",
            "MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2",
        ),
        "MAX_SUPPORT_LEASES_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_LEASES_V2",
        ),
        "MAX_SUPPORT_OBSERVATIONS_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_OBSERVATIONS_V2",
        ),
        "MAX_SUPPORT_REASON_CODES_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_REASON_CODES_V2",
        ),
        "MAX_SUPPORT_EVICTIONS_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_EVICTIONS_V2",
        ),
        "MAX_SUPPORT_RESOURCE_DEPTH_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_RESOURCE_DEPTH_V2",
        ),
        "MAX_SUPPORT_RESOURCE_NODES_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_RESOURCE_NODES_V2",
        ),
        "MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2",
        ),
        "MAX_SUPPORT_SNAPSHOT_BYTES_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_SNAPSHOT_BYTES_V2",
        ),
        "MAX_SUPPORT_TEXT_BYTES_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_TEXT_BYTES_V2",
        ),
        "MAX_SUPPORT_TRACE_ROOTS_V2": (
            "pheroos.governance.support_v2",
            "MAX_SUPPORT_TRACE_ROOTS_V2",
        ),
        "MAX_VERIFICATION_EVIDENCE_ROOTS_V2": (
            "pheroos.governance.support_v2",
            "MAX_VERIFICATION_EVIDENCE_ROOTS_V2",
        ),
        "MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2": (
            "pheroos.governance.support_v2",
            "MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2",
        ),
        "MEMBERSHIP_CLUSTER_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_CLUSTER_SCHEMA_V2",
        ),
        "MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2",
        ),
        "MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "MEMBERSHIP_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_GENESIS_TRANSITION_ID_V2",
        ),
        "MEMBERSHIP_POLICY_VERSION_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_POLICY_VERSION_V2",
        ),
        "MEMBERSHIP_PRINCIPAL_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_PRINCIPAL_SCHEMA_V2",
        ),
        "MEMBERSHIP_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_SNAPSHOT_SCHEMA_V2",
        ),
        "MEMBERSHIP_STATE_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "MEMBERSHIP_STATE_SCHEMA_V2",
        ),
        "PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2",
        ),
        "PRINCIPAL_VERIFICATION_POLICY_VERSION_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_POLICY_VERSION_V2",
        ),
        "PRINCIPAL_VERIFICATION_RECORD_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_RECORD_SCHEMA_V2",
        ),
        "PRINCIPAL_VERIFICATION_SET_REQUEST_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_SET_REQUEST_SCHEMA_V2",
        ),
        "PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2",
        ),
        "PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2",
        ),
        "SUPPORT_ADVANCE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_ADVANCE_REQUEST_SCHEMA_V2",
        ),
        "SUPPORT_EQUIVOCATION_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_EQUIVOCATION_SCHEMA_V2",
        ),
        "SUPPORT_EVALUATION_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_EVALUATION_SCHEMA_V2",
        ),
        "SUPPORT_GENESIS_HISTORY_ROOT_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_GENESIS_HISTORY_ROOT_V2",
        ),
        "SUPPORT_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "SUPPORT_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_GENESIS_TRANSITION_ID_V2",
        ),
        "SUPPORT_LEASE_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_LEASE_SCHEMA_V2",
        ),
        "SUPPORT_OBSERVATION_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_OBSERVATION_SCHEMA_V2",
        ),
        "SUPPORT_PROPOSAL_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_PROPOSAL_SCHEMA_V2",
        ),
        "SUPPORT_REVOCATION_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_REVOCATION_SCHEMA_V2",
        ),
        "SUPPORT_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_SNAPSHOT_SCHEMA_V2",
        ),
        "SUPPORT_STATE_SCHEMA_V2": (
            "pheroos.governance.support_v2",
            "SUPPORT_STATE_SCHEMA_V2",
        ),
        "DurableSupportContextV2": (
            "pheroos.governance.support_v2",
            "DurableSupportContextV2",
        ),
        "MembershipClusterV2": ("pheroos.governance.support_v2", "MembershipClusterV2"),
        "MembershipCommitRequestV2": (
            "pheroos.governance.support_v2",
            "MembershipCommitRequestV2",
        ),
        "MembershipPrincipalV2": (
            "pheroos.governance.support_v2",
            "MembershipPrincipalV2",
        ),
        "MembershipSnapshotV2": (
            "pheroos.governance.support_v2",
            "MembershipSnapshotV2",
        ),
        "PrincipalVerificationRecordV2": (
            "pheroos.governance.support_v2",
            "PrincipalVerificationRecordV2",
        ),
        "PrincipalVerificationSetAdvanceRequestV2": (
            "pheroos.governance.support_v2",
            "PrincipalVerificationSetAdvanceRequestV2",
        ),
        "PrincipalVerificationSetSnapshotV2": (
            "pheroos.governance.support_v2",
            "PrincipalVerificationSetSnapshotV2",
        ),
        "SupportAdvanceRequestV2": (
            "pheroos.governance.support_v2",
            "SupportAdvanceRequestV2",
        ),
        "SupportEquivocationV2": (
            "pheroos.governance.support_v2",
            "SupportEquivocationV2",
        ),
        "SupportEvaluationV2": ("pheroos.governance.support_v2", "SupportEvaluationV2"),
        "SupportLeaseProposalV2": (
            "pheroos.governance.support_v2",
            "SupportLeaseProposalV2",
        ),
        "SupportLeaseStatusV2": (
            "pheroos.governance.support_v2",
            "SupportLeaseStatusV2",
        ),
        "SupportLeaseV2": ("pheroos.governance.support_v2", "SupportLeaseV2"),
        "SupportMutationKindV2": (
            "pheroos.governance.support_v2",
            "SupportMutationKindV2",
        ),
        "SupportObservationV2": (
            "pheroos.governance.support_v2",
            "SupportObservationV2",
        ),
        "SupportRevocationV2": ("pheroos.governance.support_v2", "SupportRevocationV2"),
        "SupportSnapshotV2": ("pheroos.governance.support_v2", "SupportSnapshotV2"),
        "VerifiedMembershipSourceV2": (
            "pheroos.governance.support_v2",
            "VerifiedMembershipSourceV2",
        ),
        "VerifiedMembershipStateV2": (
            "pheroos.governance.support_v2",
            "VerifiedMembershipStateV2",
        ),
        "VerifiedPrincipalVerificationSourceV2": (
            "pheroos.governance.support_v2",
            "VerifiedPrincipalVerificationSourceV2",
        ),
        "VerifiedPrincipalVerificationSetStateV2": (
            "pheroos.governance.support_v2",
            "VerifiedPrincipalVerificationSetStateV2",
        ),
        "VerifiedSupportSourceV2": (
            "pheroos.governance.support_v2",
            "VerifiedSupportSourceV2",
        ),
        "VerifiedSupportStateV2": (
            "pheroos.governance.support_v2",
            "VerifiedSupportStateV2",
        ),
        "active_support_lease_from_parent_v2": (
            "pheroos.governance.support_v2",
            "active_support_lease_from_parent_v2",
        ),
        "advance_principal_verification_set_v2": (
            "pheroos.governance.support_v2",
            "advance_principal_verification_set_v2",
        ),
        "advance_support_state_v2": (
            "pheroos.governance.support_v2",
            "advance_support_state_v2",
        ),
        "canonical_membership_clusters_v2": (
            "pheroos.governance.support_v2",
            "canonical_membership_clusters_v2",
        ),
        "canonical_support_leases_v2": (
            "pheroos.governance.support_v2",
            "canonical_support_leases_v2",
        ),
        "canonical_support_observations_v2": (
            "pheroos.governance.support_v2",
            "canonical_support_observations_v2",
        ),
        "canonical_verification_records_v2": (
            "pheroos.governance.support_v2",
            "canonical_verification_records_v2",
        ),
        "commit_membership_epoch_v2": (
            "pheroos.governance.support_v2",
            "commit_membership_epoch_v2",
        ),
        "durable_support_context_v2": (
            "pheroos.governance.support_v2",
            "durable_support_context_v2",
        ),
        "evaluate_support_v2": ("pheroos.governance.support_v2", "evaluate_support_v2"),
        "membership_projection_root_v2": (
            "pheroos.governance.support_v2",
            "membership_projection_root_v2",
        ),
        "membership_state_is_current_v2": (
            "pheroos.governance.support_v2",
            "membership_state_is_current_v2",
        ),
        "membership_stream_ref_v2": (
            "pheroos.governance.support_v2",
            "membership_stream_ref_v2",
        ),
        "membership_transition_id_v2": (
            "pheroos.governance.support_v2",
            "membership_transition_id_v2",
        ),
        "open_membership_authority_session_v2": (
            "pheroos.governance.support_v2",
            "open_membership_authority_session_v2",
        ),
        "open_principal_verification_authority_session_v2": (
            "pheroos.governance.support_v2",
            "open_principal_verification_authority_session_v2",
        ),
        "open_support_authority_session_v2": (
            "pheroos.governance.support_v2",
            "open_support_authority_session_v2",
        ),
        "prepare_membership_commit_v2": (
            "pheroos.governance.support_v2",
            "prepare_membership_commit_v2",
        ),
        "prepare_principal_verification_set_v2": (
            "pheroos.governance.support_v2",
            "prepare_principal_verification_set_v2",
        ),
        "prepare_support_initialize_v2": (
            "pheroos.governance.support_v2",
            "prepare_support_initialize_v2",
        ),
        "prepare_support_issue_v2": (
            "pheroos.governance.support_v2",
            "prepare_support_issue_v2",
        ),
        "prepare_support_revoke_v2": (
            "pheroos.governance.support_v2",
            "prepare_support_revoke_v2",
        ),
        "prepare_support_switch_v2": (
            "pheroos.governance.support_v2",
            "prepare_support_switch_v2",
        ),
        "principal_verification_set_is_current_v2": (
            "pheroos.governance.support_v2",
            "principal_verification_set_is_current_v2",
        ),
        "principal_verification_stream_ref_v2": (
            "pheroos.governance.support_v2",
            "principal_verification_stream_ref_v2",
        ),
        "principal_verification_transition_id_v2": (
            "pheroos.governance.support_v2",
            "principal_verification_transition_id_v2",
        ),
        "project_support_lease_v2": (
            "pheroos.governance.support_v2",
            "project_support_lease_v2",
        ),
        "project_support_revocation_v2": (
            "pheroos.governance.support_v2",
            "project_support_revocation_v2",
        ),
        "rehydrate_membership_state_v2": (
            "pheroos.governance.support_v2",
            "rehydrate_membership_state_v2",
        ),
        "rehydrate_principal_verification_set_state_v2": (
            "pheroos.governance.support_v2",
            "rehydrate_principal_verification_set_state_v2",
        ),
        "rehydrate_support_state_v2": (
            "pheroos.governance.support_v2",
            "rehydrate_support_state_v2",
        ),
        "replacement_matches_prior_v2": (
            "pheroos.governance.support_v2",
            "replacement_matches_prior_v2",
        ),
        "require_current_membership_state_v2": (
            "pheroos.governance.support_v2",
            "require_current_membership_state_v2",
        ),
        "require_current_principal_verification_set_v2": (
            "pheroos.governance.support_v2",
            "require_current_principal_verification_set_v2",
        ),
        "require_current_support_state_v2": (
            "pheroos.governance.support_v2",
            "require_current_support_state_v2",
        ),
        "revocation_matches_lease_v2": (
            "pheroos.governance.support_v2",
            "revocation_matches_lease_v2",
        ),
        "support_event_lineage_v2": (
            "pheroos.governance.support_v2",
            "support_event_lineage_v2",
        ),
        "support_history_advance_v2": (
            "pheroos.governance.support_v2",
            "support_history_advance_v2",
        ),
        "support_issued_event_lineage_v2": (
            "pheroos.governance.support_v2",
            "support_issued_event_lineage_v2",
        ),
        "support_lease_ref_v2": (
            "pheroos.governance.support_v2",
            "support_lease_ref_v2",
        ),
        "support_lease_status_v2": (
            "pheroos.governance.support_v2",
            "support_lease_status_v2",
        ),
        "support_mutation_delta_root_v2": (
            "pheroos.governance.support_v2",
            "support_mutation_delta_root_v2",
        ),
        "support_revocation_ref_v2": (
            "pheroos.governance.support_v2",
            "support_revocation_ref_v2",
        ),
        "support_revoked_event_lineage_v2": (
            "pheroos.governance.support_v2",
            "support_revoked_event_lineage_v2",
        ),
        "support_state_is_current_v2": (
            "pheroos.governance.support_v2",
            "support_state_is_current_v2",
        ),
        "support_stream_ref_v2": (
            "pheroos.governance.support_v2",
            "support_stream_ref_v2",
        ),
        "support_switch_lineage_v2": (
            "pheroos.governance.support_v2",
            "support_switch_lineage_v2",
        ),
        "support_transition_id_v2": (
            "pheroos.governance.support_v2",
            "support_transition_id_v2",
        ),
        "verify_membership_request_source_v2": (
            "pheroos.governance.support_v2",
            "verify_membership_request_source_v2",
        ),
        "verify_principal_verification_source_v2": (
            "pheroos.governance.support_v2",
            "verify_principal_verification_source_v2",
        ),
        "verify_support_request_source_v2": (
            "pheroos.governance.support_v2",
            "verify_support_request_source_v2",
        ),
        "COMMIT_GATE_DEPENDENCIES_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_GATE_DEPENDENCIES_SCHEMA_V2",
        ),
        "COMMIT_GATE_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_GATE_GENESIS_TRANSITION_ID_V2",
        ),
        "COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "COMMIT_PERMISSION_POLICY_VERSION_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_PERMISSION_POLICY_VERSION_V2",
        ),
        "COMMIT_PERMISSION_REQUEST_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_PERMISSION_REQUEST_SCHEMA_V2",
        ),
        "COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2",
        ),
        "COMMIT_PERMISSION_STATE_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_PERMISSION_STATE_SCHEMA_V2",
        ),
        "COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "COMMIT_STOP_POLICY_VERSION_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_STOP_POLICY_VERSION_V2",
        ),
        "COMMIT_STOP_REQUEST_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_STOP_REQUEST_SCHEMA_V2",
        ),
        "COMMIT_STOP_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_STOP_SNAPSHOT_SCHEMA_V2",
        ),
        "COMMIT_STOP_STATE_SCHEMA_V2": (
            "pheroos.governance.commit_gate_v2",
            "COMMIT_STOP_STATE_SCHEMA_V2",
        ),
        "MAX_COMMIT_GATE_ITEMS_V2": (
            "pheroos.governance.commit_gate_v2",
            "MAX_COMMIT_GATE_ITEMS_V2",
        ),
        "MAX_COMMIT_GATE_SNAPSHOT_BYTES_V2": (
            "pheroos.governance.commit_gate_v2",
            "MAX_COMMIT_GATE_SNAPSHOT_BYTES_V2",
        ),
        "MAX_COMMIT_GATE_TEXT_BYTES_V2": (
            "pheroos.governance.commit_gate_v2",
            "MAX_COMMIT_GATE_TEXT_BYTES_V2",
        ),
        "CommitGateDependenciesV2": (
            "pheroos.governance.commit_gate_v2",
            "CommitGateDependenciesV2",
        ),
        "CommitPermissionRequestV2": (
            "pheroos.governance.commit_gate_v2",
            "CommitPermissionRequestV2",
        ),
        "CommitPermissionSnapshotV2": (
            "pheroos.governance.commit_gate_v2",
            "CommitPermissionSnapshotV2",
        ),
        "CommitStopRequestV2": (
            "pheroos.governance.commit_gate_v2",
            "CommitStopRequestV2",
        ),
        "CommitStopSnapshotV2": (
            "pheroos.governance.commit_gate_v2",
            "CommitStopSnapshotV2",
        ),
        "VerifiedCommitPermissionSourceV2": (
            "pheroos.governance.commit_gate_v2",
            "VerifiedCommitPermissionSourceV2",
        ),
        "VerifiedCommitPermissionStateV2": (
            "pheroos.governance.commit_gate_v2",
            "VerifiedCommitPermissionStateV2",
        ),
        "VerifiedCommitStopSourceV2": (
            "pheroos.governance.commit_gate_v2",
            "VerifiedCommitStopSourceV2",
        ),
        "VerifiedCommitStopStateV2": (
            "pheroos.governance.commit_gate_v2",
            "VerifiedCommitStopStateV2",
        ),
        "commit_gate_candidate_set_root_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_gate_candidate_set_root_v2",
        ),
        "commit_gate_claims_root_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_gate_claims_root_v2",
        ),
        "commit_gate_evaluation_context_root_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_gate_evaluation_context_root_v2",
        ),
        "commit_permission_allows_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_permission_allows_v2",
        ),
        "commit_permission_policy_root_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_permission_policy_root_v2",
        ),
        "commit_permission_state_is_current_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_permission_state_is_current_v2",
        ),
        "commit_permission_stream_ref_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_permission_stream_ref_v2",
        ),
        "commit_permission_transition_id_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_permission_transition_id_v2",
        ),
        "commit_stop_blocks_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_stop_blocks_v2",
        ),
        "commit_stop_policy_root_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_stop_policy_root_v2",
        ),
        "commit_stop_reasons_root_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_stop_reasons_root_v2",
        ),
        "commit_stop_state_is_current_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_stop_state_is_current_v2",
        ),
        "commit_stop_stream_ref_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_stop_stream_ref_v2",
        ),
        "commit_stop_transition_id_v2": (
            "pheroos.governance.commit_gate_v2",
            "commit_stop_transition_id_v2",
        ),
        "issue_commit_permission_v2": (
            "pheroos.governance.commit_gate_v2",
            "issue_commit_permission_v2",
        ),
        "open_commit_permission_authority_session_v2": (
            "pheroos.governance.commit_gate_v2",
            "open_commit_permission_authority_session_v2",
        ),
        "open_commit_stop_authority_session_v2": (
            "pheroos.governance.commit_gate_v2",
            "open_commit_stop_authority_session_v2",
        ),
        "prepare_commit_permission_issue_v2": (
            "pheroos.governance.commit_gate_v2",
            "prepare_commit_permission_issue_v2",
        ),
        "prepare_commit_stop_resolution_v2": (
            "pheroos.governance.commit_gate_v2",
            "prepare_commit_stop_resolution_v2",
        ),
        "rehydrate_commit_permission_state_v2": (
            "pheroos.governance.commit_gate_v2",
            "rehydrate_commit_permission_state_v2",
        ),
        "rehydrate_commit_stop_state_v2": (
            "pheroos.governance.commit_gate_v2",
            "rehydrate_commit_stop_state_v2",
        ),
        "require_current_commit_permission_state_v2": (
            "pheroos.governance.commit_gate_v2",
            "require_current_commit_permission_state_v2",
        ),
        "require_current_commit_stop_state_v2": (
            "pheroos.governance.commit_gate_v2",
            "require_current_commit_stop_state_v2",
        ),
        "resolve_commit_stop_v2": (
            "pheroos.governance.commit_gate_v2",
            "resolve_commit_stop_v2",
        ),
        "verify_commit_permission_request_source_v2": (
            "pheroos.governance.commit_gate_v2",
            "verify_commit_permission_request_source_v2",
        ),
        "verify_commit_stop_request_source_v2": (
            "pheroos.governance.commit_gate_v2",
            "verify_commit_stop_request_source_v2",
        ),
        "COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2",
        ),
        "COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2",
        ),
        "COMMIT_EVIDENCE_POLICY_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_POLICY_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_RECORD_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_RECORD_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2",
        ),
        "COMMIT_EVIDENCE_STATE_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COMMIT_EVIDENCE_STATE_SCHEMA_V2",
        ),
        "COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2": (
            "pheroos.governance.commit_evidence_v2",
            "COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2",
        ),
        "ChallengeResultV2": (
            "pheroos.governance.commit_evidence_v2",
            "ChallengeResultV2",
        ),
        "CommitEvidenceAdvanceRequestV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceAdvanceRequestV2",
        ),
        "CommitEvidenceAttestationV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceAttestationV2",
        ),
        "CommitEvidenceDispositionV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceDispositionV2",
        ),
        "CommitEvidenceEvaluationV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceEvaluationV2",
        ),
        "CommitEvidenceKindV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceKindV2",
        ),
        "CommitEvidencePolicySnapshotV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidencePolicySnapshotV2",
        ),
        "CommitEvidenceProjectionV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceProjectionV2",
        ),
        "CommitEvidenceRevocationV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceRevocationV2",
        ),
        "CommitEvidenceSnapshotV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceSnapshotV2",
        ),
        "CommitEvidenceStatusV2": (
            "pheroos.governance.commit_evidence_v2",
            "CommitEvidenceStatusV2",
        ),
        "CounterevidenceDispositionProposalV2": (
            "pheroos.governance.commit_evidence_v2",
            "CounterevidenceDispositionProposalV2",
        ),
        "QualifiedCommitEvidenceV2": (
            "pheroos.governance.commit_evidence_v2",
            "QualifiedCommitEvidenceV2",
        ),
        "VerifiedCommitEvidenceSourceV2": (
            "pheroos.governance.commit_evidence_v2",
            "VerifiedCommitEvidenceSourceV2",
        ),
        "VerifiedCommitEvidenceStateV2": (
            "pheroos.governance.commit_evidence_v2",
            "VerifiedCommitEvidenceStateV2",
        ),
        "active_qualified_evidence_v2": (
            "pheroos.governance.commit_evidence_v2",
            "active_qualified_evidence_v2",
        ),
        "advance_commit_evidence_state_v2": (
            "pheroos.governance.commit_evidence_v2",
            "advance_commit_evidence_state_v2",
        ),
        "commit_evidence_history_advance_v2": (
            "pheroos.governance.commit_evidence_v2",
            "commit_evidence_history_advance_v2",
        ),
        "commit_evidence_replay_receipts_for_proposals_v2": (
            "pheroos.governance.commit_evidence_v2",
            "commit_evidence_replay_receipts_for_proposals_v2",
        ),
        "commit_evidence_state_is_current_v2": (
            "pheroos.governance.commit_evidence_v2",
            "commit_evidence_state_is_current_v2",
        ),
        "commit_evidence_stream_ref_v2": (
            "pheroos.governance.commit_evidence_v2",
            "commit_evidence_stream_ref_v2",
        ),
        "commit_evidence_transition_id_v2": (
            "pheroos.governance.commit_evidence_v2",
            "commit_evidence_transition_id_v2",
        ),
        "evaluate_commit_evidence_projection_v2": (
            "pheroos.governance.commit_evidence_v2",
            "evaluate_commit_evidence_projection_v2",
        ),
        "open_commit_evidence_authority_session_v2": (
            "pheroos.governance.commit_evidence_v2",
            "open_commit_evidence_authority_session_v2",
        ),
        "prepare_commit_evidence_advance_v2": (
            "pheroos.governance.commit_evidence_v2",
            "prepare_commit_evidence_advance_v2",
        ),
        "project_current_commit_evidence_v2": (
            "pheroos.governance.commit_evidence_v2",
            "project_current_commit_evidence_v2",
        ),
        "rehydrate_commit_evidence_state_v2": (
            "pheroos.governance.commit_evidence_v2",
            "rehydrate_commit_evidence_state_v2",
        ),
        "require_current_commit_evidence_state_v2": (
            "pheroos.governance.commit_evidence_v2",
            "require_current_commit_evidence_state_v2",
        ),
        "verify_commit_evidence_request_source_v2": (
            "pheroos.governance.commit_evidence_v2",
            "verify_commit_evidence_request_source_v2",
        ),
        "COMMIT_FINALITY_INPUT_SCHEMA_V2": (
            "pheroos.governance.commit_finality_v2",
            "COMMIT_FINALITY_INPUT_SCHEMA_V2",
        ),
        "COMMIT_FINALITY_PROJECTION_SCHEMA_V2": (
            "pheroos.governance.commit_finality_v2",
            "COMMIT_FINALITY_PROJECTION_SCHEMA_V2",
        ),
        "CommitFinalityOwnerV2": (
            "pheroos.governance.commit_finality_v2",
            "CommitFinalityOwnerV2",
        ),
        "CommitFinalityProjectionV2": (
            "pheroos.governance.commit_finality_v2",
            "CommitFinalityProjectionV2",
        ),
        "CommitFinalityStatusV2": (
            "pheroos.governance.commit_finality_v2",
            "CommitFinalityStatusV2",
        ),
        "VerifiedCommitFinalityInputV2": (
            "pheroos.governance.commit_finality_v2",
            "VerifiedCommitFinalityInputV2",
        ),
        "commit_finality_owner_genesis_snapshot_root_v2": (
            "pheroos.governance.commit_finality_v2",
            "commit_finality_owner_genesis_snapshot_root_v2",
        ),
        "commit_finality_owner_stream_ref_v2": (
            "pheroos.governance.commit_finality_v2",
            "commit_finality_owner_stream_ref_v2",
        ),
        "COMMIT_DECISION_ASSESSMENT_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_ASSESSMENT_SCHEMA_V2",
        ),
        "COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2",
        ),
        "COMMIT_DECISION_CANONICAL_VERSION_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_CANONICAL_VERSION_V2",
        ),
        "COMMIT_DECISION_DEPENDENCY_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_DEPENDENCY_SCHEMA_V2",
        ),
        "COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2",
        ),
        "COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2",
        ),
        "COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "COMMIT_DECISION_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_GENESIS_TRANSITION_ID_V2",
        ),
        "COMMIT_DECISION_OUTCOME_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_OUTCOME_SCHEMA_V2",
        ),
        "COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2",
        ),
        "COMMIT_DECISION_PROGRESS_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_PROGRESS_SCHEMA_V2",
        ),
        "COMMIT_DECISION_REQUEST_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_REQUEST_SCHEMA_V2",
        ),
        "COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2",
        ),
        "COMMIT_DECISION_SEAL_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_SEAL_SCHEMA_V2",
        ),
        "COMMIT_DECISION_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_SNAPSHOT_SCHEMA_V2",
        ),
        "COMMIT_DECISION_STATE_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_STATE_SCHEMA_V2",
        ),
        "COMMIT_DECISION_WINDOW_SCHEMA_V2": (
            "pheroos.governance.commit_decision_v2",
            "COMMIT_DECISION_WINDOW_SCHEMA_V2",
        ),
        "MAX_COMMIT_DECISION_ITEMS_V2": (
            "pheroos.governance.commit_decision_v2",
            "MAX_COMMIT_DECISION_ITEMS_V2",
        ),
        "MAX_COMMIT_DECISION_RESOURCE_DEPTH_V2": (
            "pheroos.governance.commit_decision_v2",
            "MAX_COMMIT_DECISION_RESOURCE_DEPTH_V2",
        ),
        "MAX_COMMIT_DECISION_RESOURCE_NODES_V2": (
            "pheroos.governance.commit_decision_v2",
            "MAX_COMMIT_DECISION_RESOURCE_NODES_V2",
        ),
        "MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2": (
            "pheroos.governance.commit_decision_v2",
            "MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2",
        ),
        "MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2": (
            "pheroos.governance.commit_decision_v2",
            "MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2",
        ),
        "MAX_COMMIT_DECISION_TEXT_BYTES_V2": (
            "pheroos.governance.commit_decision_v2",
            "MAX_COMMIT_DECISION_TEXT_BYTES_V2",
        ),
        "CommitAssessmentV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitAssessmentV2",
        ),
        "CommitCandidateMetricsV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitCandidateMetricsV2",
        ),
        "CommitDecisionCandidateProposalV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionCandidateProposalV2",
        ),
        "CommitDecisionCommandV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionCommandV2",
        ),
        "CommitDecisionDependencyRoleV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionDependencyRoleV2",
        ),
        "CommitDecisionDependencyV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionDependencyV2",
        ),
        "CommitDecisionEvidenceProposalV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionEvidenceProposalV2",
        ),
        "CommitDecisionGateStatusV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionGateStatusV2",
        ),
        "CommitDecisionMutationKindV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionMutationKindV2",
        ),
        "CommitDecisionOutcomeKindV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionOutcomeKindV2",
        ),
        "CommitDecisionOutcomeV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionOutcomeV2",
        ),
        "CommitDecisionOutputProposalV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionOutputProposalV2",
        ),
        "CommitDecisionPhaseV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionPhaseV2",
        ),
        "CommitDecisionProgressV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionProgressV2",
        ),
        "CommitDecisionRequestV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionRequestV2",
        ),
        "CommitDecisionSealInclusionV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionSealInclusionV2",
        ),
        "CommitDecisionSnapshotV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionSnapshotV2",
        ),
        "CommitDecisionWindowSealV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionWindowSealV2",
        ),
        "CommitDecisionWindowV2": (
            "pheroos.governance.commit_decision_v2",
            "CommitDecisionWindowV2",
        ),
        "VerifiedCommitDecisionSourceV2": (
            "pheroos.governance.commit_decision_v2",
            "VerifiedCommitDecisionSourceV2",
        ),
        "VerifiedCommitDecisionStateV2": (
            "pheroos.governance.commit_decision_v2",
            "VerifiedCommitDecisionStateV2",
        ),
        "advance_commit_decision_v2": (
            "pheroos.governance.commit_decision_v2",
            "advance_commit_decision_v2",
        ),
        "canonical_candidate_proposals_v2": (
            "pheroos.governance.commit_decision_v2",
            "canonical_candidate_proposals_v2",
        ),
        "canonical_commit_decision_dependencies_v2": (
            "pheroos.governance.commit_decision_v2",
            "canonical_commit_decision_dependencies_v2",
        ),
        "commit_decision_dependency_set_root_v2": (
            "pheroos.governance.commit_decision_v2",
            "commit_decision_dependency_set_root_v2",
        ),
        "commit_decision_frozen_dependency_root_v2": (
            "pheroos.governance.commit_decision_v2",
            "commit_decision_frozen_dependency_root_v2",
        ),
        "commit_decision_history_advance_v2": (
            "pheroos.governance.commit_decision_v2",
            "commit_decision_history_advance_v2",
        ),
        "commit_decision_state_is_current_v2": (
            "pheroos.governance.commit_decision_v2",
            "commit_decision_state_is_current_v2",
        ),
        "commit_decision_stream_ref_v2": (
            "pheroos.governance.commit_decision_v2",
            "commit_decision_stream_ref_v2",
        ),
        "commit_decision_transition_id_v2": (
            "pheroos.governance.commit_decision_v2",
            "commit_decision_transition_id_v2",
        ),
        "open_commit_decision_authority_session_v2": (
            "pheroos.governance.commit_decision_v2",
            "open_commit_decision_authority_session_v2",
        ),
        "prepare_commit_decision_initialize_v2": (
            "pheroos.governance.commit_decision_v2",
            "prepare_commit_decision_initialize_v2",
        ),
        "prepare_commit_decision_missing_inputs_v2": (
            "pheroos.governance.commit_decision_v2",
            "prepare_commit_decision_missing_inputs_v2",
        ),
        "prepare_commit_decision_successor_v2": (
            "pheroos.governance.commit_decision_v2",
            "prepare_commit_decision_successor_v2",
        ),
        "reduce_commit_decision_v2": (
            "pheroos.governance.commit_decision_v2",
            "reduce_commit_decision_v2",
        ),
        "rehydrate_commit_decision_state_v2": (
            "pheroos.governance.commit_decision_v2",
            "rehydrate_commit_decision_state_v2",
        ),
        "require_current_commit_decision_state_v2": (
            "pheroos.governance.commit_decision_v2",
            "require_current_commit_decision_state_v2",
        ),
        "verify_commit_decision_request_source_v2": (
            "pheroos.governance.commit_decision_v2",
            "verify_commit_decision_request_source_v2",
        ),
        "COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2",
        ),
        "COMMIT_CERTIFICATE_BODY_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_BODY_SCHEMA_V2",
        ),
        "COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2",
        ),
        "COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2",
        ),
        "COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2",
        ),
        "COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2",
        ),
        "COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_IDENTITY_BINDING_SCHEMA_V2",
        ),
        "COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_REQUEST_SCHEMA_V2",
        ),
        "COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_SNAPSHOT_SCHEMA_V2",
        ),
        "COMMIT_CERTIFICATE_STATE_SCHEMA_V2": (
            "pheroos.governance.commit_certificate_v2",
            "COMMIT_CERTIFICATE_STATE_SCHEMA_V2",
        ),
        "CommitCertificateAuthorityLeafV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateAuthorityLeafV2",
        ),
        "CommitCertificateAuthorityRoleV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateAuthorityRoleV2",
        ),
        "CommitCertificateBodyV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateBodyV2",
        ),
        "CommitCertificateIdentityBindingV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateIdentityBindingV2",
        ),
        "CommitCertificateIssuerAttestationVerifierV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateIssuerAttestationVerifierV2",
        ),
        "CommitCertificateMutationKindV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateMutationKindV2",
        ),
        "CommitCertificateRequestV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateRequestV2",
        ),
        "CommitCertificateSnapshotV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateSnapshotV2",
        ),
        "CommitCertificateStatusV2": (
            "pheroos.governance.commit_certificate_v2",
            "CommitCertificateStatusV2",
        ),
        "PortableCommitCertificateV2": (
            "pheroos.governance.commit_certificate_v2",
            "PortableCommitCertificateV2",
        ),
        "VerifiedCommitCertificateSourceV2": (
            "pheroos.governance.commit_certificate_v2",
            "VerifiedCommitCertificateSourceV2",
        ),
        "VerifiedCommitCertificateStateV2": (
            "pheroos.governance.commit_certificate_v2",
            "VerifiedCommitCertificateStateV2",
        ),
        "advance_commit_certificate_v2": (
            "pheroos.governance.commit_certificate_v2",
            "advance_commit_certificate_v2",
        ),
        "canonical_commit_certificate_authority_leaves_v2": (
            "pheroos.governance.commit_certificate_v2",
            "canonical_commit_certificate_authority_leaves_v2",
        ),
        "commit_certificate_authority_leaf_set_root_v2": (
            "pheroos.governance.commit_certificate_v2",
            "commit_certificate_authority_leaf_set_root_v2",
        ),
        "commit_certificate_state_is_current_v2": (
            "pheroos.governance.commit_certificate_v2",
            "commit_certificate_state_is_current_v2",
        ),
        "commit_certificate_stream_ref_v2": (
            "pheroos.governance.commit_certificate_v2",
            "commit_certificate_stream_ref_v2",
        ),
        "commit_certificate_transition_id_v2": (
            "pheroos.governance.commit_certificate_v2",
            "commit_certificate_transition_id_v2",
        ),
        "open_commit_certificate_authority_session_v2": (
            "pheroos.governance.commit_certificate_v2",
            "open_commit_certificate_authority_session_v2",
        ),
        "prepare_commit_certificate_v2": (
            "pheroos.governance.commit_certificate_v2",
            "prepare_commit_certificate_v2",
        ),
        "rehydrate_commit_certificate_state_v2": (
            "pheroos.governance.commit_certificate_v2",
            "rehydrate_commit_certificate_state_v2",
        ),
        "require_current_commit_certificate_state_v2": (
            "pheroos.governance.commit_certificate_v2",
            "require_current_commit_certificate_state_v2",
        ),
        "verified_commit_certificate_finality_input_v2": (
            "pheroos.governance.commit_certificate_v2",
            "verified_commit_certificate_finality_input_v2",
        ),
        "verify_portable_commit_certificate_v2": (
            "pheroos.governance.commit_certificate_v2",
            "verify_portable_commit_certificate_v2",
        ),
        "DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2",
        ),
        "DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2",
        ),
        "DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2",
        ),
        "DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2",
        ),
        "DISTRIBUTED_DEPENDENCY_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_DEPENDENCY_SCHEMA_V2",
        ),
        "DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_EPOCH_TRANSITION_CERTIFICATE_SCHEMA_V2",
        ),
        "DISTRIBUTED_GENESIS_TRANSITION_ID_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_GENESIS_TRANSITION_ID_V2",
        ),
        "DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2",
        ),
        "DISTRIBUTED_LANE_STATE_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_LANE_STATE_SCHEMA_V2",
        ),
        "DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2",
        ),
        "DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2": (
            "pheroos.governance.distributed_commit_v2",
            "DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2",
        ),
        "DistributedAdvanceRequestV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedAdvanceRequestV2",
        ),
        "DistributedCertificateStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedCertificateStateV2",
        ),
        "DistributedCertificateStatusV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedCertificateStatusV2",
        ),
        "DistributedCommitCertificateV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedCommitCertificateV2",
        ),
        "DistributedCommitProposalV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedCommitProposalV2",
        ),
        "DistributedCommitValueV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedCommitValueV2",
        ),
        "DistributedDependencyRoleV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedDependencyRoleV2",
        ),
        "DistributedDependencyV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedDependencyV2",
        ),
        "DistributedEpochStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedEpochStateV2",
        ),
        "DistributedEpochTransitionCertificateV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedEpochTransitionCertificateV2",
        ),
        "DistributedEquivocationFindingV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedEquivocationFindingV2",
        ),
        "DistributedLaneSnapshotV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedLaneSnapshotV2",
        ),
        "DistributedLaneStatusV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedLaneStatusV2",
        ),
        "DistributedLaneV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedLaneV2",
        ),
        "DistributedMutationKindV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedMutationKindV2",
        ),
        "DistributedPolicyBindingV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedPolicyBindingV2",
        ),
        "DistributedProposalStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedProposalStateV2",
        ),
        "DistributedQuorumWitnessV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedQuorumWitnessV2",
        ),
        "DistributedWitnessAttestationVerifierV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedWitnessAttestationVerifierV2",
        ),
        "DistributedWitnessConflictObservationV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedWitnessConflictObservationV2",
        ),
        "DistributedWitnessStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "DistributedWitnessStateV2",
        ),
        "VerifiedDistributedAdvanceSourceV2": (
            "pheroos.governance.distributed_commit_v2",
            "VerifiedDistributedAdvanceSourceV2",
        ),
        "VerifiedDistributedCertificateStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "VerifiedDistributedCertificateStateV2",
        ),
        "VerifiedDistributedEpochStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "VerifiedDistributedEpochStateV2",
        ),
        "VerifiedDistributedProposalStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "VerifiedDistributedProposalStateV2",
        ),
        "VerifiedDistributedStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "VerifiedDistributedStateV2",
        ),
        "VerifiedDistributedWitnessStateV2": (
            "pheroos.governance.distributed_commit_v2",
            "VerifiedDistributedWitnessStateV2",
        ),
        "advance_distributed_commit_v2": (
            "pheroos.governance.distributed_commit_v2",
            "advance_distributed_commit_v2",
        ),
        "canonical_distributed_dependencies_v2": (
            "pheroos.governance.distributed_commit_v2",
            "canonical_distributed_dependencies_v2",
        ),
        "distributed_dependency_set_root_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_dependency_set_root_v2",
        ),
        "distributed_genesis_history_root_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_genesis_history_root_v2",
        ),
        "distributed_genesis_snapshot_root_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_genesis_snapshot_root_v2",
        ),
        "distributed_lane_stream_ref_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_lane_stream_ref_v2",
        ),
        "distributed_lane_transition_id_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_lane_transition_id_v2",
        ),
        "distributed_policy_binding_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_policy_binding_v2",
        ),
        "distributed_state_is_current_v2": (
            "pheroos.governance.distributed_commit_v2",
            "distributed_state_is_current_v2",
        ),
        "open_distributed_authority_session_v2": (
            "pheroos.governance.distributed_commit_v2",
            "open_distributed_authority_session_v2",
        ),
        "prepare_distributed_certificate_v2": (
            "pheroos.governance.distributed_commit_v2",
            "prepare_distributed_certificate_v2",
        ),
        "prepare_distributed_epoch_v2": (
            "pheroos.governance.distributed_commit_v2",
            "prepare_distributed_epoch_v2",
        ),
        "prepare_distributed_proposal_v2": (
            "pheroos.governance.distributed_commit_v2",
            "prepare_distributed_proposal_v2",
        ),
        "prepare_distributed_witness_conflict_observation_v2": (
            "pheroos.governance.distributed_commit_v2",
            "prepare_distributed_witness_conflict_observation_v2",
        ),
        "prepare_distributed_witness_v2": (
            "pheroos.governance.distributed_commit_v2",
            "prepare_distributed_witness_v2",
        ),
        "rehydrate_distributed_state_v2": (
            "pheroos.governance.distributed_commit_v2",
            "rehydrate_distributed_state_v2",
        ),
        "require_current_distributed_state_v2": (
            "pheroos.governance.distributed_commit_v2",
            "require_current_distributed_state_v2",
        ),
        "validate_distributed_membership_v2": (
            "pheroos.governance.distributed_commit_v2",
            "validate_distributed_membership_v2",
        ),
        "verified_distributed_commit_finality_input_v2": (
            "pheroos.governance.distributed_commit_v2",
            "verified_distributed_commit_finality_input_v2",
        ),
        "verify_distributed_witness_v2": (
            "pheroos.governance.distributed_commit_v2",
            "verify_distributed_witness_v2",
        ),
        "recover_baseline_output_result_v2": (
            "pheroos.governance.baseline_output_v2",
            "recover_baseline_output_result_v2",
        ),
        "evaluate_and_commit_governed_baseline_output_v2": (
            "pheroos.governance.baseline_output_v2",
            "evaluate_and_commit_governed_baseline_output_v2",
        ),
    }
)
COMPATIBILITY_MODULES = MappingProxyType(
    {
        "attention": "pheroos.governance.attention",
        "atomic_evaluation": "pheroos.governance.atomic_evaluation",
        "authority": "pheroos.governance.authority",
        "authority_domain": "pheroos.governance.authority_domain",
        "authority_session_v2": "pheroos.governance.authority_session_v2",
        "authority_store_v2": "pheroos.governance.authority_store_v2",
        "baseline_output_v2": "pheroos.governance.baseline_output_v2",
        "candidate": "pheroos.governance.candidate",
        "certificate": "pheroos.governance.certificate",
        "challenge": "pheroos.governance.challenge",
        "collective": "pheroos.governance.collective",
        "commit": "pheroos.governance.commit",
        "commit_semantics": "pheroos.governance.commit_semantics",
        "commit_numeric": "pheroos.governance.commit_numeric",
        "commit_certificate_v2": "pheroos.governance.commit_certificate_v2",
        "commit_decision_v2": "pheroos.governance.commit_decision_v2",
        "commit_evidence_v2": "pheroos.governance.commit_evidence_v2",
        "commit_finality_v2": "pheroos.governance.commit_finality_v2",
        "commit_gate_v2": "pheroos.governance.commit_gate_v2",
        "commit_state": "pheroos.governance.commit_state",
        "commit_state_v2": "pheroos.governance.commit_state_v2",
        "distributed_commit": "pheroos.governance.distributed_commit",
        "distributed_commit_v2": "pheroos.governance.distributed_commit_v2",
        "errors": "pheroos.governance.errors",
        "evidence": "pheroos.governance.evidence",
        "evidence_binding": "pheroos.governance.evidence_binding",
        "historical_certificate": "pheroos.governance.historical_certificate",
        "hybrid_commit": "pheroos.governance.hybrid_commit",
        "hybrid_commit_evaluation": "pheroos.governance.hybrid_commit_evaluation",
        "hybrid_replay_v2": "pheroos.governance.hybrid_replay_v2",
        "layer_coordination": "pheroos.governance.layer_coordination",
        "observation": "pheroos.governance.observation",
        "output": "pheroos.governance.output",
        "permission": "pheroos.governance.permission",
        "pheromone": "pheroos.governance.pheromone",
        "pheromone_feedback": "pheroos.governance.pheromone_feedback",
        "policy_adjustment": "pheroos.governance.policy_adjustment",
        "principal": "pheroos.governance.principal",
        "quorum": "pheroos.governance.quorum",
        "recovery": "pheroos.governance.recovery",
        "replay": "pheroos.governance.replay",
        "risk": "pheroos.governance.risk",
        "risk_v2": "pheroos.governance.risk_v2",
        "runtime_policy": "pheroos.governance.runtime_policy",
        "schema": "pheroos.governance.schema",
        "signal": "pheroos.governance.signal",
        "stop_signal": "pheroos.governance.stop_signal",
        "support_lease": "pheroos.governance.support_lease",
        "support_v2": "pheroos.governance.support_v2",
        "target": "pheroos.governance.target",
        "trace": "pheroos.governance.trace",
    }
)


__all__ = ["COMPATIBILITY_MODULES", "PUBLIC_API", "PUBLIC_API_ORDER_SHA256"]
