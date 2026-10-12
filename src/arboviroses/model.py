"""Modelo global MLP com saída de contagem binomial negativa."""

from __future__ import annotations


def build_model(n_municipalities: int, lookback: int = 52, hidden: tuple[int, int] = (128, 64)):
    try:
        import torch
        import torch.nn as nn
    except ImportError as error:
        raise RuntimeError(
            "PyTorch não está instalado. Instale o extra de treino: pip install -e '.[train]'"
        ) from error

    class GlobalCountMLP(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.city_embedding = nn.Embedding(max(n_municipalities, 1), 8)
            self.network = nn.Sequential(
                nn.Linear(lookback + 4 + 7 + 8 + 8, hidden[0]),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden[0], hidden[1]),
                nn.ReLU(),
                nn.Linear(hidden[1], 8),
            )

        def forward(self, history, regional, state, municipality, season):
            features = self.network(
                torch.cat(
                    (history, regional, state, self.city_embedding(municipality), season),
                    dim=1,
                )
            )
            raw_mean, raw_dispersion = features[:, :4], features[:, 4:]
            mean = torch.nn.functional.softplus(raw_mean) + 1e-5
            dispersion = torch.nn.functional.softplus(raw_dispersion) + 1e-3
            return mean, dispersion

    return GlobalCountMLP()


def negative_binomial_nll(mean, dispersion, target, mask):
    """NLL da NB do PyTorch; probs=mu/(r+mu), logo média=r*p/(1-p)=mu."""
    import torch

    safe_mean = mean.clamp_min(1e-6)
    safe_dispersion = dispersion.clamp_min(1e-5)
    distribution = torch.distributions.NegativeBinomial(
        total_count=safe_dispersion,
        logits=torch.log(safe_mean) - torch.log(safe_dispersion),
    )
    log_probability = distribution.log_prob(target)
    weights = mask.to(log_probability.dtype)
    return -(log_probability * weights).sum() / weights.sum().clamp_min(1.0)
