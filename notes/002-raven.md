---
title: "Raven: The Harness of Harnesses for Composable Agentic Intelligence"
source: https://arxiv.org/abs/2609.33439
license: CC BY 4.0
---

# Raven: the harness of harnesses

EverMind AI, *Raven: The Harness of Harnesses for Composable Agentic Intelligence*, arXiv 2609.33439v1 (cs.AI, 27 September 2026), 82 pages. Code: https://github.com/EverMind-AI/Raven. This note is adapted from the paper, which is licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); the summary and the selection of results are ours.

## In one paragraph

What an agent can do depends on its model and on its **harness**: the tool interfaces, context and memory handling, skills, control rules and error recovery wrapped around the model. Harnesses keep growing, so building them by hand stops scaling, and a harness tuned for one domain carries assumptions that make it a poor fit elsewhere. Raven changes the question from "how do I build a stronger harness for one domain?" to "how do I build specialised harnesses automatically, improve them with experience, and make them work together?" It treats every runnable model-harness pair as one composable unit and puts a host agent on top that plans which unit does what, in which order.

## Terms

- **Model**: the LLM itself, its weights. Raven never trains it.
- **Harness**: everything that turns the model into an agent that acts: tools, context, memory, skills, rules, recovery.
- **Agent**: a model-harness pair, written `a_i = Agent(M_i, h_i)`. Two agents may share a model; different harnesses make them different units.
- **Specialist**: an agent whose harness is tuned for one domain. Raven ships four: Raven-Research, Raven-Code, Raven-Design and Raven-Oncall.
- **Third-party agent**: an agent built elsewhere, with its own harness, connected through an adapter. The paper names Claude Code, Codex, Hermes Agent and OpenClaw.
- **Host Agent**: the agent the user talks to. It breaks a request into subtasks, picks an agent for each, wires their dependencies and merges the results.
- **DAG**: a directed acyclic graph. Each node is one agent call; an edge says "this node needs that node's output". No cycles means no two jobs can wait on each other forever.
- **Artifact**: a concrete output of a node, such as a report, code, a slide file or a test result. Agents hand work to each other through recorded artifacts, not free-form chat.

## How a request becomes a graph

The paper's running example: a user asks for a survey of recent progress in AI for AI research, a reproduction of the leading algorithms in one environment, and a web page that reports the results. Two research nodes can start at once, one on the algorithms and one on their benchmarks. A coding node needs both. A design node needs the reproduction results:

```
{research: algorithms, research: benchmarks} -> code -> design
```

Collaboration runs in five stages.

1. **Plan.** The host loads the full orchestration guide only when a request needs several agents; otherwise a short description is all it carries, which keeps the context small. It builds the graph backwards from the deliverable: every node needs an identifiable output and an agent able to make it.
2. **Admit.** Before any worker starts, the runtime runs five groups of checks: format, graph structure (unique ids, dependencies that resolve, file paths kept inside the workspace, no cycles), capability (wiring the chosen agent can honour), status (each named agent registered and enabled) and environment (no recursive delegation from inside a sub-agent, a shared dispatch budget, user approval when asked). It stops at the first failure and names the node or field at fault, often with the repair.
3. **Run.** A node starts once all its predecessors have completed. Its output, or the error it raised, goes to a completion judge that reads the prompt, the output and the end of the transcript. A failed verdict becomes an exception report for the host; a worker's question is answered from the host's conversation and memory when possible, and otherwise reaches the user.
4. **Report.** A run report returns file locations and final outputs to the host, which writes the answer.
5. **Reuse.** Later graphs refer to completed nodes instead of redoing them. Every node's prompt, output and transcript sit in an append-only artifact ledger, and file or node contents passed into a prompt are marked as untrusted data, kept apart from the host's instructions.

## The theory, in one line

The paper defines "composable intelligence" as reliable task coverage under a shared resource budget, and proves sufficient conditions under which a composed system solves tasks that no single available agent solves reliably alone: the local capabilities complement each other, the handoffs between agents are compatible, and planning and execution errors stay bounded. The cost of planning and coordination is counted. The paper is careful: these are sufficient conditions, and whether real agents and a real host meet them is a separate question.

## Getting better without training: harness self-evolution

The model stays frozen; the policy around it changes. The best harness so far supplies failure traces; a loop diagnoses them and proposes edits of four kinds (prompt, domain knowledge, runtime rules, configuration), screens the candidates for validity, activation and a paired gain, and keeps one complete harness per edit kind and failure pattern in a "gene bank". The harness picked on training tasks is frozen before the held-out test. These numbers come from the team's earlier HarnessBank paper, reproduced in Raven's Table 11 (frozen Qwen3.6-27B, held-out Pass@1, %):

| Benchmark | Initial | Evolved | Gain |
|---|---|---|---|
| AppWorld | 41.3 | 56.7 | +15.4 |
| BrowseComp+ | 16.9 | 30.8 | +13.9 |
| LiveCodeBench | 58.1 | 71.8 | +13.7 |
| Omni-MATH | 54.3 | 66.0 | +11.7 |
| Terminal-Bench-2 | 36.1 | 45.4 | +9.3 |
| GDPval | 43.7 | 52.9 | +9.2 |
| SWE-bench Verified | 47.4 | 52.6 | +5.1 |

All seven improve. Six pass the source's paired-gain test; SWE-bench Verified, with a 26-task test split, does not. Scores and gains are as HarnessBank reported them (SWE-bench Verified's rounded scores differ by 5.2).

## Planning results: MAOB

MAOB (Multi-Agent Orchestration Benchmark) is new in this paper: 140 tasks over four specialist domains, covering all 11 combinations of two or more domains. It measures planning alone: each system gets the request, submits a graph through its own orchestration tool, and the graph is scored against a reference before any worker runs. Three systems on identical inputs: Raven, Claude Code and Hermes Agent, each on two backbones.

- **Node F1**: did it pick the right specialists?
- **Edge F1**: did it draw the right dependencies?
- **Partial Order Accuracy**: for the shared nodes, is the order accepted?
- **Exact Match**: is the whole plan right, specialists and order both?

Scores (0 to 1; Figure 13, Figure 1):

| Metric | Qwen3.8-27B: Claude Code / Hermes / Raven | DeepSeek-V4-Flash-0731: Claude Code / Hermes / Raven |
|---|---|---|
| Node F1 | 0.524 / 0.776 / 0.923 | 0.835 / 0.854 / 0.963 |
| Edge F1 | 0.507 / 0.744 / 0.812 | 0.813 / 0.776 / 0.897 |
| Partial Order Accuracy | 0.518 / 0.780 / 0.950 | 0.844 / 0.803 / 0.918 |
| Exact Match | 0.464 / 0.607 / 0.711 | 0.762 / 0.748 / 0.867 |

Raven leads on all four metrics with both backbones. Exact Match beats the strongest baseline by 10.4 points (Qwen3.8-27B) and 10.5 points (DeepSeek-V4-Flash-0731). The baselines swap places between backbones: Hermes Agent leads Claude Code everywhere on Qwen, Claude Code leads on three of four metrics on DeepSeek.

## The four specialists

- **Raven-Research**, DeepResearch Mixed accuracy (Table 4): best in all three shared-backbone groups, 56.3 vs 49.7, 59.3 vs 56.0 and 76.5 vs 68.9, so +6.6, +3.3 and +7.6 points over the stronger of MiroFlow and DeepSeek-Harness.
- **Raven-Code**: best in six of eight settings; the largest margin is whole-repository stack migration (SWE-Refactor), 16.5 against 7.0 for the compared leaderboard entries with DeepSeek-V4-Flash.
- **Raven-Design**, PresentBench (0 to 100): 80.2 with Claude Opus 5 and 72.9 with GPT-5.6 Luna, against 78.3 and 52.4 for Claude Code on the same models.
- **Raven-Oncall**, 17 internal scientific tasks with Claude Opus 5: 14 solved (82.35%) against 11 for Claude Code (64.71%), at 5.10 USD per task on average against 13.60 USD, and 6.1 million tokens against 16.3 million.

## Skills

Skill Forge serves reusable procedures (in the Agent Skills `SKILL.md` format) from a curated catalogue and from experience. From the team's SkillCorpus paper: skill retrieval improves all twelve comparisons (two harnesses, Raven and OpenClaw, on two backbones and three benchmarks, each averaged over three runs). On SkillsBench with Qwen3.5-397B-A17B, Raven goes from 9.2 to 22.6 Pass@1 (+13.4) while OpenClaw with the same skills goes from 11.1 to 16.9 (+5.8).

## How to use it

- If your agent setup has more than one specialist, write the plan as a graph with explicit inputs and outputs before anything runs, and validate it the way Raven's admission does.
- Hand work over as files or records, not as chat. A reviewer, or the next agent, can then point at exactly what it was given.
- Mark anything copied from another agent's output as untrusted data in the next prompt.
- Before tuning the model, try tuning the harness: prompts, rules and settings around a frozen model moved held-out scores by 5 to 15 points in the reported runs.

## Limits

- The harness-evolution and skill results are not new experiments of this report; they are reproduced from HarnessBank and SkillCorpus, as the paper says.
- MAOB scores the plan, not the work: no worker runs, so a perfect graph says nothing about whether the agents then succeed.
- The theory gives sufficient conditions; the paper itself notes that whether real agents and a host meet them is a separate question.
- The four specialists are each compared on their own benchmarks and backbones, so the numbers do not add up to one end-to-end comparison.
