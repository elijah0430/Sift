from collections.abc import Callable, Sequence


def mae(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Average absolute error across equally weighted examples."""
    if not targets or len(predictions) != len(targets):
        raise ValueError("Expected non-empty, equally sized predictions and targets.")
    return sum(
        abs(prediction - target)
        for prediction, target in zip(
            predictions,
            targets,
            strict=True,
        )
    ) / len(targets)


def evaluate(
    inputs: Sequence[float],
    targets: Sequence[float],
    predict: Callable[[float], float],
    score: Callable[[Sequence[float], Sequence[float]], float] = mae,
) -> dict[str, float | int]:
    """Apply a caller-selected model and metric to a concrete dataset."""
    predictions = [predict(value) for value in inputs]
    return {"score": score(predictions, targets), "examples": len(targets)}
