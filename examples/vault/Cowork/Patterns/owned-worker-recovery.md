---
title: Owned worker crash recovery with persistent pause
type: procedure
status: observed
project: Sample Alpha
applies_when: A local application owns a loopback worker and has explicit persistent pause semantics.
sources: ["Cowork/Projects/sample-alpha.md"]
tags: ["worker", "crash-recovery", "persistent-pause", "cross-project", "synthetic-example"]
---

# Owned worker crash recovery with persistent pause

This synthetic lesson illustrates knowledge transfer from [[Cowork/Projects/sample-alpha]]
to [[Cowork/Projects/sample-beta]]. It is not a real production acceptance record.

Use a supervisor to check the owned worker's health and instance identity, wait
through slow startup, and restart an unexpected exit with backoff. Retain state
outside the process. A saved pause or intentional stop must prevent automatic
restart. Leave foreign listeners alone.

Before reusing this procedure, verify the current application's ownership checks,
platform, launcher behavior and pause contract. In particular, a Windows Python
virtual-environment launcher may own the actual interpreter as a descendant.
Test recovery and state retention in the target application before marking it proven.
