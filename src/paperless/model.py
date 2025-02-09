"""Configuration model."""

import os

import pulumi as p
import pydantic
import pydantic.alias_generators


class ConfigBaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=lambda s: s.replace('_', '-'),
        populate_by_name=True,
        extra='forbid',
    )


class EnvVarRef(ConfigBaseModel):
    envvar: str

    @property
    def value(self) -> p.Output[str]:
        return p.Output.secret(os.environ[self.envvar])


class UnifyConfig(ConfigBaseModel):
    url: pydantic.HttpUrl = pydantic.HttpUrl('https://unifi/')
    verify_ssl: bool = False


class PaperlessConfig(ConfigBaseModel):
    pass


class ServiceConfig(ConfigBaseModel):
    domain_name: str


class ComponentConfig(ConfigBaseModel):
    service: ServiceConfig
    paperless: PaperlessConfig
    unify: UnifyConfig
