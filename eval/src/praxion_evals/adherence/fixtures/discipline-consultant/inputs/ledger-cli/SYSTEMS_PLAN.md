# Plan: the draft under challenge

## Goal

Extend a small command-line bookkeeping tool with a richer record model.

## Architecture

### Data Structures

A record is a dictionary with optional keys, validated where it is used. A change event carries a payload whose fields depend on the kind of change. Failure is reported with return codes in some places and exceptions in others. All records live in one JSON list.
