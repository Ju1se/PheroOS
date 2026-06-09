---
name: fastapi-api
description: Use this skill when building, modifying, or reviewing FastAPI REST APIs, request schemas, route handlers, dependency injection, and API tests.
---

# FastAPI API Skill

## Goal

Build maintainable FastAPI endpoints with typed request and response schemas, validation, error handling, and tests.

## Required Workflow

1. Inspect existing route structure before adding new routes.
2. Define Pydantic schemas before implementing handlers.
3. Keep business logic outside route functions.
4. Add tests for success path and failure path.
5. Run the relevant test command before finalizing.

## Output Expectations

- Include changed files.
- Explain the API contract.
- Mention test coverage.
