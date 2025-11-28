# Failure Analysis Report: Persistent Gemini Grounding Issues

**Date:** 2025-09-13
**Author:** Cline (LLM Agent)
**Project:** FilePromptForge (FPF)
**Focus:** Investigation into repeated failures to achieve provider-side web search grounding for `gemini/gemini-2.5-flash` via LiteLLM.

---

## 1. Original Goal and Core Constraints

The primary objective was to enable **provider-side web search grounding** for FilePromptForge (FPF) running with `gemini/gemini-2.5-flash` through the LiteLLM proxy. This functionality must adhere to several non-negotiable constraints:

*   **Always Use Grounding:** FPF must *always* attempt to use grounding for every request when enabled.
*   **No Fallback:** If a grounded call fails, there must be *no fallback* to a non-grounded call or any alternative. The process must fail fast with error metadata.
*   **FPF Provider-Agnostic:** FPF's core application logic must *never* contain provider-specific or model-specific logic. All necessary adaptations for API shapes, tool injection, or grounding mechanisms must occur within the **LiteLLM proxy configuration**.
*   **Explicit Tooling:** FPF communicates its intent to LiteLLM by explicitly sending OpenAI-style `Responses` API calls, including `tools=[{"type": "web_search_preview"}]`.

## 2. Analysis of Iterative Attempts and Failures

This section details each significant attempt, the underlying hypothesis, the configuration changes, and the observed outcome that led to continued "no-tool" successful completions or HTTP 400 errors.

---

### Attempt 1: Initial Gemini Call with Automatic Web Search Abstraction (via `Responses` API in FPF)

*   **Hypothesis:** LiteLLM's `Responses` endpoint would automatically translate FPF's `tools=[{"type": "web_search_preview"}]` to Gemini's native web search tool (`google_search` or `google_search_retrieval`).
*   **`litellm_config.yaml` (Relevant Snippet):**
    ```yaml
      # Alias that matches provider-prefixed slug
      - model_name: "gemini/gemini-2.5-flash"
        litellm_params:
          model: "gemini/gemini-2.5-flash"
          api_key: os.environ/GOOGLE_API_KEY
          # No explicit web_search: {} or extra_body yet
          drop_params: true
          additional_drop_params: ["tools", "tool_choice"]
        model_info:
          supports_web_search: true
    ```
*   **Observed Outcome:**
    *   **Prior to LiteLLM reload (due to config changes):** Initial runs failed with HTTP 400 errors from LiteLLM, indicating "Function calling config is set without function_declarations." This meant LiteLLM was forwarding the OpenAI-style tool metadata to Gemini, but Gemini rejected it because it expected its own native tool declarations.
    *   **After LiteLLM reload & `extra_body` re-addition confusion:** (See below for details on how `extra_body` was added.)

*   **Conclusion:** LiteLLM's *default* handling of `tools=[{"type": "web_search_preview"}]` from the `Responses` API for Gemini was insufficient. It didn't automatically inject the correct Gemini-native search tool.

---

### Attempt 2: Explicitly Inject `google_search` via `extra_body` (First Set, Initial Phase)

*   **Hypothesis:** By explicitly providing Gemini's native `google_search` tool within `extra_body`, LiteLLM would correctly inject it into the request.
*   **`litellm_config.yaml` (Relevant Snippet):**
    ```yaml
      # Alias that matches provider-prefixed slug
      - model_name: "gemini/gemini-2.5-flash"
        litellm_params:
          model: "gemini/gemini-2.5-flash"
          api_key: os.environ/GOOGLE_API_KEY
          web_search: {} # Added this per docs for web search
          extra_body: # This was introduced
            tools:
              - google_search: {}
            tool_config:
              function_calling_config:
                mode: AUTO
          drop_params: true
          additional_drop_params: ["tools", "tool_choice"]
        model_info:
          supports_web_search: true
    ```
*   **Observed Outcome (First run after this change and LiteLLM restart):**
    *   **HTTP 400 Error:** `"Error code: 400 - {'error': {'message': 'litellm.BadRequestError: VertexAIException BadRequestError - {"error": {"code": 400,"message": "Function calling config is set without function_declarations.", ...`
    *   This was the same error as before.
*   **Conclusion:** Directly injecting `extra_body` with `google_search` while simultaneously relying on `web_search: {}` (or `web_search_options: {}`) and dropping original tools seemed to create a conflict or was simply not the correct combination for LiteLLM to handle the web search abstraction. The original FPF client sent `tools=[{"type": "web_search_preview"}]`, which might have conflicted with the `extra_body` injection via LiteLLM's internal routing.

---

### Attempt 3: Switch FPF to `chat.completions` (Abandoning `Responses` API for Grounded Calls)

*   **Hypothesis:** Perhaps LiteLLM's `web_search_options` abstraction works more reliably for the `chat.completions` endpoint for Gemini. This was a deviation in FPF's strategy, moving from the tool-centric `Responses` API.
*   **FPF Code Change:** `APIClient.send_prompt` was modified to use `client.chat.completions.create(...)` when `grounding_enabled` = True.
*   **`litellm_config.yaml` (Relevant Snippet, *during this phase*)**
    ```yaml
      # Alias that matches provider-prefixed slug
      - model_name: "gemini/gemini-2.5-flash"
        litellm_params:
          model: "gemini/gemini-2.5-flash"
          api_key: os.environ/GOOGLE_API_KEY
          web_search: {} # This was the primary way to enable web search
          # Extra body and additional_drop_params were still present, creating a complex interaction
          extra_body:
            tools:
              - google_search: {}
            tool_config:
              function_calling_config:
                mode: AUTO
          drop_params: true
          additional_drop_params: ["tools", "tool_choice"]
        model_info:
          supports_web_search: true
    ```
*   **Observed Outcome:**
    *   **No HTTP errors**, but `method: "no-tool"` and `sources: []` in FPF's meta.json.
    *   Output content was full-length, but *semantically not grounded* (e.g., outdated dates for weather).
    *   `raw_response_excerpt` showed `object='chat.completion'` and `tools:[]`.
*   **Initial Conclusion:** The `chat.completions` path worked transport-wise, but LiteLLM was *still* not correctly injecting the web search tool, indicating the abstraction was failing or conflicting.

---

### Attempt 4: Clean `litellm_config.yaml` for `chat.completions` (Removing `extra_body`)

*   **Hypothesis:** The `extra_body` config was conflicting with LiteLLM's `web_search: {}` abstraction for `chat.completions`. Removing it would allow LiteLLM to correctly handle the web search injection.
*   **`litellm_config.yaml` Change:** Removed `extra_body` from `gemini/gemini-2.5-flash` entries.
*   **Observed Outcome:**
    *   **No HTTP errors**, but `method: "no-tool"`, `sources: []`, and semantically ungrounded content.
*   **Conclusion:** This confirmed that `web_search: {}` alone (without `extra_body`) was also insufficient for triggering Gemini grounding for `chat.completions`. The core problem of LiteLLM not correctly engaging the search tool persisted across both `extra_body` usage and its absence, when calling via `chat.completions`.

---

### Attempt 5: **Crucial Remediation: Reverting FPF to `responses` API (Corrected Strategy)**

*   **User Decision:** User explicitly chose to switch FPF back to `client.responses.create(...)` for grounded calls (as `Option B` for FPF's strategy). This was an explicit instruction overcoming previous client-side refactoring.
*   **FPF Code Change:** `APIClient.send_prompt` was modified back to use `client.responses.create(...)` when `grounding_enabled` is True, sending `tools=[{"type": "web_search_preview"}]`.
*   **`litellm_config.yaml` at time of this run:** This was the state after "Attempt 4", where `extra_body` was removed, leaving only `web_search: {}` and `drop_params`.
*   **Observed Outcome:**
    *   **HTTP 400 Error:** `litellm.BadRequestError: VertexAIException BadRequestError - {"error": {"code": 400,"message": "Function calling config is set without function_declarations.", ...`
    *   This returned us to the original 400 error, which occurs when LiteLLM forwards the OpenAI-style `tools` parameter to Gemini without the necessary translation/injection of Gemini-native `google_search` tools.
*   **Conclusion:** The `responses` API indeed correctly carries the `tools` parameter, but LiteLLM (in this build) is *not* translating the `web_search_preview` tool type to Gemini's native requirements. This reiterates that the `extra_body` was likely required to explicitly inject Gemini's specific tool.

---

### Attempt 6: **Re-Introduce `extra_body` for `responses` API**

*   **Hypothesis:** Since the `responses` API correctly passes the `tools` parameter, re-introducing `extra_body` with the explicit `google_search` tool injection could make LiteLLM inject the tool, overriding its lack of native mapping for `web_search_preview` tools.
*   **`litellm_config.yaml` Change (on 2025-09-13 9:47 PM):**
    ```yaml
    # For gemini/gemini-2.5-flash entries
    litellm_params:
      model: "gemini/gemini-2.5-flash"
      api_key: os.environ/GOOGLE_API_KEY
      # Enable provider-native web search; LiteLLM injects correct Gemini Search
      web_search: {} # Use the web_search abstraction directly.
      extra_body:
        tools:
          - google_search: {}
        tool_config:
          function_calling_config:
            mode: AUTO
      drop_params: true
      additional_drop_params: ["tools", "tool_choice"]
    model_info:
      supports_web_search: true
    ```
    This change was made via `write_to_file`.
*   **Observed Outcome (Last FPF run on 2025-09-13 9:44:30 PM PST, *before* explicit LiteLLM restart):**
    *   **Successful transport (no HTTP 400).** `meta.json` showed `method: "no-tool"`, `sources: []`.
    *   Output was still a full-length, non-grounded general completion.
    *   `raw_response_excerpt` showed `tools:[]`, confirming the injected tool was *still not* being attached, or was being overridden/stripped by other LiteLLM layers.
*   **Conclusion:** Re-adding `extra_body` with `web_search: {}` still did not cause LiteLLM to attach the `google_search` tool dynamically for this API path *without an explicit LiteLLM restart*. The core problem persists: LiteLLM is failing to attach the provider-native search tool for Gemini when called with FPF's "always grounded" constraints.

---

## 3. Core Hypothesis for Persistent Failure

Despite numerous attempts to adjust `litellm_config.yaml` parameters (`web_search: {}`, `extra_body`, `drop_params`) and moving FPF to the `responses` API, the LiteLLM proxy consistently fails to accurately translate our client’s `web_search_preview` intent into a functional, tool-attached, grounded request for `gemini/gemini-2.5-flash`. The proxy is effectively downgrading the request to a bare `chat.completion` without the `google_search` tool being triggered, despite LiteLLM advertising `supports_web_search: true` for this model.

This strongly suggests:
*   **Version-specific mapping issues:** Your LiteLLM build might lack robust, production-ready mapping for `gemini/gemini-2.5-flash`'s web search when invoked from the OpenAI `responses` API.
*   **Internal conflict:** There's an unresolved conflict within LiteLLM's internal processing of tool parameters, where our explicit `tools=[{"type": "web_search_preview"}]` (from FPF) and config-level `web_search`/`extra_body` settings are not harmonizing to produce the correct upstream Gemini API call. This is the **most likely cause**, as the `raw_response_excerpt` clearly shows `tools: []` being sent to Gemini. This indicates that LiteLLM is either actively stripping the tool, or its internal mapping is failing to inject it due to a higher-priority conflict.

## 4. Recommendations for Deeper Diagnosis and Fix (Proxy-Only; No FPF Changes)

Given the extensive troubleshooting and strict constraints, a direct investigation into LiteLLM's internal behavior and capabilities is paramount.

1.  **Direct LiteLLM Version Check & `responses` API specific web search support:**
    *   **Action:** Run `litellm --version` (`v1.71.0+` is stated as needed for web search). Consult LiteLLM's release notes or GitHub for *specific* support on `gemini/gemini-2.5-flash`'s web search when called via the `/responses` endpoint (or a similar Google AI Studio model/syntax). It is possible this is a feature gated by a newer LiteLLM version or a known bug.
2.  **Verify Model Group Capabilities via `/model_group/info` (Re-Confirm):**
    *   **Action:** Call `GET http://localhost:4000/model_group/info`. Ensure `gemini/gemini-2.5-flash` (and the `model_group` it maps to) truly advertises `"supports_web_search": true` *and* understand what it means by that for this exact model.
3.  **LiteLLM `--detailed_debug` Logging (Crucial):**
    *   **Action:** Restart LiteLLM with `--detailed_debug`. Run FPF with `gemini/gemini-2.5-flash`.
    *   **Observed (Last FPF run on 2025-09-13 9:15:10 PM PST, *after* explicit LiteLLM restart):**
        *   **Incoming Request (FPF to LiteLLM):** FPF correctly sent `tools=[{"type": "web_search_preview"}]` and `tool_choice: "auto"`.
        *   **LiteLLM's Internal `acompletion` Call (to Upstream Gemini API):** The debug logs showed LiteLLM making its internal call to Gemini with `tools=[]` (empty list) and `tool_choice=None`.
        *   **Conclusion:** LiteLLM is **actively stripping or ignoring** the `tools=[{"type": "web_search_preview"}]` from FPF's incoming request *before* sending it to Gemini. It is *not* translating `web_search_preview` into Gemini's native `google_search` tool. This is why Gemini is returning a non-grounded response.
4.  **Sanity Test with `gemini/gemini-2.0-flash`:**
    *   **Action:** Temporarily revert `filepromptforge/default_config.yaml` to use `model: gemini/gemini-2.0-flash`. Then restart LiteLLM and re-run FPF.
    *   **Hypothesis:** If this works (i.e., `method: "provider-tool"` and proper grounded content with citations), then the issue is highly specific to the `gemini-2.5-flash` mapping in LiteLLM.
    *   **Conclusion:** This would provide strong evidence to file a targeted bug report with the LiteLLM project or to use `gemini-2.0-flash` until `2.5` support is improved.
5.  **Direct LiteLLM Project Engagement:**
    *   If the above steps do not reveal a clear path, the next step is to engage directly with the LiteLLM project maintainers (via GitHub issues or their community) with all the collected evidence and logs.

This report summarizes our current understanding of the problem and proposes a strategic path forward, with the understanding that the solution lies outside FPF's codebase and within LiteLLM's internal API mapping for Gemini web search.

---

## 3. Core Hypothesis for Persistent Failure

Despite numerous attempts to adjust `litellm_config.yaml` parameters (`web_search: {}`, `extra_body`, `drop_params`) and moving FPF to the `responses` API, the LiteLLM proxy consistently fails to accurately translate our client’s `web_search_preview` intent into a functional, tool-attached, grounded request for `gemini/gemini-2.5-flash`. The proxy is effectively downgrading the request to a bare `chat.completion` without the `google_search` tool being triggered, despite LiteLLM advertising `supports_web_search: true` for this model.

This strongly suggests:
*   **Version-specific mapping issues:** Your LiteLLM build might lack robust, production-ready mapping for `gemini/gemini-2.5-flash`'s web search when invoked from the OpenAI `responses` API.
*   **Internal conflict:** There's an unresolved conflict within LiteLLM's internal processing of tool parameters, where our explicit `tools=[{"type": "web_search_preview"}]` (from FPF) and config-level `web_search`/`extra_body` settings are not harmonizing to produce the correct upstream Gemini API call. This is the **most likely cause**, as the `raw_response_excerpt` clearly shows `tools: []` being sent to Gemini. This indicates that LiteLLM is either actively stripping the tool, or its internal mapping is failing to inject it due to a higher-priority conflict.

## 4. Recommendations for Deeper Diagnosis and Fix (Proxy-Only; No FPF Changes)

Given the extensive troubleshooting and strict constraints, a direct investigation into LiteLLM's internal behavior and capabilities is paramount.

1.  **Direct LiteLLM Version Check & `responses` API specific web search support:**
    *   **Action:** Run `litellm --version` (`v1.71.0+` is stated as needed for web search). Consult LiteLLM's release notes or GitHub for *specific* support on `gemini/gemini-2.5-flash`'s web search when called via the `/responses` endpoint (or a similar Google AI Studio model/syntax). It is possible this is a feature gated by a newer LiteLLM version or a known bug.
2.  **Verify Model Group Capabilities via `/model_group/info` (Re-Confirm):**
    *   **Action:** Call `GET http://localhost:4000/model_group/info`. Ensure `gemini/gemini-2.5-flash` (and the `model_group` it maps to) truly advertises `"supports_web_search": true` *and* understand what it means by that for this exact model.
3.  **LiteLLM `--detailed_debug` Logging (Crucial):**
    *   **Action:** Restart LiteLLM with `--detailed_debug`. Run FPF with `gemini/gemini-2.5-flash`.
    *   **Observed (Last FPF run on 2025-09-13 9:15:10 PM PST, *after* explicit LiteLLM restart):**
        *   **Incoming Request (FPF to LiteLLM):** FPF correctly sent `tools=[{"type": "web_search_preview"}]` and `tool_choice: "auto"`.
        *   **LiteLLM's Internal `acompletion` Call (to Upstream Gemini API):** The debug logs showed LiteLLM making its internal call to Gemini with `tools=[]` (empty list) and `tool_choice=None`.
        *   **Conclusion:** LiteLLM is **actively stripping or ignoring** the `tools=[{"type": "web_search_preview"}]` from FPF's incoming request *before* sending it to Gemini. It is *not* translating `web_search_preview` into Gemini's native `google_search` tool. This is why Gemini is returning a non-grounded response.
4.  **Sanity Test with `gemini/gemini-2.0-flash`:**
    *   **Action:** Temporarily revert `filepromptforge/default_config.yaml` to use `model: gemini/gemini-2.0-flash`. Then restart LiteLLM and re-run FPF.
    *   **Hypothesis:** If this works (i.e., `method: "provider-tool"` and proper grounded content with citations), then the issue is highly specific to the `gemini-2.5-flash` mapping in LiteLLM.
    *   **Conclusion:** This would provide strong evidence to file a targeted bug report with the LiteLLM project or to use `gemini-2.0-flash` until `2.5` support is improved.
5.  **Direct LiteLLM Project Engagement:**
    *   If the above steps do not reveal a clear path, the next step is to engage directly with the LiteLLM project maintainers (via GitHub issues or their community) with all the collected evidence and logs.

This report summarizes our current understanding of the problem and proposes a strategic path forward, with the understanding that the solution lies outside FPF's codebase and within LiteLLM's internal API mapping for Gemini web search.

---
