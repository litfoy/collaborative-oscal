# Collaborative OSCAL

Read this README in [German](README.de.md).

Collaborative OSCAL is an open-source project exploring how organizations can
work together on security controls and compliance.

[OSCAL](https://pages.nist.gov/OSCAL/), developed by NIST, provides a
machine-readable way to describe security catalogs, profiles, and assessments.
It gives organizations and tools a shared format for exchanging compliance
information and creates a foundation for reuse and automation.

## What we are building

Our goal is to help people in different roles collaborate on security controls,
reduce duplicated effort, and make compliance work easier to maintain and
eventually automate.

The current proof of concept includes OIDC sign-in, tenant-aware access, a
read-only OSCAL Catalog Explorer, basic Profile authoring, and a
self-reported Control Implementation Register. Catalogs can be imported through
a command-line tool. Catalog editing, Profile resolution, assessments,
workflows, and evidence management are not implemented yet.

## An early proof of concept

This project is not production-ready. Much of the code was created with AI
assistance and has received limited review. It needs further technical and
domain review, as well as operational hardening, before it could be used with
real organizational data.

We welcome contributors, subject-matter experts, and supporters interested in
helping shape an open-source project for collaborative compliance. You can try
the local demo with `docker compose up` and open
[http://localhost:3000](http://localhost:3000). The demo is for local use only:
do not expose it publicly or use it with production data.

Use the header language selector to switch between **English** (default) and
**Deutsch**. The browser remembers your choice; both languages are included in
the same image. Only the interface is translated, never imported OSCAL content
or your authored descriptions.

For setup, development, and technical details, see the
[developer guide](docs/development.md).
