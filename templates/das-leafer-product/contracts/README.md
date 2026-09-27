# Contracts

This directory is the contract hub for API schemas, event schemas, and fixtures.

The generated repository starts with one minimal, valid HFVI interaction-event
schema plus one valid and one invalid fixture. `./scripts/verify-contracts`
checks that bootstrap contract without external dependencies, so the first
clean repository is verifiable. Replace or extend it with the project's real
contracts in the first change; do not weaken the valid/invalid fixture gate.
