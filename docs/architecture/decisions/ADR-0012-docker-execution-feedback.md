# ADR-0012: Docker-only deterministic execution feedback

Status: accepted

Phase 7 needs functional evidence without trusting candidate code. A narrow application port is
implemented by a Docker CLI adapter; domain comparison stays filesystem-, process- and
vendor-neutral. Plans are trusted explicit inputs with immutable images and argument vectors.

The adapter copies detached worktrees, supplies no ambient environment, applies privilege/resource
restrictions, and fails closed. Semantic artifacts exclude operational identity and raw logs. Docker
remains trusted; stronger hostile-code isolation requires a hardened VM or sandbox service.

Direct host subprocesses, shell strings, mutable tags, repository-derived commands and local fallback
are rejected. This phase adds no repair generation, agent integration, benchmark or language model.
