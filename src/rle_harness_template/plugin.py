"""The entry-point object RLE loads (``rle.harnesses`` group, name ``template``)."""

from __future__ import annotations

from pydantic import BaseModel
from rle.harness import Availability, BaseHarness, HarnessContext

from rle_harness_template.harness import TemplateHarness, TemplateOptions


class TemplatePlugin:
    name = "template"
    description = "Template harness: sets one work priority per tick. Copy me."

    def available(self) -> Availability:
        # Probe for binaries / extras here. Must stay cheap and import-free.
        return Availability.available()

    def option_schema(self) -> type[BaseModel]:
        return TemplateOptions

    def create(self, ctx: HarnessContext, options: BaseModel) -> BaseHarness:
        assert isinstance(options, TemplateOptions)
        return TemplateHarness(options)

    def smoke(self, ctx: HarnessContext, options: BaseModel) -> BaseHarness:
        # The smoke variant must run with no external tool or LLM. For a
        # harness that needs one, return a scripted stand-in here.
        assert isinstance(options, TemplateOptions)
        return TemplateHarness(options)

    def describe(self) -> dict[str, str]:
        return {"harness": self.name, "template_version": "0.1.0"}


PLUGIN = TemplatePlugin()
