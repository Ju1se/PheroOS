# Swarm Protocol Example

This example is provider-free, network-free, and deterministic. It demonstrates a declared collective decision policy, independent scout reports, recruitment and inhibition signals, evidence-bound pheromone memory, pheromone evaporation, a declared safe fallback candidate, output authorization requirements, and swarm trace events.

The pheromone fields model stigmergic memory as a traceable, decaying score signal. Pheromone trails can attach to uniform subjects, are bounded by source and deposit caps, and use deterministic exponential decay by default. Pheromone trails do not create evidence, commit candidates, or authorize output.
