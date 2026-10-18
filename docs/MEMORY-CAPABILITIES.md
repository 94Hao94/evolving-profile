# What EP can remember

[README](../README.md) · [简体中文](MEMORY-CAPABILITIES-中文.md)

EP turns source material into several kinds of memory with different purposes.
The distinction matters: a project fact answers “what happened?”, a preference
helps decide “how should we collaborate?”, and process experience helps assess
“what approach might work here?”. Original messages and tool evidence remain
the basis for checking the distilled result.

The capabilities below describe the published implementation. They do not imply
that every host captures every source automatically, that a new installation
contains populated memories, or that every request reads every layer. Setup and
host-specific limits remain in the [deployment](DEPLOYMENT.md),
[host](HOST-SETUP.md) and [agent setup](AGENT-SETUP.md) guides.

## User memory: context, preferences and their evidence

| Memory dimension | What is represented | How it helps |
| --- | --- | --- |
| **Facts and states** | Source-backed facts, plans, constraints, corrections and other reported context | Recover an earlier decision or distinguish an old plan from a later correction. |
| **Events and experiences** | Actions, interactions, event context and reported outcomes, with source-role attribution | Reconstruct what occurred without treating an assistant's report as independent verification. |
| **Entities and relationships** | People, organizations, places, projects and concepts, connected to memories and relationships supported by the source | Find related context while keeping similarly named projects and roles distinct. |
| **Temporal and contextual detail** | What, when, where, who and why; occurrence ranges, mention time and available metadata | Check whether a candidate concerns the intended person, stage and period. |
| **Consolidated observations** | Synthesized patterns and learnings derived from accumulated facts | Navigate recurring themes while retaining the distinction between synthesis and source evidence. |
| **Five-dimensional preferences** | Communication, learning, reasoning, collaboration and delivery, with conditions and lifecycle metadata | Adapt the way the agent works to the current task. |
| **Fusion mental models** | Versioned interpretations linking reviewed preference units across dimensions | Consult a broader working model with source references, exceptions and counterevidence. |
| **Scenario context** | Session/Project navigation, goals, constraints, corrections, reported progress and unresolved items in compact, standard and full summaries | Locate the relevant episode before reading more detail. |
| **Original evidence** | Available source text, message locators and bounded Session/Project history | Check exact names, amounts, versions, negations and disputed wording. |

These are product dimensions, not nine interchangeable database fact types.
The Bank stores `world`, `experience` and `observation` memory units. In the
extraction contract, user facts, preferences and constraints use `world`;
assistant actions use `assistant`, which maps to stored `experience`. User
experiences may therefore be represented as world facts about events. The
separate Agent Process Memory store adds execution-specific structure and gates;
it is not merely a renamed Bank `experience` category.

Implementation: [fact extraction](../api/evolving_profile_api/engine/retain/fact_extraction.py),
[Bank models](../api/evolving_profile_api/models.py),
[scenario model](../host-adapter/lib/scenario_model.py) and
[source readback](../api/evolving_profile_api/engine/source_facts.py).

## Preferences: five dimensions, with conditions intact

The Chinese labels match the preference UI. English UI labels are shortened to
Communication, Learning, Reasoning, Collaboration and Delivery.

| Dimension | Chinese UI label | Examples of the information captured |
| --- | --- | --- |
| **Communication & presentation** (`communication`) | 沟通与呈现 | Tone, wording, explanation length, organization and visual presentation. |
| **Learning & understanding** (`learning`) | 学习与理解 | Concrete examples, causal explanations, learning order and review methods. |
| **Analysis & decision-making** (`reasoning`) | 分析与决策 | Evidence requirements, comparison methods, uncertainty and recommendations. |
| **Execution & collaboration** (`collaboration`) | 执行与协作 | Initiative, task boundaries, checkpoints and collaboration behavior. |
| **Quality & delivery** (`delivery`) | 质量与交付 | Verification, acceptance criteria, output format and delivery expectations. |

The extraction contract distinguishes an explicit preference, a reusable explicit
requirement, an inferred pattern and a task-local instruction. A correction,
tradeoff or reason for dissatisfaction can supply evidence; the topic of a task
alone is insufficient. An inferred pattern requires independent source-family
support before publication. A one-task requirement retains its task scope.

A structured preference carries applicability and exceptions, its intended
effect on action, global/domain/project/task scope, polarity, stability or
method sensitivity, evidence references and source families. Support and
contradiction counts, recency inputs, revisions and supersession make changes
inspectable. A source quote retains its original wording even when the canonical
preference text corrects a supported speech-transcription error.

The console offers dimension, graph, table and timeline views, review states and
manual correction of text, applicability and exceptions. Correction does not
erase the need to check the source or grant broader execution authority.

Fusion mental models combine active preference revisions into sections with
applicability, exceptions, counterevidence and references. The atomic
cross-dimensional model contract requires supporting references across at least
two dimensions, plus a mechanism, confidence and last verification time. These
models are revisable interpretations for collaboration, not proof of personality
or a license to override the current request. This preference-fusion layer is
distinct from general Bank observation synthesis.

Implementation: [preference extraction](../guidance/extract_raw_preference_candidates.py),
[validation and source contracts](../guidance/schemas.py),
[model publication](../guidance/models.py),
[preference UI](../console/src/components/preference-view.tsx) and
[dimension/model graph](../console/src/lib/preference-graph.ts).

## Agent memory: from execution evidence to reusable experience

| Record or workflow | What it preserves | Reuse boundary |
| --- | --- | --- |
| **Raw trajectories and process events** | Available execution/tool metadata, source locators, task context and observed returns | A tool returning successfully is not proof that the task succeeded. |
| **Process observations** | Descriptions of execution behavior associated with source traces | An observation is evidence to assess, not a published strategy. |
| **Process drafts and failure episodes** | Failure signatures, attempted repairs and supporting traces | Drafts and historical candidates retain their evidence and maturity status. |
| **Repair patterns** | A repeated repair shape derived from verified episodes | Pattern promotion requires multiple verified episodes. |
| **Reusable process strategies** | Strategies derived from replicated patterns, with prerequisites, repair actions and verification | The internal record kind is `skill`; it does not automatically install a host Skill. |
| **Capability observations** | Independently verified results for a model/version, task family and phase | A result for one task family or phase is not a general model ranking. |
| **Migration and revalidation** | Transfer scope, environment/model fingerprints, drift and revalidation history | Model/tool changes require evidence for reuse; compatibility constraints apply when supplied. |
| **Task-level assistance** | Explicitly requested hints, recommendations, scaffolds or guards | The current agent still decides applicability and adoption. |

The process contract records nine execution phases: **understand, plan, retrieve,
act, observe, verify, recover, deliver and reflect**. Records can also carry task
archetypes and process-dimension tags, model/version information, environment and
modality/capability fingerprints, prerequisites, outcomes, counterevidence,
verification evidence, derivation links and creation/update time. The schema has
a versioned dimension-registry marker; process tags are extensible strings, not
a claim that every possible cognitive skill has a certified extractor.

Maturity separates observed, diagnosed, repaired, verified, replicated,
generalized and deprecated records. Historical strategy candidates can remain
in shadow status pending independent verification. Rollout supports shadow,
canary, publication and rollback with evaluation gates. Records requiring
revalidation or marked deprecated are excluded from normal process recall.

This supports adaptation through remembered experience and measured reuse. It
does not update model weights, guarantee autonomous improvement, or establish
that a historical repair will work with a new model and environment.

Implementation: [process contracts, promotion and compatibility](../host-adapter/lib/process_memory.py),
[evaluation gates](../host-adapter/lib/process_memory_evaluation.py),
[bounded trajectory capture and tool routes](../host-adapter/evolving_profile_controller_mcp.py) and
[Agent Memory UI](../console/src/components/agent-memory-view.tsx).

## Retrieval, original evidence and receipts

User Recall/Research and Agent Recall/Research serve their respective memory
planes. Scenario summaries help choose the right context; exact claims may
need original source readback. `compact → standard → full` expands navigation
detail within budgets. Even a full summary is not a complete transcript or
proof that every historical correction was preserved.

Optional external RAG searches operator-selected files using lexical/vector
retrieval, reciprocal-rank fusion and optional reranking. External documents
remain document evidence, with their own indexing and compatibility controls;
they do not become personal preferences or past execution experience simply
because a search returns them.

The evidence chain keeps **candidate discovery, admission, return, observed
delivery, original-source reading and confirmed answer adoption** separate.
Source references support provenance, while receipts describe observable events.
Neither alone proves present-day truth or answer quality. Missing attribution,
unavailable sources, unknown model identity and unmeasured delivery must remain
visible as limitations. Current requests, time, source revision and model/tool
applicability still need to be checked before using remembered material.

See [the README workflow](../README.md#ep-how-it-works) for the task-level view
and [release evidence and limits](RELEASE-NOTES-5.1.1.md) for the current package.
