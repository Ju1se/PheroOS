"""Internal wire-version mirrors for the distributed lifecycle engines.

The public ABI constants remain directly declared by
``pheroos.governance.distributed_commit``.  These immutable mirrors let private
owners avoid a dependency back to that aggregate facade.
"""

DISTRIBUTED_PROPOSAL_VERSION = "pheroos-distributed-commit-proposal-v1"
DISTRIBUTED_COMMIT_VALUE_VERSION = "pheroos-distributed-commit-value-v1"
QUORUM_WITNESS_VERSION = "pheroos-quorum-witness-v1"
WITNESS_VERIFICATION_VERSION = "pheroos-witness-verification-v1"
DISTRIBUTED_STATE_VERSION = "pheroos-distributed-commit-state-v1"
DISTRIBUTED_COMMIT_CERTIFICATE_VERSION = "pheroos-distributed-commit-certificate-v1"
EPOCH_TRANSITION_CERTIFICATE_VERSION = "pheroos-epoch-transition-certificate-v1"
DISTRIBUTED_FINALITY_DECISION_VERSION = "pheroos-distributed-finality-decision-v1"
DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR = "distributed_commit_certificate"
EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR = "epoch_transition_certificate"
