import json
from pathlib import Path

from toy_research import evaluate


def main():
    data = json.loads(Path("data/original.json").read_text())
    metrics = evaluate(data["inputs"], data["targets"], predict=lambda value: value)
    Path("results").mkdir(exist_ok=True)
    Path("results/metrics.json").write_text(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
