# Research and engineering decisions

- **Deterministic control:** Python owns state transitions, command execution, verification, scoring, and promotion. LLM roles propose, implement, and review only.
- **Provider-neutral roles:** each role independently selects an Anthropic-compatible or OpenAI-compatible endpoint, model, effort, and budgets. No interactive subscription is used.
- **Content lineage, not Git:** champions and candidates are bound by SHA-256 manifests. The project need not be a Git repository.
- **Task-only workspaces:** an experiment copies only its selected task, avoiding routine duplication of the roughly 886 MB DQI artifact for other tasks.
- **Orchestrator-only commands:** agents use confined file tools. Configured builds/tests and official verifiers run outside the agent tool loop.
- **Full gate:** promotion requires full official PASS, finite positive improved cost, unchanged candidate bytes, and an unchanged parent. Full failures do not enter same-salt repair loops.
- **Local score caveat:** geometric-mean estimates use pinned local reference costs. Private-salt hosted results can differ, especially for DQI.
- **No automatic submission:** portfolio packaging uses the existing local package utility and never calls Kaggle.
