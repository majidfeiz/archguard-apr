from typing import Protocol

from archguard.domain.models import ArtifactReference


class RepairProviderPort(Protocol):
    def propose(self, analysis: ArtifactReference, problem: str) -> ArtifactReference:
        """Return a candidate patch artifact; never apply it to the source repository."""
        ...
