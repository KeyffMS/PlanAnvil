# Goal analysis

## Requested outcome

Replace a single status column with a status-history model without downtime.

## Repository evidence

The fixture records the affected components and quality gates.

## Change classification and risk

STATEFUL.

## Affected paths and boundaries

Only stage allowlists may be modified by the later executor.

## Assumptions

The fixture evidence is authoritative for this example.

## Unknowns and verification

No critical unknown remains.

## Recommended stage boundaries

Stages are split by independent acceptance and rollback boundaries.
