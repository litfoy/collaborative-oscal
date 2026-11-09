# ADR 0001: Start as a modular monolith

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The project is at its foundation stage. Product boundaries and operational load are not yet established, while self-hostability and a low operational burden are core requirements.

## Decision

Deploy the web app, API, and future worker as a modular monolith. Keep domain boundaries explicit in code and documentation. Do not introduce microservices, message brokers, or orchestration infrastructure until a concrete scaling or isolation need warrants them.

## Consequences

The initial system is simpler to develop and self-host. Modules must still avoid coupling their internals, so future extraction remains possible. Deployment scaling and independent release cadence are not provided yet.
