---
version: 1
created: 2026-02-26T10:00:00+00:00
author: human:marianne
status: active
---

# Intent: Expense Tracker

## WANT
- CRUD operations for expenses (add, list, update, delete)
- Summary with totals by category and month

## DON'T
- No external dependencies
- No database — in-memory only

## LIKE
- Stripe's API design (clean, predictable method signatures)

## FOR
- Personal finance prototype
- Single user, runs locally

## ENSURE
- Negative amounts throw an error
- Future dates throw an error
- Categories are case-insensitive

## TRUST
- [autonomous] Choose the data structure
- [autonomous] Choose class vs functional style
- [ask] Adding any validation not listed in ENSURE
- [ask] Modifying the public API signature

## Changelog

### v1 — 2026-02-26
Initial spec compiled from conversation.
