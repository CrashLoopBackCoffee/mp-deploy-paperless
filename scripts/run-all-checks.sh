#!/usr/bin/env bash

set -x
set -eu

uv run ruff format
uv run ruff check --fix
uv run pyright --warnings
