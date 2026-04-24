# Network Configuration Builder

This project started in November 2025, driven by concrete customer requirements: generate complete, deterministic network device configurations (including underlay and overlay services) from a persisted topology.

Nothing less. Nothing more.

The goal is not orchestration but compilation: transforming validated topology and service intent into vendor-specific device configurations in a reproducible and explainable way.

This project is also a personal exploration of modern design patterns and architectural principles, applied pragmatically through “learning by doing”.

Hans Verkerk  
April 2026


## What it does

- Persists network topology (devices, interfaces, links) sourced from an  Excel document. In /app an example file is included.
- Accepts service, protocol and addressing intent defined in YAML
- Computes complete, vendor-agnostic configuration intent
- Renders vendor-specific device configurations using Jinja2 templates

## What it does *not* do

- No configuration deployment or execution
- No attempt to be a full CMDB or inventory system

This tool assumes that topology and intent are the source of truth
and treats configuration generation as a compile-time operation.

## Typical Workflow

1. Create or update persisted network topology by modifying the Excel document
2. Insert resource pools. These are defined in the Excel document and added to the DB.
2. Define services and addressing policies using YAML specifications. 
3. Compile topology and intent into device-scoped configuration data
4. Render complete device configurations using vendor templates

## Design principles

- Topology-first: all computation derives from persisted topology
- Deterministic execution: identical inputs produce identical outputs
- Idempotency: recomputation is always safe
- Clear separation of concerns:
  - topology storage
  - intent computation
  - rendering
- Vendor-agnostic computation with vendor-specific rendering

## Intended use

The Network Configuration Builder is designed for:

- Greenfield environments without an established CMDB
- Engineers who need reproducible, explainable configurations
- Incremental adoption without requiring a large operational platform

It is deliberately lightweight and focused.

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [Adding a new service](docs/ADDING_A_NEW_SERVICE.md)