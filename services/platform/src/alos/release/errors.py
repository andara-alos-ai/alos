"""Release-governance exception types."""


class ReleaseGovernanceError(RuntimeError):
    """A safe lifecycle policy failure."""


class SegregationOfDutiesError(ReleaseGovernanceError):
    """One person attempted incompatible lifecycle duties."""


class LifecycleConflictError(ReleaseGovernanceError):
    """A transition lacks required evidence or is out of sequence."""
