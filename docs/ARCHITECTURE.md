# Architecture Overview

This document describes the internal architecture of the Network Configuration Builder.

The system is designed to compute complete, deterministic device configurations from a persisted topology.

---

## Core Principles

- Topology-first 
  All computation derives from a persisted topology model (devices, interfaces, links, roles).

- Deterministic computation
  Given the same topology and service definitions, the output is always identical.

- Loose coupling 
  Topology, intent, computation, and rendering are clearly separated.

- Idempotency
  Re-running the same inputs produces the same outputs.

---
## Database model

Module: `app.models`
[View source](../app/models)

The models are used to persist topology and service data.
SQLite was chosen for its lightweight and simple deployment model, while SQLAlchemy provides strong integration with Python and robust type checking support via Pylance.

This combination offers a high degree of control over model design, allowing the data structures to closely reflect the underlying domain and business logic.

---
## Excel data entry

Module: `app.excel_data_handing`
[View source](../app/excel_data_handling)

Responsibilities:
- Load topology: devices, links (optional, can be auto derived), interfaces, roles
- Performs strict input data validation
- Define prefix and resource pools and load them into DB incrementally
- Create DB and Excel snapshots after a topology/service run.

---

## Job Executor and Job handlers

Module: `app.services.job_handling`
[View source](../app/services/job_handling/)

The Job Executor coordinates all work in the system.

Responsibilities:
- The Jobs are implicit defined in the Excel input
- The JobExecutor module provides and injects the database session into dependent components, adhering to the dependency injection (DI) pattern.
- The JobExecutor module also executes the jobs after loading IP addressing policies.
- Specialized Job Handlers maintain idempotency and invoke topology builders
- Apply topology changes incrementally.
- Triggers a full service orchestration run after all jobs have been executed.
---

## Topology Builders

Module: `app.services.service_handling.topology_building`
[View source](../app/services/topology_building/)

Responsible for constructing and modifying the persisted topology model:

- Devices (including roles and metadata such as labels)
- Interfaces and LAGs (parent/member relationships)
- Physical connectivity
- IP address allocation
- Resource allocation (IDs, labels, protocol parameters)

Topology is persisted and serves as the system’s single source of truth.

---

## IP and Resource Allocation

YAML Definitions:
[View source](../app/services/service_handling/addressing_definitions/)


Addressing Policy Resolver: 
[View source](../app/services/service_handling/addressing_policy_resolver.py)

Resource Pool Allocator:
[View source](../app/services/service_handling/resource_pool_allocator.py)

IP addressing and other allocatable resources are handled explicitly and deterministically:
- Interfaces eligible for IP assignment are selected automatically based on topology attributes (e.g. interface role, LAG parent, loopback).
- Address assignment is driven by allocation policies, defined in YAML templates
- Different pools and policies can be applied, for example:
  - by device role (sedge, core, rr, ...)
  
---

## Service Orchestrator

Module: `app.services.service_handling.service_orchestrator`  
[View source](../app/services/service_handling/service_orchestrator.py)

The Service Orchestrator controls execution order:

1. Underlay and Overlay services
2. Basic validation of YAML service definitions
3. Invocation of the Service Builder
---

## Service Builder

Module: `app.services.service_handling.service_builder`  
[View source](../app/services/service_handling/service_builder.py)

The Service Builder is responsible for computing intent-derived data.

Responsibilities:
- Executes the relevant Feature Handlers for a service
- Aggregates their output
- Persists computed results per ServiceInstance in the DB
---

## Feature Handlers

Feature handlers:
[View source](../app/services/service_handling/feature_handlers/)

YAML definitions:
[View source](../app/services/services_definitions/)

Feature Handlers compute protocol- or service-specific intent from topology and YAML defined service definitions.

Characteristics:
- Protocol-aware (deep domain knowledge lives here)
- Deterministic
- Stateless aside from persisted topology and allocations
- Easy to extend or replace

Examples:
- Underlay protocols (IS-IS, BGP, SR)
- Overlay services (EVPN, L2VPN, L3VPN)
- Ring- or role-based reachability
- Service-specific resource allocation

Feature Handlers produce vendor-agnostic, device-scoped intent.

---

## Context Layer

Context layer:
[View source](../app/services/context/)

The Context Layer composes render-ready device contexts by:

- Projecting topology into device/interface render units
- Merging protocol intent into those render units
- Normalizing data for deterministic rendering

---

## Configuration Rendering

Templates:
[View source](../app/services/templates/sros/)

Computed contexts are rendered using Jinja2 templates.

Characteristics:
- Vendor-specific
- Stateless
- No topology or protocol logic

This allows multiple vendors to be supported without changing computation logic.

---

## Printer

Module: `app.printing`  
[View source](../app/printing/printer.py)

Used to output rendered device configurations.

---

## Execution Flow

1. Topology is built or modified and persisted if needed.
2. Job Executor triggers Service Orchestration
3. Service Builder runs Feature Handlers
4. Computed intent is persisted per ServiceInstance
5. Context Layer composes render-ready device contexts
6. Device configurations are rendered

Execution can be performed in 'dry_run' mode. In this mode, any error will trigger a full rollback of all database transactions, ensuring no state is persisted.

In non-dry-run mode, errors also result in a full transaction rollback to prevent inconsistent or stale state.

---

## Scope

The architecture is designed to support:

- Large-scale service provider and data center networks
- Complex topologies (rings, aggregation/distribution layers, multiple fabrics)
- Multiple concurrent services and protocol instances
- Incremental, repeatable, and auditable configuration generation

---

### Final Note

This system is intentionally lightweight and focused:

It computes device configurations from a persisted topology. Nothing less, and nothing more.
