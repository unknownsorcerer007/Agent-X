/**
 * llm-bridge.ts — LLM Bridge Module
 *
 * Uses the user's connected tool's LLM (z-ai-web-dev-sdk) for all AI operations.
 * No separate LLM is added — whatever tool the user connects to, that LLM is used.
 *
 * Provides:
 * - complete(): General text completion
 * - classify(): Text classification with categories
 * - extract(): Structured data extraction from text/HTML
 * - summarize(): Text summarization
 * - reasonAboutPage(): Analyze page content for reasoning
 * - planFormFill(): Plan form filling strategy
 * - planSwarmQuery(): Decompose and plan swarm queries
 *
 * Gracefully degrades when SDK is unavailable — returns fallback results
 * with a `usedLLM: false` flag so callers know LLM was not used.
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LLMResult {
  success: boolean;
  content: string;
  usedLLM: boolean;
  error?: string;
  tokensUsed?: number;
}

export interface ClassificationResult {
  category: string;
  confidence: number;
  reasoning: string;
  usedLLM: boolean;
}

export interface ExtractionResult {
  data: Record<string, any>;
  usedLLM: boolean;
  error?: string;
}

export interface SummaryResult {
  summary: string;
  originalLength: number;
  summaryLength: number;
  compressionRatio: number;
  usedLLM: boolean;
}

export interface SwarmPlan {
  subQueries: Array<{
    query: string;
    reasoning: string;
    priority: number;
    searchEngine: string;
  }>;
  overallStrategy: string;
  usedLLM: boolean;
}

export interface FormPlan {
  fields: Array<{
    name: string;
    value: string;
    strategy: string;
    confidence: number;
  }>;
  submitStrategy: string;
  multiPage: boolean;
  nextPageIndicator: string;
  usedLLM: boolean;
}

// ─── ZAI SDK Singleton ───────────────────────────────────────────────────────

let zaiInstance: any = null;
let zaiInitPromise: Promise<any> | null = null;
let zaiAvailable: boolean | null = null;

async function getZAI(): Promise<any> {
  if (zaiInstance) return zaiInstance;
  if (zaiInitPromise) return zaiInitPromise;

  zaiInitPromise = (async () => {
    try {
      const ZAI = (await import("z-ai-web-dev-sdk")).default;
      zaiInstance = await ZAI.create();
      zaiAvailable = true;
      console.log("[LLMBridge] z-ai-web-dev-sdk initialized successfully");
      return zaiInstance;
    } catch (err: any) {
      zaiAvailable = false;
      console.warn("[LLMBridge] z-ai-web-dev-sdk not available, LLM features will use heuristic fallback:", err.message || err);
      return null;
    }
  })();

  return zaiInitPromise;
}

// ─── Core LLM Methods ────────────────────────────────────────────────────────

/**
 * Send a completion request to the LLM.
 * Returns the text response or a fallback message.
 * Never throws — always returns an LLMResult.
 */
export async function complete(
  prompt: string,
  systemPrompt?: string
): Promise<LLMResult> {
  try {
    const zai = await getZAI();
    if (!zai) {
      return {
        success: false,
        content: "",
        usedLLM: false,
        error: "LLM SDK not available",
      };
    }

    const messages: Array<{ role: string; content: string }> = [];
    if (systemPrompt) {
      messages.push({ role: "assistant", content: systemPrompt });
    }
    messages.push({ role: "user", content: prompt });

    // Add a 30-second timeout to prevent hanging
    const completionPromise = zai.chat.completions.create({
      messages,
      thinking: { type: "disabled" },
    });

    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error("LLM request timed out after 30s")), 30000);
    });

    const completion = await Promise.race([completionPromise, timeoutPromise]);

    const content = completion.choices?.[0]?.message?.content || "";
    return {
      success: true,
      content,
      usedLLM: true,
      tokensUsed: completion.usage?.total_tokens,
    };
  } catch (err: any) {
    console.error("[LLMBridge] complete() failed:", err.message || err);
    return {
      success: false,
      content: "",
      usedLLM: false,
      error: err.message || String(err),
    };
  }
}

/**
 * Classify text into one of the given categories using LLM.
 * Falls back to keyword matching if LLM unavailable.
 */
export async function classify(
  text: string,
  categories: string[]
): Promise<ClassificationResult> {
  const zai = await getZAI();
  if (!zai) {
    // Heuristic fallback: keyword matching
    const lower = text.toLowerCase();
    const scores: Record<string, number> = {};
    for (const cat of categories) {
      const keywords = cat.toLowerCase().split(/[_\s-]+/);
      scores[cat] = keywords.reduce((score, kw) => score + (lower.includes(kw) ? 1 : 0), 0);
    }
    const best = categories.reduce((a, b) => (scores[a] || 0) >= (scores[b] || 0) ? a : b, categories[0]);
    return {
      category: best,
      confidence: Math.min((scores[best] || 0) / 3, 1),
      reasoning: "Heuristic keyword matching (LLM unavailable)",
      usedLLM: false,
    };
  }

  try {
    const prompt = `Classify the following text into exactly one of these categories: ${categories.join(", ")}

Text:
"""
${text.substring(0, 4000)}
"""

Respond with ONLY a JSON object in this exact format:
{"category": "<chosen_category>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}`;

    const result = await complete(prompt, "You are a precise text classifier. Always respond with valid JSON only.");
    if (!result.success || !result.content) {
      return {
        category: categories[0],
        confidence: 0,
        reasoning: "LLM call failed: " + (result.error || "empty response"),
        usedLLM: false,
      };
    }

    // Try to parse JSON from response
    try {
      const jsonMatch = result.content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return {
          category: parsed.category || categories[0],
          confidence: typeof parsed.confidence === "number" ? parsed.confidence : 0.5,
          reasoning: parsed.reasoning || "LLM classification",
          usedLLM: true,
        };
      }
    } catch (parseErr: any) {
      console.warn("[LLMBridge] classify() JSON parse failed:", parseErr.message);
    }

    // Try to match category from plain text response
    const lowerContent = result.content.toLowerCase();
    for (const cat of categories) {
      if (lowerContent.includes(cat.toLowerCase())) {
        return {
          category: cat,
          confidence: 0.7,
          reasoning: "Extracted from LLM text response",
          usedLLM: true,
        };
      }
    }

    return {
      category: categories[0],
      confidence: 0.3,
      reasoning: "Could not parse LLM response",
      usedLLM: true,
    };
  } catch (err: any) {
    console.error("[LLMBridge] classify() error:", err.message || err);
    return {
      category: categories[0],
      confidence: 0,
      reasoning: "Error: " + (err.message || String(err)),
      usedLLM: false,
    };
  }
}

/**
 * Extract structured data from text/HTML using LLM.
 * Falls back to regex/DOM parsing if LLM unavailable.
 */
export async function extract(
  content: string,
  schema: Record<string, string>
): Promise<ExtractionResult> {
  const zai = await getZAI();
  if (!zai) {
    // Heuristic fallback: basic regex extraction
    const data: Record<string, any> = {};
    for (const [key, type] of Object.entries(schema)) {
      if (type === "email") {
        const match = content.match(/[\w.-]+@[\w.-]+\.\w+/);
        data[key] = match ? match[0] : null;
      } else if (type === "url") {
        const match = content.match(/https?:\/\/[^\s"'<>]+/);
        data[key] = match ? match[0] : null;
      } else if (type === "number" || type === "price") {
        const match = content.match(/[\$€£]?\d+[.,]?\d*/);
        data[key] = match ? match[0] : null;
      } else if (type === "date") {
        const match = content.match(/\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}/);
        data[key] = match ? match[0] : null;
      } else if (type === "phone") {
        const match = content.match(/[+]?[\d\s()-]{7,}/);
        data[key] = match ? match[0].trim() : null;
      } else {
        data[key] = null;
      }
    }
    return { data, usedLLM: false };
  }

  try {
    const schemaStr = Object.entries(schema)
      .map(([k, v]) => `  "${k}": "${v}"`)
      .join(",\n");

    const prompt = `Extract structured data from the following content according to this schema:
{
${schemaStr}
}

Content:
"""
${content.substring(0, 6000)}
"""

Respond with ONLY a valid JSON object matching the schema. Use null for fields you cannot find.`;

    const result = await complete(prompt, "You are a precise data extraction assistant. Always respond with valid JSON only. No markdown, no explanation, just the JSON object.");
    if (!result.success || !result.content) {
      return {
        data: {},
        usedLLM: false,
        error: "LLM extraction failed: " + (result.error || "empty response"),
      };
    }

    try {
      const jsonMatch = result.content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        return { data: parsed, usedLLM: true };
      }
    } catch (parseErr: any) {
      console.warn("[LLMBridge] extract() JSON parse failed:", parseErr.message);
    }

    return {
      data: {},
      usedLLM: true,
      error: "Could not parse LLM extraction response",
    };
  } catch (err: any) {
    console.error("[LLMBridge] extract() error:", err.message || err);
    return {
      data: {},
      usedLLM: false,
      error: err.message || String(err),
    };
  }
}

/**
 * Summarize text using LLM.
 * Falls back to truncation if LLM unavailable.
 */
export async function summarize(
  text: string,
  maxSentences: number = 5
): Promise<SummaryResult> {
  const originalLength = text.length;
  const zai = await getZAI();

  if (!zai) {
    // Heuristic fallback: extract first N sentences
    const sentences = text.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 10);
    const summary = sentences.slice(0, maxSentences).join(" ");
    return {
      summary,
      originalLength,
      summaryLength: summary.length,
      compressionRatio: originalLength > 0 ? summary.length / originalLength : 1,
      usedLLM: false,
    };
  }

  try {
    const prompt = `Summarize the following text in at most ${maxSentences} sentences. Capture the key information concisely.

Text:
"""
${text.substring(0, 8000)}
"""

Summary:`;

    const result = await complete(prompt, "You are a concise summarizer. Provide clear, factual summaries without filler.");
    if (!result.success || !result.content) {
      // Fall back to truncation
      const truncated = text.substring(0, 500) + "...";
      return {
        summary: truncated,
        originalLength,
        summaryLength: truncated.length,
        compressionRatio: originalLength > 0 ? truncated.length / originalLength : 1,
        usedLLM: false,
      };
    }

    return {
      summary: result.content.trim(),
      originalLength,
      summaryLength: result.content.length,
      compressionRatio: originalLength > 0 ? result.content.length / originalLength : 1,
      usedLLM: true,
    };
  } catch (err: any) {
    console.error("[LLMBridge] summarize() error:", err.message || err);
    const truncated = text.substring(0, 500) + "...";
    return {
      summary: truncated,
      originalLength,
      summaryLength: truncated.length,
      compressionRatio: originalLength > 0 ? truncated.length / originalLength : 1,
      usedLLM: false,
    };
  }
}

/**
 * Analyze page content for intelligent reasoning about what to do next.
 * Used by agent swarm and form filling to make decisions.
 */
export async function reasonAboutPage(
  pageTitle: string,
  pageUrl: string,
  pageText: string,
  accessibilityTree: string,
  goal: string
): Promise<LLMResult> {
  const zai = await getZAI();
  if (!zai) {
    return {
      success: false,
      content: JSON.stringify({
        action: "proceed",
        reasoning: "LLM unavailable, proceeding with default behavior",
        nextSteps: ["Take a snapshot", "Look for form fields", "Fill and submit"],
      }),
      usedLLM: false,
    };
  }

  const prompt = `You are an intelligent browser automation agent. Analyze the current page state and determine what to do next to achieve the user's goal.

GOAL: ${goal}

CURRENT PAGE:
- Title: ${pageTitle}
- URL: ${pageUrl}
- Text content (first 3000 chars): ${pageText.substring(0, 3000)}
- Accessibility tree (first 2000 chars): ${accessibilityTree.substring(0, 2000)}

Based on the page state and the goal, respond with ONLY a JSON object:
{
  "action": "fill_form" | "click_element" | "navigate" | "wait" | "handover_to_user" | "task_complete" | "error",
  "reasoning": "<explain why you chose this action>",
  "nextSteps": ["<step 1>", "<step 2>", ...],
  "elementToInteract": "<description of element to click/fill, if applicable>",
  "valueToFill": "<value to fill, if applicable>",
  "urlToNavigate": "<URL to navigate to, if applicable>",
  "waitReason": "<reason to wait, if applicable>"
}`;

  return complete(prompt, "You are an intelligent browser automation agent. Always respond with valid JSON only. Analyze the page carefully and choose the best action to achieve the user's goal.");
}

/**
 * Plan a form filling strategy using LLM.
 * Takes the page content and desired form data, returns a plan.
 */
export async function planFormFill(
  pageText: string,
  accessibilityTree: string,
  desiredData: Record<string, string>
): Promise<FormPlan> {
  const zai = await getZAI();
  if (!zai) {
    // Heuristic fallback: direct field mapping
    const fields = Object.entries(desiredData).map(([name, value]) => ({
      name,
      value,
      strategy: "match_by_name_placeholder",
      confidence: 0.5,
    }));
    return {
      fields,
      submitStrategy: "find_submit_button",
      multiPage: false,
      nextPageIndicator: "",
      usedLLM: false,
    };
  }

  const prompt = `You are a form filling expert. Analyze the page and plan how to fill the form with the given data.

DESIRED DATA:
${JSON.stringify(desiredData, null, 2)}

PAGE TEXT (first 2000 chars):
${pageText.substring(0, 2000)}

ACCESSIBILITY TREE (first 2000 chars):
${accessibilityTree.substring(0, 2000)}

Respond with ONLY a JSON object:
{
  "fields": [
    {
      "name": "<field name from desired data>",
      "value": "<value to fill>",
      "strategy": "match_by_label" | "match_by_placeholder" | "match_by_name_attr" | "match_by_aria" | "match_by_position" | "click_dropdown_option",
      "confidence": <0.0-1.0>
    }
  ],
  "submitStrategy": "click_submit_button" | "press_enter" | "js_submit" | "no_submit",
  "multiPage": <true if this is a multi-step form>,
  "nextPageIndicator": "<text or element that indicates next page, or ''>"
}`;

  const result = await complete(prompt, "You are a form filling expert. Always respond with valid JSON only.");
  if (!result.success || !result.content) {
    const fields = Object.entries(desiredData).map(([name, value]) => ({
      name, value, strategy: "match_by_name_placeholder", confidence: 0.3,
    }));
    return { fields, submitStrategy: "find_submit_button", multiPage: false, nextPageIndicator: "", usedLLM: false };
  }

  try {
    const jsonMatch = result.content.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      return {
        fields: parsed.fields || [],
        submitStrategy: parsed.submitStrategy || "find_submit_button",
        multiPage: parsed.multiPage || false,
        nextPageIndicator: parsed.nextPageIndicator || "",
        usedLLM: true,
      };
    }
  } catch (parseErr: any) {
    console.warn("[LLMBridge] planFormFill() JSON parse failed:", parseErr.message);
  }

  const fields = Object.entries(desiredData).map(([name, value]) => ({
    name, value, strategy: "match_by_name_placeholder", confidence: 0.3,
  }));
  return { fields, submitStrategy: "find_submit_button", multiPage: false, nextPageIndicator: "", usedLLM: false };
}

/**
 * Plan a swarm search query decomposition using LLM.
 * Takes a complex query and breaks it into intelligent sub-queries.
 */
export async function planSwarmQuery(
  query: string,
  maxAgents: number = 10
): Promise<SwarmPlan> {
  const zai = await getZAI();
  if (!zai) {
    // Heuristic fallback: simple query splitting
    const words = query.split(/\s+/);
    const subQueries = [];
    const strategies = [
      `What is ${query}?`,
      `${query} latest news 2024`,
      `${query} reviews comparison`,
      `${query} tutorial guide`,
      `${query} best practices`,
    ];
    for (let i = 0; i < Math.min(maxAgents, strategies.length); i++) {
      subQueries.push({
        query: strategies[i],
        reasoning: `Heuristic reformulation ${i + 1}`,
        priority: maxAgents - i,
        searchEngine: "google",
      });
    }
    return {
      subQueries,
      overallStrategy: "Parallel search with heuristic query reformulation (LLM unavailable)",
      usedLLM: false,
    };
  }

  const prompt = `You are a search strategy expert. Break down the following query into ${maxAgents} or fewer intelligent sub-queries that together will provide comprehensive results.

ORIGINAL QUERY: ${query}

For each sub-query, think about:
- Different aspects/perspectives of the topic
- Current vs historical information
- Technical vs general audience
- Different sources/angles

Respond with ONLY a JSON object:
{
  "subQueries": [
    {
      "query": "<search query string>",
      "reasoning": "<why this query will help>",
      "priority": <1-10>,
      "searchEngine": "google" | "bing" | "duckduckgo"
    }
  ],
  "overallStrategy": "<explain the overall search strategy>"
}`;

  const result = await complete(prompt, "You are a search strategy expert. Always respond with valid JSON only. Create diverse, intelligent sub-queries that cover different aspects of the topic.");
  if (!result.success || !result.content) {
    // Fallback
    const subQueries = [{
      query, reasoning: "Original query (LLM unavailable)", priority: 10, searchEngine: "google",
    }];
    return { subQueries, overallStrategy: "Single query fallback (LLM unavailable)", usedLLM: false };
  }

  try {
    const jsonMatch = result.content.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      return {
        subQueries: (parsed.subQueries || []).slice(0, maxAgents),
        overallStrategy: parsed.overallStrategy || "LLM-planned multi-perspective search",
        usedLLM: true,
      };
    }
  } catch (parseErr: any) {
    console.warn("[LLMBridge] planSwarmQuery() JSON parse failed:", parseErr.message);
  }

  const subQueries = [{
    query, reasoning: "Original query (parse failed)", priority: 10, searchEngine: "google",
  }];
  return { subQueries, overallStrategy: "Single query fallback", usedLLM: false };
}

/**
 * Check if the LLM is available.
 */
export async function isLLMAvailable(): Promise<boolean> {
  if (zaiAvailable !== null) return zaiAvailable;
  const zai = await getZAI();
  return zai !== null;
}

/**
 * Get LLM status info.
 */
export async function getLLMStatus(): Promise<{
  available: boolean;
  provider: string;
  model: string;
}> {
  const available = await isLLMAvailable();
  return {
    available,
    provider: available ? "z-ai-web-dev-sdk" : "none",
    model: available ? "configured-model" : "none",
  };
}
