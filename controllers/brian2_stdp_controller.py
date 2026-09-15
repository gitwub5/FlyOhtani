from __future__ import annotations


class Brian2STDPController:
    """Placeholder boundary for reward-modulated STDP experiments.

    Brian2 is optional in this repository. The controller raises a helpful error
    until the SNN experiment path is implemented.
    """

    def __init__(self) -> None:
        try:
            import brian2 as brian2  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Brian2STDPController requires the optional SNN dependency. "
                'Install it with: pip install -e ".[snn]"'
            ) from exc

    def reset(self) -> None:
        raise NotImplementedError("Brian2 STDP reset logic is not implemented yet.")

    def act(self, observation):
        raise NotImplementedError("Brian2 STDP action logic is not implemented yet.")
