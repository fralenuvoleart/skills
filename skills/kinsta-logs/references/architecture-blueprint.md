# Agentic Workflow Architecture Blueprint

This document outlines the "Orchestrate-Analyze-Build" (OAB) architecture used by the `kinsta-logs` skill. This pattern is the gold standard for complex, multi-step agentic workflows that require data gathering, analysis, and formatted report generation.

Use this document as a blueprint when designing future skills that involve similar requirements.

---

## The Problem with "LLM-as-Operator"

Early iterations of complex skills often treat the LLM as a command-line operator and a Markdown editor. The LLM is instructed to:
1. Run a script to get data.
2. Run another script to get more data.
3. Use `sed` or `grep` to extract specific values.
4. Use `apply_diff` to inject findings into a pre-generated Markdown skeleton.

**Failure Modes of this approach:**
*   **Context Loss:** Long, multi-step procedural instructions cause the LLM to forget earlier steps or lose track of state variables (like directory paths).
*   **Brittle Execution:** Shell commands (`sed`, `grep`) written by the LLM are prone to escaping errors and typos.
*   **Formatting Breakage:** `apply_diff` on large Markdown files frequently fails due to line number shifts or slight formatting mismatches, destroying the final report.
*   **Instruction Fatigue:** Forcing the LLM to read the entire encyclopedia of domain knowledge (e.g., every possible bot type) wastes tokens and dilutes attention.

---

## The Solution: The OAB Architecture

The Orchestrate-Analyze-Build pattern solves these issues by strictly separating mechanical tasks from analytical reasoning.

### Phase 1: Orchestrate (Data Gathering)

**Goal:** Automate all mechanical data retrieval and initial parsing into a single command.

*   **Implementation:** A master script (e.g., `orchestrator.py`) handles API calls, file fetching, and running initial analysis scripts.
*   **State Management:** The orchestrator writes a `.run_state.json` file containing all necessary paths, timestamps, and environment variables. Subsequent scripts read this file instead of relying on the LLM to pass arguments correctly.
*   **Output:** The orchestrator produces a structured data payload (e.g., `context.json`) containing all raw data, metrics, and auto-generated tables.
*   **LLM Role:** The LLM simply executes the orchestrator script and waits for it to finish.

### Phase 2: Analyze (LLM Reasoning)

**Goal:** Focus the LLM entirely on high-level reasoning, correlation, and severity judgment.

*   **Dynamic Context Injection:** The analysis script (run by the orchestrator) examines the raw data and dynamically injects *only the relevant* domain rules into the `context.json` payload (e.g., an `llm_instructions` array). If a specific error isn't present, the rule for it isn't loaded.
*   **Structured Output:** The LLM reads `context.json` and writes its findings into a structured JSON file (e.g., `analyst_findings.json`). It does NOT write Markdown directly into the final report.
*   **LLM Role:** The LLM acts as a pure analyst. It reads the curated data, applies the injected rules, and outputs its conclusions in a strict JSON schema.

### Phase 3: Build (Report Generation)

**Goal:** Mechanically merge the LLM's findings with the raw data to produce a perfectly formatted final deliverable.

*   **Implementation:** A final script (e.g., `build_report.py`) reads `context.json` and `analyst_findings.json`. It handles all Markdown formatting, table generation, and verdict injection.
*   **Mechanical Validation:** Validation scripts (e.g., `verify_urls.py`) run automatically during this phase to mechanically check the LLM's output against source data, catching hallucinations (like transliterated URL typos) before the report is finalized.
*   **LLM Role:** The LLM executes the build script and presents the final file path to the user.

---

## Key Principles for Future Skills

When building a new skill using this blueprint, adhere to these principles:

1.  **Zero Formatting Risk:** The LLM should never use `apply_diff` to edit a complex Markdown report. It should output JSON, and a script should build the Markdown.
2.  **Progressive Disclosure:** Keep `SKILL.md` lean. Move dense rules (Tone Calibration, Formatting Directives) into `references/*.md` and link them explicitly.
3.  **Dynamic Prompt Assembly:** Do not force the LLM to read static reference files if the rules don't apply to the current run. Have your analysis scripts inject tailored instructions into the data payload.
4.  **Mechanical Validation:** If a fact can be checked mechanically (e.g., "Does this URL actually exist in the logs?"), write a script to check it. Do not rely on the LLM to self-correct typos.
5.  **State Files:** Use hidden JSON files (e.g., `.run_state.json`) to pass context between scripts. Never rely on the LLM to remember a directory path across a 20-turn conversation.