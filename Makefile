# Holdings benchmark: can open-weight models be trusted about library holdings?
# Stages are separate so figures can be regenerated without re-running models.

RUNS ?= 3
MODELS ?= gemma4:latest,gemma4:26b,gpt-oss:20b,qwen3:32b,qwen2.5:7b,llama3.1:latest,llama3.2:latest

.PHONY: all ground-truth bench bench-dev analyze plot clean-results fidelity

all: ground-truth bench analyze plot

ground-truth:        ## verify the held/absent title list against NEXUS (no model)
	uv run python -m benchmark.ground_truth

bench:               ## full sweep: all MODELS x all titles x RUNS (resumable)
	uv run python -m benchmark.run --models "$(MODELS)" --runs $(RUNS)

bench-dev:           ## smoke test: first model, one held + one absent title, 1 run
	uv run python -m benchmark.run --models "$(MODELS)" --dev

analyze:             ## per-model metrics -> benchmark/results/summary.{json,md}
	uv run python -m benchmark.analyze

plot:                ## figures from the summary -> benchmark/figures/
	uv run python -m benchmark.plot

clean-results:       ## delete trial results (keeps ground truth and figures)
	rm -rf benchmark/results

fidelity:            ## search-fidelity traces: all questions x RUNS, local model -> fidelity/results/
	uv run python -m fidelity.run --runs $(RUNS)
