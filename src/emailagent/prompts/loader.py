"""Strict, manifest-driven prompt loading with hashes of all transitive includes."""
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, meta
from pydantic import BaseModel, ConfigDict, Field

from src.emailagent.ports.llm import PromptTrace

PROMPTS_RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources" / "prompts"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class PromptVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str
    task: str | None = None
    output_schema_version: str
    description: str


class PromptManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    current_version: str
    versions: dict[str, PromptVersion]
    targets: dict[str, float] = Field(default_factory=dict)


class PromptLoader:
    def __init__(self, resource_dir: Path = PROMPTS_RESOURCE_DIR):
        self.resource_dir = resource_dir.resolve()
        self.env = Environment(
            loader=FileSystemLoader(str(self.resource_dir)), undefined=StrictUndefined,
            # Dynamic data is JSON-serialized by builders/gateways, never interpolated into XML.
            autoescape=False, trim_blocks=True, lstrip_blocks=True,
        )

    def manifest(self, domain: str) -> PromptManifest:
        if not _IDENTIFIER.fullmatch(domain):
            raise ValueError("Invalid prompt domain")
        manifest = PromptManifest.model_validate(yaml.safe_load(
            (self.resource_dir / domain / "metadata.yaml").read_text(encoding="utf-8")
        ))
        if manifest.domain != domain or manifest.current_version not in manifest.versions:
            raise ValueError("Invalid prompt manifest version or domain")
        return manifest

    def _sources(self, name: str, sources: dict[str, str], visiting: set[str]) -> None:
        if name in visiting:
            raise ValueError("Cyclic prompt include")
        if name in sources:
            return
        if not (self.resource_dir / name).resolve().is_relative_to(self.resource_dir):
            raise ValueError("Prompt path escapes resource directory")
        source, _, _ = self.env.loader.get_source(self.env, name)
        visiting.add(name)
        for dependency in meta.find_referenced_templates(self.env.parse(source)):
            if dependency is None:
                raise ValueError("Dynamic prompt includes are not supported")
            self._sources(dependency, sources, visiting)
        visiting.remove(name)
        sources[name] = source

    def render(self, domain: str, template_name: str, **context: Any) -> str:
        if not _IDENTIFIER.fullmatch(domain) or Path(template_name).name != template_name:
            raise ValueError("Invalid prompt template name")
        return self.env.get_template(f"{domain}/{template_name}").render(**context).strip()

    def load(self, domain: str, version: str | None = None, **context: Any) -> tuple[str, str, PromptTrace]:
        manifest = self.manifest(domain)
        selected = version or manifest.current_version
        if selected not in manifest.versions:
            raise ValueError(f"Unknown prompt version: {domain}/{selected}")
        specification = manifest.versions[selected]
        sources: dict[str, str] = {}
        for name in (specification.system, specification.task):
            if name:
                self._sources(f"{domain}/{name}", sources, set())
        digest_input = {"sources": sources, "specification": specification.model_dump()}
        digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        system = self.render(domain, specification.system, **context)
        task = self.render(domain, specification.task, **context) if specification.task else ""
        return system, task, PromptTrace(
            prompt_id=domain, version=selected, bundle_hash=digest,
            output_schema_version=specification.output_schema_version,
        )

    def validate_all(self) -> None:
        """Fail early on missing resources, invalid includes or required variables."""
        for domain in ("analysis", "qa", "rewriter", "analytics"):
            self.manifest(domain)
        for path in sorted(self.resource_dir.glob("*/metadata.yaml")):
            manifest = self.manifest(path.parent.name)
            for version in manifest.versions:
                self.load(manifest.domain, version)


prompt_loader = PromptLoader()
