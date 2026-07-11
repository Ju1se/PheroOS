from pheroos.governance import LayerProposal, PheromoneFeedback, PheromoneTrail, PolicyAdjustmentProposal
from pheroos.governance.layer_coordination import LayerProposal as ModuleLayerProposal
from pheroos.governance.pheromone import PheromoneTrail as ModulePheromoneTrail
from pheroos.governance.pheromone_feedback import PheromoneFeedback as ModulePheromoneFeedback
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal as ModulePolicyAdjustmentProposal


def test_public_governance_exports_use_cohesive_pheromone_modules() -> None:
    assert PheromoneTrail is ModulePheromoneTrail
    assert PheromoneFeedback is ModulePheromoneFeedback
    assert LayerProposal is ModuleLayerProposal
    assert PolicyAdjustmentProposal is ModulePolicyAdjustmentProposal
