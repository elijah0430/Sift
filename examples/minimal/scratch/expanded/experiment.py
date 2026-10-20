import argparse
import json
from pathlib import Path

from toy_research import evaluate, mae


def clipped_mae(predictions, targets):
    return sum(
        min(abs(prediction - target), 1.0)
        for prediction, target in zip(
            predictions,
            targets,
            strict=True,
        )
    ) / len(targets)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/shifted.json")
    parser.add_argument("--model", choices=["identity", "scaled"], default="scaled")
    parser.add_argument("--metric", choices=["mae", "clipped"], default="clipped")
    args = parser.parse_args()
    data = json.loads(Path(args.dataset).read_text())
    predict = (lambda value: value * 2) if args.model == "scaled" else (lambda value: value)
    metrics = evaluate(
        data["inputs"],
        data["targets"],
        predict,
        score=clipped_mae if args.metric == "clipped" else mae,
    )
    Path("results").mkdir(exist_ok=True)
    Path("results/metrics.json").write_text(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
