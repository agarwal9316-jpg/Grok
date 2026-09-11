package com.grokorg.desk.server

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * OpenAI-compatible chat client with mock fallback (mirrors Python llm.py).
 */
class LlmClient(
    var apiKey: String = "",
    var baseUrl: String = "https://api.openai.com/v1",
    var model: String = "gpt-4o-mini",
) {
    val useMock: Boolean
        get() = apiKey.isBlank()

    fun chat(messages: List<Map<String, String>>, temperature: Double = 0.4, maxTokens: Int = 1024): String {
        if (useMock) return mockResponse(messages)
        return try {
            val url = URL("${baseUrl.trimEnd('/')}/chat/completions")
            val payload = JSONObject().apply {
                put("model", model)
                put("temperature", temperature)
                put("max_tokens", maxTokens)
                put("messages", JSONArray().also { arr ->
                    messages.forEach { m ->
                        arr.put(JSONObject().put("role", m["role"]).put("content", m["content"]))
                    }
                })
            }
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 60_000
                readTimeout = 60_000
                doOutput = true
                setRequestProperty("Authorization", "Bearer $apiKey")
                setRequestProperty("Content-Type", "application/json")
            }
            conn.outputStream.bufferedWriter().use { it.write(payload.toString()) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                Log.w(TAG, "LLM HTTP $code: $text")
                return mockResponse(messages)
            }
            val json = JSONObject(text)
            json.getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content")
        } catch (e: Exception) {
            Log.w(TAG, "LLM call failed; mock fallback", e)
            mockResponse(messages)
        }
    }

    private fun roleHint(system: String): String {
        val s = system.lowercase()
        if ("chief of staff" in s) return "chief_of_staff"
        if ("ceo" in s && "chief" !in s) return "ceo"
        if ("you are an ops" in s || "you are the ops" in s || s.startsWith("ops ")) return "ops"
        if ("you are a research" in s || "you are the research" in s) return "research"
        if ("you are a comms" in s || "you are the comms" in s) return "comms"
        if ("ops specialist" in s || ("operations" in s && "specialist" in s)) return "ops"
        if ("research specialist" in s) return "research"
        if ("comms specialist" in s || "communication specialist" in s) return "comms"
        return "generic"
    }

    private fun mockResponse(messages: List<Map<String, String>>): String {
        val userBits = messages.filter { it["role"] == "user" }.mapNotNull { it["content"] }
        val systemBits = messages.filter { it["role"] == "system" }.mapNotNull { it["content"] }
        val lastUser = userBits.lastOrNull().orEmpty()
        val system = systemBits.joinToString(" ")
        val lower = lastUser.lowercase()
        val role = roleHint(system)

        when (role) {
            "ops" -> return "[Ops Specialist] Operational assessment complete. " +
                "Resources are available; recommend proceeding with a phased rollout. " +
                "Context considered: ${lastUser.take(180)}"
            "research" -> return "[Research Specialist] Research summary: key findings support the objective. " +
                "Recommend validating assumptions with a short pilot. " +
                "Query: ${lastUser.take(180)}"
            "comms" -> return "[Comms Specialist] Draft update for stakeholders:\n" +
                "We have coordinated Ops and Research inputs and are ready to share a concise plan. " +
                "Subject: ${lastUser.take(120)}"
            "ceo" -> return "[CEO] Direction acknowledged. Proceed with the plan."
            "chief_of_staff" -> {
                if ("synthesize" in lower) {
                    return "[Chief of Staff] Coordination complete. Subtasks executed; synthesizing " +
                        "results into an executive brief for the CEO. Recommendation: proceed with " +
                        "the phased pilot, validate via Research, and publish the Comms brief."
                }
                if ("decompose" in lower || "break down" in lower || "subtask" in lower) {
                    return "DECOMPOSE:\n" +
                        "1. [Ops] Assess operational readiness and constraints\n" +
                        "2. [Research] Gather relevant background and options\n" +
                        "3. [Comms] Draft a clear stakeholder summary\n" +
                        "ASSIGN each subtask to the matching specialist team."
                }
                return "[Chief of Staff] Acknowledged. Coordinating Ops, Research, and Comms now."
            }
        }

        if ("decompose" in lower || "break down" in lower) {
            return "DECOMPOSE:\n" +
                "1. [Ops] Assess operational readiness and constraints\n" +
                "2. [Research] Gather relevant background and options\n" +
                "3. [Comms] Draft a clear stakeholder summary\n" +
                "ASSIGN each subtask to the matching specialist team."
        }
        if ("synthesize" in lower) {
            return "[Chief of Staff] Coordination complete. Subtasks executed; synthesizing " +
                "results into an executive brief for the CEO."
        }
        return "[Mock LLM] Processed request with ${messages.size} message(s). " +
            "Response regarding: ${lastUser.take(240).ifBlank { "general task" }}"
    }

    companion object {
        private const val TAG = "LlmClient"
    }
}
