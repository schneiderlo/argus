from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from argus.errors import ArgusValidationError


@dataclass(frozen=True, slots=True)
class ProviderRunConfig:
    name: str
    model: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_non_empty_string(self.name, "name"))
        if self.model is not None:
            object.__setattr__(
                self,
                "model",
                _normalize_non_empty_string(self.model, "model"),
            )


@dataclass(frozen=True, slots=True)
class RunConfig:
    provider_pool: tuple[str, ...]
    providers: dict[str, ProviderRunConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_pool: list[str] = []
        for index, provider_name in enumerate(self.provider_pool):
            normalized_name = _normalize_non_empty_string(
                provider_name,
                f"provider_pool[{index}]",
            )
            if normalized_name in normalized_pool:
                raise ArgusValidationError(
                    f"provider_pool contains duplicate provider names: {normalized_name}."
                )
            normalized_pool.append(normalized_name)
        if not normalized_pool:
            raise ArgusValidationError("provider_pool must include at least one provider.")
        object.__setattr__(self, "provider_pool", tuple(normalized_pool))

        normalized_providers: dict[str, ProviderRunConfig] = {}
        for provider_name, provider_config in self.providers.items():
            normalized_name = _normalize_non_empty_string(provider_name, "providers key")
            if not isinstance(provider_config, ProviderRunConfig):
                raise ArgusValidationError(
                    "providers entries must be ProviderRunConfig instances, "
                    f"got {type(provider_config).__name__}."
                )
            if provider_config.name != normalized_name:
                raise ArgusValidationError(
                    "providers keys must match each provider config name."
                )
            normalized_providers[normalized_name] = provider_config
        object.__setattr__(self, "providers", normalized_providers)

        missing = [name for name in self.provider_pool if name not in self.providers]
        if missing:
            raise ArgusValidationError(
                "provider_pool references providers without configuration blocks: "
                + ", ".join(missing)
            )

    @classmethod
    def load(cls, path: Path) -> "RunConfig":
        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_file():
            raise ArgusValidationError(f"Run config does not exist: {resolved_path}")
        try:
            payload = tomllib.loads(resolved_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ArgusValidationError(
                f"Run config is not valid TOML: {resolved_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ArgusValidationError("Run config must decode to a TOML table.")

        provider_table = payload.get("providers", {})
        if not isinstance(provider_table, dict):
            raise ArgusValidationError("[providers] must be a TOML table.")

        providers: dict[str, ProviderRunConfig] = {}
        for provider_name, raw_provider_config in provider_table.items():
            normalized_name = _normalize_non_empty_string(provider_name, "providers key")
            if not isinstance(raw_provider_config, dict):
                raise ArgusValidationError(
                    f"[providers.{normalized_name}] must be a TOML table."
                )
            allowed_keys = {"model"}
            extra_keys = sorted(set(raw_provider_config) - allowed_keys)
            if extra_keys:
                raise ArgusValidationError(
                    f"[providers.{normalized_name}] contains unsupported keys: "
                    + ", ".join(extra_keys)
                )
            providers[normalized_name] = ProviderRunConfig(
                name=normalized_name,
                model=None
                if "model" not in raw_provider_config
                else _normalize_non_empty_string(
                    raw_provider_config["model"],
                    f"providers.{normalized_name}.model",
                ),
            )

        provider_pool = _load_provider_pool(payload, providers)
        return cls(provider_pool=provider_pool, providers=providers)

    def provider_model(self, provider_name: str) -> str | None:
        normalized_name = _normalize_non_empty_string(provider_name, "provider_name")
        provider = self.providers.get(normalized_name)
        if provider is None:
            return None
        return provider.model


@dataclass(frozen=True, slots=True)
class ArgusConfig:
    """Filesystem locations used by the CLI."""

    root_dir: Path
    benchmark_cases_dir: Path
    artifacts_dir: Path
    benchmark_runs_dir: Path
    runs_dir: Path
    agent_runs_dir: Path
    provider_invocations_dir: Path
    verify_dir: Path
    latest_benchmark_run_pointer: Path
    latest_agent_run_pointer: Path

    @classmethod
    def discover(cls, root: Path | None = None) -> "ArgusConfig":
        root_dir = (root or Path.cwd()).expanduser().resolve()
        artifacts_dir = root_dir / "artifacts"
        return cls(
            root_dir=root_dir,
            benchmark_cases_dir=root_dir / "benchmarks" / "cases",
            artifacts_dir=artifacts_dir,
            benchmark_runs_dir=artifacts_dir / "benchmarks",
            runs_dir=artifacts_dir / "runs",
            agent_runs_dir=artifacts_dir / "agent_runs",
            provider_invocations_dir=artifacts_dir / "provider_invocations",
            verify_dir=artifacts_dir / "verify",
            latest_benchmark_run_pointer=artifacts_dir / "benchmarks" / "latest.txt",
            latest_agent_run_pointer=artifacts_dir / "latest-run.txt",
        )


def _load_provider_pool(
    payload: dict[str, object],
    providers: dict[str, ProviderRunConfig],
) -> tuple[str, ...]:
    if "provider_pool" in payload:
        raw_pool = payload["provider_pool"]
        if not isinstance(raw_pool, list):
            raise ArgusValidationError("provider_pool must be a TOML array of strings.")
        return tuple(
            _normalize_non_empty_string(value, f"provider_pool[{index}]")
            for index, value in enumerate(raw_pool)
        )
    if "provider" in payload:
        return (_normalize_non_empty_string(payload["provider"], "provider"),)
    if providers:
        return tuple(providers)
    raise ArgusValidationError(
        "Run config must define `provider`, `provider_pool`, or at least one [providers.<name>] table."
    )


def _normalize_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ArgusValidationError(
            f"{field_name} must be a string, got {type(value).__name__}."
        )
    normalized = value.strip()
    if not normalized:
        raise ArgusValidationError(f"{field_name} must not be empty.")
    return normalized
