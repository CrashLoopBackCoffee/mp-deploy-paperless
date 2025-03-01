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


class PaperlessConfig(ConfigBaseModel):
    version: str
    port: pydantic.PositiveInt = 8000
    data_size_gb: pydantic.PositiveInt
    media_size_gb: pydantic.PositiveInt


class RedisConfig(ConfigBaseModel):
    version: str
    port: pydantic.PositiveInt = 6379


class EntraIdConfig(ConfigBaseModel):
    tenant_id: str = '19d0fb13-2d87-4699-9ae2-6e431148a6ae'
    client_id: str
    client_secret: str


class ComponentConfig(ConfigBaseModel):
    paperless: PaperlessConfig
    redis: RedisConfig
    entraid: EntraIdConfig
