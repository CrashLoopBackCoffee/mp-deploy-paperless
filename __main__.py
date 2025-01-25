"""Paperless ng."""

import pulumi as p

from paperless.model import ComponentConfig

component_config = ComponentConfig.model_validate(p.Config().require_object('config'))
