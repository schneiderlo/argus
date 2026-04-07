from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from argus.errors import ArgusValidationError


@dataclass(frozen=True, slots=True)
class ProviderRunConfig:
    name: str
    provider_type: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_non_empty_string(self.name, "name"))
        if self.provider_type is not None:
            object.__setattr__(
                self,
                "provider_type",
                _normalize_non_empty_string(self.provider_type, "provider_type"),
            )
        if self.model is not None:
            object.__setattr__(
                self,
                "model",
                _normalize_non_empty_string(self.model, "model"),
            )
        if self.reasoning_effort is not None:
            object.__setattr__(
                self,
                "reasoning_effort",
                _normalize_non_empty_string(self.reasoning_effort, "reasoning_effort"),
            )


@dataclass(frozen=True, slots=True)
class RunConfig:
    provider_pool: tuple[str, ...]
    budget: int | None = None
    request: str | None = None
    prompt_file: Path | None = None
    cost_profile: str | None = None
    search_profile: str | None = None
    progress: str | None = None
    verbose: bool | None = None
    observe: bool | None = None
    observe_port: int | None = None
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
        if self.budget is not None:
            object.__setattr__(
                self,
                "budget",
                _normalize_positive_int(self.budget, "budget"),
            )
        if self.request is not None:
            object.__setattr__(
                self,
                "request",
                _normalize_non_empty_string(self.request, "request"),
            )
        if self.prompt_file is not None and not isinstance(self.prompt_file, Path):
            raise ArgusValidationError(
                f"prompt_file must be a filesystem path, got {type(self.prompt_file).__name__}."
            )
        if self.request is not None and self.prompt_file is not None:
            raise ArgusValidationError(
                "Run config may set only one of `request` or `prompt_file`."
            )
        if self.cost_profile is not None:
            object.__setattr__(
                self,
                "cost_profile",
                _normalize_non_empty_string(self.cost_profile, "cost_profile"),
            )
        if self.search_profile is not None:
            object.__setattr__(
                self,
                "search_profile",
                _normalize_non_empty_string(self.search_profile, "search_profile"),
            )
        if self.progress is not None:
            object.__setattr__(
                self,
                "progress",
                _normalize_non_empty_string(self.progress, "progress"),
            )
        if self.verbose is not None:
            object.__setattr__(
                self,
                "verbose",
                _normalize_bool(self.verbose, "verbose"),
            )
        if self.observe is not None:
            object.__setattr__(
                self,
                "observe",
                _normalize_bool(self.observe, "observe"),
            )
        if self.observe_port is not None:
            object.__setattr__(
                self,
                "observe_port",
                _normalize_positive_int(self.observe_port, "observe_port"),
            )

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
        allowed_top_level_keys = {
            "provider",
            "provider_pool",
            "providers",
            "budget",
            "request",
            "prompt_file",
            "cost_profile",
            "search_profile",
            "progress",
            "verbose",
            "observe",
            "observe_port",
        }
        extra_top_level_keys = sorted(set(payload) - allowed_top_level_keys)
        if extra_top_level_keys:
            raise ArgusValidationError(
                "Run config contains unsupported top-level keys: "
                + ", ".join(extra_top_level_keys)
            )

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
            allowed_keys = {"model", "reasoning_effort", "type"}
            extra_keys = sorted(set(raw_provider_config) - allowed_keys)
            if extra_keys:
                raise ArgusValidationError(
                    f"[providers.{normalized_name}] contains unsupported keys: "
                    + ", ".join(extra_keys)
                )
            providers[normalized_name] = ProviderRunConfig(
                name=normalized_name,
                provider_type=None
                if "type" not in raw_provider_config
                else _normalize_non_empty_string(
                    raw_provider_config["type"],
                    f"providers.{normalized_name}.type",
                ),
                model=None
                if "model" not in raw_provider_config
                else _normalize_non_empty_string(
                    raw_provider_config["model"],
                    f"providers.{normalized_name}.model",
                ),
                reasoning_effort=None
                if "reasoning_effort" not in raw_provider_config
                else _normalize_non_empty_string(
                    raw_provider_config["reasoning_effort"],
                    f"providers.{normalized_name}.reasoning_effort",
                ),
            )

        provider_pool = _load_provider_pool(payload, providers)
        budget = None if "budget" not in payload else payload["budget"]
        request = None if "request" not in payload else payload["request"]
        prompt_file = None
        if "prompt_file" in payload:
            prompt_path = Path(
                _normalize_non_empty_string(payload["prompt_file"], "prompt_file")
            ).expanduser()
            if not prompt_path.is_absolute():
                prompt_path = resolved_path.parent / prompt_path
            prompt_file = prompt_path.resolve()
        return cls(
            provider_pool=provider_pool,
            budget=budget,
            request=request,
            prompt_file=prompt_file,
            cost_profile=None if "cost_profile" not in payload else payload["cost_profile"],
            search_profile=None
            if "search_profile" not in payload
            else payload["search_profile"],
            progress=None if "progress" not in payload else payload["progress"],
            verbose=None if "verbose" not in payload else payload["verbose"],
            observe=None if "observe" not in payload else payload["observe"],
            observe_port=None if "observe_port" not in payload else payload["observe_port"],
            providers=providers,
        )

    def provider_model(self, provider_name: str) -> str | None:
        normalized_name = _normalize_non_empty_string(provider_name, "provider_name")
        provider = self.providers.get(normalized_name)
        if provider is None:
            return None
        return provider.model

    def provider_type_name(self, provider_name: str) -> str:
        normalized_name = _normalize_non_empty_string(provider_name, "provider_name")
        provider = self.providers.get(normalized_name)
        if provider is None:
            return normalized_name
        if provider.provider_type is not None:
            return provider.provider_type
        return normalized_name

    def provider_reasoning_effort(self, provider_name: str) -> str | None:
        normalized_name = _normalize_non_empty_string(provider_name, "provider_name")
        provider = self.providers.get(normalized_name)
        if provider is None:
            return None
        return provider.reasoning_effort


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


def _normalize_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise ArgusValidationError(
            f"{field_name} must be an integer, got {type(value).__name__}."
        )
    if value <= 0:
        raise ArgusValidationError(f"{field_name} must be a positive integer.")
    return value


def _normalize_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ArgusValidationError(
            f"{field_name} must be a boolean, got {type(value).__name__}."
        )
    return value
