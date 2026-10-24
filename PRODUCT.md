# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated: standard-library Python (`http.server`) with vanilla HTML/CSS/JS, SQLite by default and Tiger Cloud / TimescaleDB when `DATABASE_URL` is set. Judgement comes from an open-weight model (`qwen/qwen3.8-27b`) over an OpenAI-compatible API, with a deterministic rules floor when no key is configured. Chosen for a one-day build because zero-install serving is part of the open-source argument.

## Users

The primary user is the builder themself: a solo developer shipping a series of Hacktoberfest projects who wants proof of which automations actually gave time back. They use it at a laptop, at the end of a working session, entering chores from memory. Secondary audience (not designed for yet): solo builders and freelancers who automate things and cannot say whether it paid off.

## Product Purpose

Sloth Ledger records how much manual time a chore cost, judges whether it is worth automating, and books the minutes back when an automation actually runs. Success means the user can answer "what did this save me?" with a number they can defend, per automation and per week, instead of a feeling.

## Positioning

The model gives the judgement; the database gives the arithmetic. Every figure in the ledger carries the evidence that produced it (count × per-item rate, a hand measurement, or a labelled model estimate), and totals come from SQL. A ledger built on a cloud chatbot cannot make that claim, because the same system would be inventing both the opinion and the number.

## Operating Context

Runs locally from `python app.py` with no build step. With no key it answers on the deterministic rules floor; with `MODEL_*` set it asks an open-weight model over an OpenAI-compatible API. Further lanes: a Tiger Cloud Postgres/TimescaleDB instance for storage. The demo corpus is a labelled synthetic freelancer season, entered by hand; any fictional persona data must be labelled as such.

## Capabilities and Constraints

Confirmed: describe a chore in plain English; optional hand-measured minutes; verdict of automate / delegate / ignore forever; run an automation once per chore and book its minutes; weekly, all-time and still-manual totals; fourteen-day daily rollup; ledger history. Numbers are reconciled deterministically (count × rate wins; a stated measurement wins; the model's estimate only stands when nothing is countable). Python 3.11+ standard library, `pg8000` only for the Postgres lane. Undecided: user accounts, multi-user, edit/delete of past entries, exports.

## Brand Commitments

Name: Sloth Ledger. Voice: dry, plain, accountable; never cute about the sloth. The product must not claim savings it cannot show.

## Evidence on Hand

The user's own Week 1 and Week 2 Hacktoberfest work (repo `UdhaarBook`) as candidate real entries. No user testimonials, no benchmarks, no usage statistics. Demo data beyond the user's own entries must be labelled synthetic.

## Product Principles

1. A number without evidence is a rumour; show the arithmetic beside the figure.
2. Never let the model do arithmetic that the ledger can do.
3. Laziness is a design goal, not a joke: the shortest path from chore to verdict.
4. Offline is a feature, not a limitation to apologise for.
5. Ignoring a chore is a valid, recorded outcome.

## Accessibility & Inclusion

Keyboard-complete operation, visible focus, 44px minimum targets, AA contrast on the ledger ground, reduced-motion honoured, and a screen-reader-only column header set on the ledger table.
