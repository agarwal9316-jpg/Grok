package com.grokorg.desk.server

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.TimeZone
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException

/**
 * SQLite-backed store mirroring Python models + bootstrap.
 */
class OrgStore(context: Context) {
    private val appContext = context.applicationContext
    private val dbHelper = DbHelper(appContext)
    val llm = LlmClient()

    init {
        loadLlmSettings()
    }

    fun db(): SQLiteDatabase = dbHelper.writableDatabase

    fun nowIso(): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        return fmt.format(Date())
    }

    // ---- settings ----

    fun getSetting(key: String, default: String = ""): String {
        db().rawQuery("SELECT value FROM app_settings WHERE key=?", arrayOf(key)).use { c ->
            return if (c.moveToFirst()) c.getString(0) else default
        }
    }

    fun setSetting(key: String, value: String) {
        val cv = ContentValues().apply {
            put("key", key)
            put("value", value)
        }
        db().insertWithOnConflict("app_settings", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun normalizeBaseUrl(url: String): String {
        var u = url.trim().trimEnd('/')
        if (u.isBlank()) return "https://api.openai.com/v1"
        val lower = u.lowercase()
        if (lower.endsWith("/v1") || lower.contains("/v1/") || lower.endsWith("/v1beta") || lower.contains("/openai/deployments")) {
            return u
        }
        val markers = listOf(
            "api.openai.com",
            "openrouter.ai/api",
            "api.groq.com/openai",
            "api.together.xyz",
            "api.fireworks.ai/inference",
            "integrate.api.nvidia.com",
            "api.deepseek.com",
            "api.mistral.ai",
        )
        for (h in markers) {
            if (lower.endsWith(h) || lower.contains("://$h")) {
                return "$u/v1"
            }
        }
        try {
            val parsed = URL(if ("://" in u) u else "https://$u")
            val path = (parsed.path ?: "").trimEnd('/')
            if (path.isEmpty() || path == "/api") return "$u/v1"
        } catch (_: Exception) {
        }
        return u
    }

    fun loadLlmSettings() {
        llm.apiKey = getSetting("openai_api_key", "")
        llm.baseUrl = normalizeBaseUrl(getSetting("openai_base_url", "https://api.openai.com/v1"))
        llm.model = getSetting("openai_model", "gpt-4o-mini")
    }

    fun configJson(): JSONObject {
        loadLlmSettings()
        val hasKey = llm.apiKey.isNotBlank()
        return JSONObject()
            .put("openai_base_url", llm.baseUrl)
            .put("openai_model", llm.model)
            .put("api_key_set", hasKey)
            .put("has_llm_key", hasKey)
            .put("use_mock", !hasKey)
            .put("database_url", "sqlite:///grok_org_os.db")
            .put("host", "127.0.0.1")
            .put("port", LocalBackend.DEFAULT_PORT)
            .put("version", "2.1.4")
            .put("workspace_dir", "workspace")
    }

    fun updateSettings(body: JSONObject): JSONObject {
        if (body.has("openai_api_key") && !body.isNull("openai_api_key")) {
            setSetting("openai_api_key", body.getString("openai_api_key"))
        }
        if (body.has("openai_base_url") && !body.isNull("openai_base_url")) {
            val v = normalizeBaseUrl(body.getString("openai_base_url"))
            if (v.isNotEmpty()) setSetting("openai_base_url", v)
        }
        if (body.has("openai_model") && !body.isNull("openai_model")) {
            val v = body.getString("openai_model").trim()
            if (v.isNotEmpty()) setSetting("openai_model", v)
        }
        loadLlmSettings()
        return configJson()
    }

    // ---- helpers ----

    private fun cursorToJson(c: Cursor, vararg cols: String): JSONObject {
        val o = JSONObject()
        for (col in cols) {
            val idx = c.getColumnIndex(col)
            if (idx < 0) continue
            when (c.getType(idx)) {
                Cursor.FIELD_TYPE_NULL -> o.put(col, JSONObject.NULL)
                Cursor.FIELD_TYPE_INTEGER -> {
                    if (col == "is_human") o.put(col, c.getInt(idx) != 0)
                    else o.put(col, c.getLong(idx))
                }
                else -> {
                    val s = c.getString(idx)
                    if (s == null) o.put(col, JSONObject.NULL) else o.put(col, s)
                }
            }
        }
        return o
    }

    private fun queryList(sql: String, args: Array<String>?, mapper: (Cursor) -> JSONObject): JSONArray {
        val arr = JSONArray()
        db().rawQuery(sql, args).use { c ->
            while (c.moveToNext()) arr.put(mapper(c))
        }
        return arr
    }

    private fun queryOne(sql: String, args: Array<String>?, mapper: (Cursor) -> JSONObject): JSONObject? {
        db().rawQuery(sql, args).use { c ->
            return if (c.moveToFirst()) mapper(c) else null
        }
    }

    // ---- organisations ----

    fun listOrgs(): JSONArray = queryList(
        "SELECT * FROM organisations ORDER BY id", null
    ) { cursorToJson(it, "id", "name", "description", "created_at") }

    fun getOrg(id: Long): JSONObject? = queryOne(
        "SELECT * FROM organisations WHERE id=?", arrayOf(id.toString())
    ) { cursorToJson(it, "id", "name", "description", "created_at") }

    fun createOrg(name: String, description: String?): JSONObject {
        val now = nowIso()
        val cv = ContentValues().apply {
            put("name", name)
            put("description", description)
            put("created_at", now)
        }
        val id = db().insertOrThrow("organisations", null, cv)
        return getOrg(id)!!
    }

    fun orgCount(): Int {
        db().rawQuery("SELECT COUNT(*) FROM organisations", null).use { c ->
            c.moveToFirst()
            return c.getInt(0)
        }
    }

    // ---- teams ----

    fun listTeams(orgId: Long?): JSONArray {
        val sql = if (orgId != null)
            "SELECT * FROM teams WHERE organisation_id=? ORDER BY id"
        else "SELECT * FROM teams ORDER BY id"
        val args = if (orgId != null) arrayOf(orgId.toString()) else null
        return queryList(sql, args) {
            cursorToJson(it, "id", "organisation_id", "name", "description", "created_at")
        }
    }

    fun getTeam(id: Long): JSONObject? = queryOne(
        "SELECT * FROM teams WHERE id=?", arrayOf(id.toString())
    ) { cursorToJson(it, "id", "organisation_id", "name", "description", "created_at") }

    fun createTeam(orgId: Long, name: String, description: String?): JSONObject {
        val cv = ContentValues().apply {
            put("organisation_id", orgId)
            put("name", name)
            put("description", description)
            put("created_at", nowIso())
        }
        val id = db().insertOrThrow("teams", null, cv)
        return getTeam(id)!!
    }

    fun findTeam(orgId: Long, name: String): JSONObject? = queryOne(
        "SELECT * FROM teams WHERE organisation_id=? AND name=?",
        arrayOf(orgId.toString(), name)
    ) { cursorToJson(it, "id", "organisation_id", "name", "description", "created_at") }

    // ---- agents ----

    fun listAgents(orgId: Long?): JSONArray {
        val sql = if (orgId != null)
            "SELECT * FROM agents WHERE organisation_id=? ORDER BY id"
        else "SELECT * FROM agents ORDER BY id"
        val args = if (orgId != null) arrayOf(orgId.toString()) else null
        return queryList(sql, args) {
            cursorToJson(
                it, "id", "organisation_id", "team_id", "name", "role",
                "is_human", "system_prompt", "created_at"
            )
        }
    }

    fun getAgent(id: Long): JSONObject? = queryOne(
        "SELECT * FROM agents WHERE id=?", arrayOf(id.toString())
    ) {
        cursorToJson(
            it, "id", "organisation_id", "team_id", "name", "role",
            "is_human", "system_prompt", "status", "created_at"
        )
    }

    fun createAgent(
        orgId: Long,
        name: String,
        role: String,
        teamId: Long? = null,
        isHuman: Boolean = false,
        systemPrompt: String? = null,
    ): JSONObject {
        val cv = ContentValues().apply {
            put("organisation_id", orgId)
            if (teamId != null) put("team_id", teamId) else putNull("team_id")
            put("name", name)
            put("role", role)
            put("is_human", if (isHuman) 1 else 0)
            put("system_prompt", systemPrompt)
            put("created_at", nowIso())
        }
        val id = db().insertOrThrow("agents", null, cv)
        return getAgent(id)!!
    }

    fun findAgent(orgId: Long, name: String): JSONObject? = queryOne(
        "SELECT * FROM agents WHERE organisation_id=? AND name=?",
        arrayOf(orgId.toString(), name)
    ) {
        cursorToJson(
            it, "id", "organisation_id", "team_id", "name", "role",
            "is_human", "system_prompt", "status", "created_at"
        )
    }

    fun listSpecialists(orgId: Long): List<JSONObject> {
        val list = mutableListOf<JSONObject>()
        db().rawQuery(
            "SELECT * FROM agents WHERE organisation_id=? AND role='specialist' AND is_human=0 ORDER BY id",
            arrayOf(orgId.toString())
        ).use { c ->
            while (c.moveToNext()) {
                list.add(
                    cursorToJson(
                        c, "id", "organisation_id", "team_id", "name", "role",
                        "is_human", "system_prompt", "status", "created_at"
                    )
                )
            }
        }
        return list
    }

    // ---- channels ----

    fun listChannels(orgId: Long?): JSONArray {
        val sql = if (orgId != null)
            "SELECT * FROM channels WHERE organisation_id=? ORDER BY id"
        else "SELECT * FROM channels ORDER BY id"
        val args = if (orgId != null) arrayOf(orgId.toString()) else null
        return queryList(sql, args) {
            cursorToJson(it, "id", "organisation_id", "name", "description", "created_at")
        }
    }

    fun getChannel(id: Long): JSONObject? = queryOne(
        "SELECT * FROM channels WHERE id=?", arrayOf(id.toString())
    ) { cursorToJson(it, "id", "organisation_id", "name", "description", "created_at") }

    fun createChannel(orgId: Long, name: String, description: String?): JSONObject {
        val cv = ContentValues().apply {
            put("organisation_id", orgId)
            put("name", name)
            put("description", description)
            put("created_at", nowIso())
        }
        val id = db().insertOrThrow("channels", null, cv)
        return getChannel(id)!!
    }

    fun findChannel(orgId: Long, name: String): JSONObject? = queryOne(
        "SELECT * FROM channels WHERE organisation_id=? AND name=?",
        arrayOf(orgId.toString(), name)
    ) { cursorToJson(it, "id", "organisation_id", "name", "description", "created_at") }

    // ---- messages ----

    fun listMessages(channelId: Long?): JSONArray {
        val sql = if (channelId != null)
            """
            SELECT m.*, a.name AS agent_name, a.role AS agent_role
            FROM messages m JOIN agents a ON a.id = m.agent_id
            WHERE m.channel_id=? ORDER BY m.id
            """.trimIndent()
        else
            """
            SELECT m.*, a.name AS agent_name, a.role AS agent_role
            FROM messages m JOIN agents a ON a.id = m.agent_id
            ORDER BY m.id
            """.trimIndent()
        val args = if (channelId != null) arrayOf(channelId.toString()) else null
        return queryList(sql, args) {
            cursorToJson(
                it, "id", "channel_id", "agent_id", "content", "parent_id", "created_at",
                "agent_name", "agent_role"
            )
        }
    }

    fun createMessage(channelId: Long, agentId: Long, content: String, parentId: Long? = null): JSONObject {
        val cv = ContentValues().apply {
            put("channel_id", channelId)
            put("agent_id", agentId)
            put("content", content)
            if (parentId != null) put("parent_id", parentId) else putNull("parent_id")
            put("created_at", nowIso())
        }
        val id = db().insertOrThrow("messages", null, cv)
        return queryOne(
            """
            SELECT m.*, a.name AS agent_name, a.role AS agent_role
            FROM messages m JOIN agents a ON a.id = m.agent_id
            WHERE m.id=?
            """.trimIndent(),
            arrayOf(id.toString())
        ) {
            cursorToJson(
                it, "id", "channel_id", "agent_id", "content", "parent_id", "created_at",
                "agent_name", "agent_role"
            )
        }!!
    }

    fun messageCount(channelId: Long): Int {
        db().rawQuery(
            "SELECT COUNT(*) FROM messages WHERE channel_id=?",
            arrayOf(channelId.toString())
        ).use { c ->
            c.moveToFirst()
            return c.getInt(0)
        }
    }

    // ---- tasks ----

    fun listTasks(orgId: Long?, status: String? = null): JSONArray {
        val clauses = mutableListOf<String>()
        val args = mutableListOf<String>()
        if (orgId != null) {
            clauses += "organisation_id=?"
            args += orgId.toString()
        }
        if (status != null) {
            clauses += "status=?"
            args += status
        }
        val where = if (clauses.isEmpty()) "" else "WHERE " + clauses.joinToString(" AND ")
        return queryList("SELECT * FROM tasks $where ORDER BY id", args.toTypedArray()) {
            taskFromCursor(it)
        }
    }

    fun getTask(id: Long): JSONObject? = queryOne(
        "SELECT * FROM tasks WHERE id=?", arrayOf(id.toString())
    ) { taskFromCursor(it) }

    private fun taskFromCursor(c: Cursor): JSONObject =
        cursorToJson(
            c, "id", "organisation_id", "title", "description", "status",
            "assignee_id", "channel_id", "parent_task_id", "result",
            "created_at", "updated_at"
        )

    fun createTask(
        orgId: Long,
        title: String,
        description: String?,
        status: String = "pending",
        assigneeId: Long? = null,
        channelId: Long? = null,
        parentTaskId: Long? = null,
        result: String? = null,
    ): JSONObject {
        val now = nowIso()
        var st = status
        if (assigneeId != null && st == "pending") st = "assigned"
        val cv = ContentValues().apply {
            put("organisation_id", orgId)
            put("title", title)
            put("description", description)
            put("status", st)
            if (assigneeId != null) put("assignee_id", assigneeId) else putNull("assignee_id")
            if (channelId != null) put("channel_id", channelId) else putNull("channel_id")
            if (parentTaskId != null) put("parent_task_id", parentTaskId) else putNull("parent_task_id")
            put("result", result)
            put("created_at", now)
            put("updated_at", now)
        }
        val id = db().insertOrThrow("tasks", null, cv)
        return getTask(id)!!
    }

    fun updateTask(id: Long, updates: Map<String, Any?>): JSONObject {
        val cv = ContentValues()
        updates.forEach { (k, v) ->
            when (v) {
                null -> cv.putNull(k)
                is String -> cv.put(k, v)
                is Long -> cv.put(k, v)
                is Int -> cv.put(k, v)
                is Boolean -> cv.put(k, if (v) 1 else 0)
                else -> cv.put(k, v.toString())
            }
        }
        cv.put("updated_at", nowIso())
        db().update("tasks", cv, "id=?", arrayOf(id.toString()))
        return getTask(id)!!
    }

    // ---- bootstrap ----

    fun bootstrap(name: String = "Grok Demo Org"): JSONObject {
        val existing = queryOne(
            "SELECT * FROM organisations WHERE name=?", arrayOf(name)
        ) { cursorToJson(it, "id", "name", "description", "created_at") }
        val org = existing ?: createOrg(name, "Sample multi-agent organisation for demos and tests")
        val orgId = org.getLong("id")

        fun team(n: String, d: String): JSONObject =
            findTeam(orgId, n) ?: createTeam(orgId, n, d)

        val ops = team("Ops", "Operations and execution")
        val research = team("Research", "Research and analysis")
        val comms = team("Comms", "Communications and stakeholder updates")

        fun agent(
            n: String,
            role: String,
            teamId: Long? = null,
            isHuman: Boolean = false,
            prompt: String? = null,
        ): JSONObject =
            findAgent(orgId, n) ?: createAgent(orgId, n, role, teamId, isHuman, prompt)

        val ceo = agent(
            "CEO", "ceo", isHuman = true,
            prompt = "You are the human CEO. Set direction and approve plans."
        )
        val cos = agent(
            "Chief of Staff", "chief_of_staff",
            prompt = "You are the Chief of Staff. Decompose CEO directives into subtasks, " +
                "assign work to Ops/Research/Comms specialists, and synthesize results."
        )
        val opsA = agent(
            "Ops Specialist", "specialist", ops.getLong("id"),
            prompt = "You are an Ops specialist focused on operations, logistics, and execution readiness."
        )
        val researchA = agent(
            "Research Specialist", "specialist", research.getLong("id"),
            prompt = "You are a Research specialist focused on gathering facts, options, and analysis."
        )
        val commsA = agent(
            "Comms Specialist", "specialist", comms.getLong("id"),
            prompt = "You are a Comms specialist focused on clear stakeholder communication."
        )

        val channel = findChannel(orgId, "HQ")
            ?: createChannel(orgId, "HQ", "Primary coordination channel")

        return JSONObject()
            .put("organisation", org)
            .put(
                "agents",
                JSONObject()
                    .put("ceo", ceo)
                    .put("chief_of_staff", cos)
                    .put("ops", opsA)
                    .put("research", researchA)
                    .put("comms", commsA)
            )
            .put("channel", channel)
            .put(
                "teams",
                JSONObject()
                    .put("Ops", JSONObject().put("id", ops.getLong("id")).put("name", ops.getString("name")).put("description", ops.optString("description")))
                    .put("Research", JSONObject().put("id", research.getLong("id")).put("name", research.getString("name")).put("description", research.optString("description")))
                    .put("Comms", JSONObject().put("id", comms.getLong("id")).put("name", comms.getString("name")).put("description", comms.optString("description")))
            )
    }

    fun ensureBootstrapped() {
        if (orgCount() == 0) bootstrap()
    }

    // ---- v2 agents status ----

    fun agentsStatus(): JSONArray {
        val arr = JSONArray()
        db().rawQuery("SELECT id, name, role, is_human, COALESCE(status,'idle') FROM agents ORDER BY id", null).use { c ->
            while (c.moveToNext()) {
                arr.put(
                    JSONObject()
                        .put("id", c.getLong(0))
                        .put("name", c.getString(1))
                        .put("role", c.getString(2))
                        .put("is_human", c.getInt(3) == 1)
                        .put("status", c.getString(4) ?: "idle")
                )
            }
        }
        return arr
    }

    fun setAgentStatus(agentId: Long, status: String) {
        val cv = ContentValues().apply { put("status", status) }
        db().update("agents", cv, "id=?", arrayOf(agentId.toString()))
    }


    private val netExecutor = Executors.newCachedThreadPool()

    fun providersJson(): JSONObject {
        val providers = JSONArray()
        fun add(id: String, name: String, base: String, editable: Boolean = true, placeholder: Boolean = false) {
            val o = JSONObject()
                .put("id", id)
                .put("name", name)
                .put("base_url", base)
                .put("editable", editable)
            if (placeholder) o.put("placeholder", true)
            providers.put(o)
        }
        add("openai", "OpenAI", "https://api.openai.com/v1")
        add("openrouter", "OpenRouter", "https://openrouter.ai/api/v1")
        add("groq", "Groq", "https://api.groq.com/openai/v1")
        add("nvidia", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1")
        add("together", "Together", "https://api.together.xyz/v1")
        add("fireworks", "Fireworks", "https://api.fireworks.ai/inference/v1")
        add("deepseek", "DeepSeek", "https://api.deepseek.com/v1")
        add("mistral", "Mistral", "https://api.mistral.ai/v1")
        add("google", "Google AI Studio (OpenAI compat)", "https://generativelanguage.googleapis.com/v1beta/openai")
        add("azure", "Azure OpenAI", "https://YOUR_RESOURCE.openai.azure.com/openai/v1", placeholder = true)
        add("ollama", "Ollama", "http://127.0.0.1:11434/v1")
        add("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1")
        add("custom", "Custom", "")
        return JSONObject().put("ok", true).put("providers", providers).put("count", providers.length())
    }

    private fun resolveOverrides(overrides: JSONObject?): Triple<String, String, String> {
        loadLlmSettings()
        var apiKey = llm.apiKey
        var baseUrl = llm.baseUrl
        var model = llm.model
        if (overrides != null) {
            if (overrides.has("openai_api_key") && !overrides.isNull("openai_api_key")) {
                val k = overrides.optString("openai_api_key", "").trim()
                if (k.isNotEmpty()) apiKey = k
            }
            if (overrides.has("openai_base_url") && !overrides.isNull("openai_base_url")) {
                val b = overrides.optString("openai_base_url", "").trim()
                if (b.isNotEmpty()) baseUrl = normalizeBaseUrl(b)
            }
            if (overrides.has("openai_model") && !overrides.isNull("openai_model")) {
                val m = overrides.optString("openai_model", "").trim()
                if (m.isNotEmpty()) model = m
            }
        }
        return Triple(apiKey, baseUrl, model)
    }

    private fun looksChatCapable(id: String): Boolean {
        val mid = id.lowercase()
        val skip = listOf(
            "embed", "embedding", "rerank", "tts", "whisper", "transcri",
            "moderation", "dall-e", "stable-diffusion", "flux", "image", "video", "codec", "retrieve",
        )
        return skip.none { mid.contains(it) }
    }

    private fun <T> runNet(timeoutSec: Long = 45, block: () -> T): T {
        val fut = netExecutor.submit(block)
        return try {
            fut.get(timeoutSec, TimeUnit.SECONDS)
        } catch (e: TimeoutException) {
            fut.cancel(true)
            throw e
        }
    }

    fun testLlmConnection(overrides: JSONObject? = null): JSONObject {
        val (apiKey, baseUrlRaw, model) = resolveOverrides(overrides)
        if (apiKey.isBlank()) {
            return JSONObject().put("ok", true).put("mode", "mock").put("model", model)
                .put("message", "Mock LLM ready")
        }
        return try {
            runNet(45) {
                val base = normalizeBaseUrl(baseUrlRaw)
                val url = URL("${base.trimEnd('/')}/chat/completions")
                val payload = JSONObject().apply {
                    put("model", model)
                    put("temperature", 0)
                    put("max_tokens", 16)
                    put("messages", JSONArray().put(
                        JSONObject().put("role", "user").put("content", "Reply with exactly: pong")
                    ))
                }
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    connectTimeout = 45_000
                    readTimeout = 45_000
                    instanceFollowRedirects = true
                    doOutput = true
                    setRequestProperty("Authorization", "Bearer $apiKey")
                    setRequestProperty("Content-Type", "application/json")
                    setRequestProperty("User-Agent", "NEHA/2.1.4")
                    setRequestProperty("Accept", "application/json")
                }
                try {
                    conn.outputStream.bufferedWriter().use { it.write(payload.toString()) }
                    val code = conn.responseCode
                    val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                    val textBody = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                    when {
                        code == 401 -> JSONObject()
                            .put("ok", false).put("mode", "live").put("model", model)
                            .put("base_url", base)
                            .put("error", "401 Unauthorized — API key rejected. Check key and provider.")
                            .put("status_code", 401)
                        code == 404 -> JSONObject()
                            .put("ok", false).put("mode", "live").put("model", model)
                            .put("base_url", base)
                            .put("error", "404 Not Found at $url. Check base URL (often needs /v1; no trailing slash).")
                            .put("status_code", 404)
                        code !in 200..299 -> JSONObject()
                            .put("ok", false).put("mode", "live").put("model", model)
                            .put("base_url", base)
                            .put("error", "HTTP $code: ${textBody.take(400)}")
                            .put("status_code", code)
                        else -> {
                            val msg = JSONObject(textBody)
                                .getJSONArray("choices").getJSONObject(0)
                                .getJSONObject("message").optString("content", "")
                            JSONObject().put("ok", true).put("mode", "live").put("model", model)
                                .put("base_url", base).put("message", msg.take(200))
                        }
                    }
                } finally {
                    conn.disconnect()
                }
            }
        } catch (e: TimeoutException) {
            JSONObject().put("ok", false).put("mode", "live").put("model", model)
                .put("base_url", baseUrlRaw)
                .put("error", "Timeout after 45s testing connection")
        } catch (e: Exception) {
            JSONObject().put("ok", false).put("mode", "live").put("model", model)
                .put("base_url", baseUrlRaw)
                .put("error", "Connection failed: ${e.message ?: "error"}")
        }
    }

    fun listModels(overrides: JSONObject? = null): JSONObject {
        val (apiKey, baseUrlRaw, _) = resolveOverrides(overrides)
        if (apiKey.isBlank()) {
            val models = JSONArray()
            listOf(
                "gpt-4o-mini" to "openai",
                "gpt-4o" to "openai",
                "gpt-4.1-mini" to "openai",
                "gpt-4.1" to "openai",
                "o3-mini" to "openai",
                "claude-3.5-sonnet" to "anthropic",
            ).forEach { (id, owned) ->
                models.put(JSONObject().put("id", id).put("owned_by", owned))
            }
            return JSONObject()
                .put("ok", true)
                .put("mode", "mock")
                .put("base_url", normalizeBaseUrl(baseUrlRaw))
                .put("note", "No API key set — showing curated mock models. Add a key to fetch from the provider.")
                .put("models", models)
                .put("data", models)
        }
        return try {
            runNet(45) {
                val base = normalizeBaseUrl(baseUrlRaw)
                val url = URL("${base.trimEnd('/')}/models")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 45_000
                    readTimeout = 45_000
                    instanceFollowRedirects = true
                    setRequestProperty("Authorization", "Bearer $apiKey")
                    setRequestProperty("User-Agent", "NEHA/2.1.4")
                    setRequestProperty("Accept", "application/json")
                }
                try {
                    val code = conn.responseCode
                    val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                    val textBody = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
                    if (code == 401) {
                        return@runNet JSONObject()
                            .put("ok", false).put("mode", "live").put("base_url", base)
                            .put("error", "401 Unauthorized — check API key")
                            .put("status_code", 401)
                            .put("models", JSONArray()).put("data", JSONArray())
                    }
                    if (code == 404) {
                        return@runNet JSONObject()
                            .put("ok", false).put("mode", "live").put("base_url", base)
                            .put("error", "404 Not Found at $url. Check base URL (try with /v1; trailing slash is stripped).")
                            .put("status_code", 404)
                            .put("models", JSONArray()).put("data", JSONArray())
                    }
                    if (code !in 200..299) {
                        return@runNet JSONObject()
                            .put("ok", false).put("mode", "live").put("base_url", base)
                            .put("error", "HTTP $code: ${textBody.take(300)}")
                            .put("status_code", code)
                            .put("models", JSONArray()).put("data", JSONArray())
                    }
                    val payload = JSONObject(textBody)
                    val raw = payload.optJSONArray("data") ?: JSONArray()
                    val sorted = mutableListOf<JSONObject>()
                    for (i in 0 until raw.length()) {
                        val item = raw.opt(i)
                        when (item) {
                            is JSONObject -> {
                                val id = item.optString("id", "")
                                if (id.isNotBlank()) {
                                    sorted += JSONObject()
                                        .put("id", id)
                                        .put("owned_by", item.optString("owned_by", item.optString("ownedBy", "")))
                                }
                            }
                            is String -> sorted += JSONObject().put("id", item).put("owned_by", "")
                        }
                    }
                    sorted.sortWith(compareBy({ if (looksChatCapable(it.getString("id"))) 0 else 1 }, { it.getString("id").lowercase() }))
                    val out = JSONArray()
                    sorted.forEach { out.put(it) }
                    JSONObject()
                        .put("ok", true).put("mode", "live").put("base_url", base)
                        .put("models", out).put("data", out).put("count", out.length())
                } finally {
                    conn.disconnect()
                }
            }
        } catch (e: TimeoutException) {
            JSONObject()
                .put("ok", false).put("mode", "live").put("base_url", baseUrlRaw)
                .put("error", "Timeout after 45s fetching models")
                .put("models", JSONArray()).put("data", JSONArray())
        } catch (e: Exception) {
            JSONObject()
                .put("ok", false).put("mode", "live").put("base_url", baseUrlRaw)
                .put("error", e.message ?: "error")
                .put("models", JSONArray()).put("data", JSONArray())
        }
    }

    // ---- approvals ----

    fun listApprovals(orgId: Long?, status: String? = null): JSONArray {
        val clauses = mutableListOf<String>()
        val args = mutableListOf<String>()
        if (orgId != null) { clauses += "organisation_id=?"; args += orgId.toString() }
        if (status != null) { clauses += "status=?"; args += status }
        val where = if (clauses.isEmpty()) "" else "WHERE " + clauses.joinToString(" AND ")
        return queryList("SELECT * FROM approvals $where ORDER BY id DESC", args.toTypedArray()) {
            approvalFromCursor(it)
        }
    }

    private fun approvalFromCursor(c: Cursor): JSONObject {
        val o = cursorToJson(
            c, "id", "organisation_id", "requester_agent_id", "title", "description",
            "status", "decision_note", "related_task_id", "created_at", "resolved_at"
        )
        val req = o.optLongOrNull("requester_agent_id")
        if (req != null) {
            getAgent(req)?.let { o.put("requester_name", it.optString("name")) }
        }
        return o
    }

    fun createApproval(
        orgId: Long,
        title: String,
        description: String?,
        requesterAgentId: Long?,
        relatedTaskId: Long?,
    ): JSONObject {
        val cv = ContentValues().apply {
            put("organisation_id", orgId)
            put("title", title)
            put("description", description)
            if (requesterAgentId != null) put("requester_agent_id", requesterAgentId) else putNull("requester_agent_id")
            if (relatedTaskId != null) put("related_task_id", relatedTaskId) else putNull("related_task_id")
            put("status", "pending")
            put("created_at", nowIso())
        }
        val id = db().insertOrThrow("approvals", null, cv)
        return queryOne("SELECT * FROM approvals WHERE id=?", arrayOf(id.toString())) { approvalFromCursor(it) }!!
    }

    fun resolveApproval(id: Long, approve: Boolean, note: String?): JSONObject {
        val cv = ContentValues().apply {
            put("status", if (approve) "approved" else "rejected")
            put("decision_note", note ?: if (approve) "Approved by CEO" else "Rejected by CEO")
            put("resolved_at", nowIso())
        }
        db().update("approvals", cv, "id=?", arrayOf(id.toString()))
        val a = queryOne("SELECT * FROM approvals WHERE id=?", arrayOf(id.toString())) { approvalFromCursor(it) }!!
        val req = a.optLongOrNull("requester_agent_id")
        if (req != null) setAgentStatus(req, "idle")
        val taskId = a.optLongOrNull("related_task_id")
        if (taskId != null) {
            if (approve) updateTask(taskId, mapOf("status" to "assigned"))
            else updateTask(taskId, mapOf("status" to "failed", "result" to "Rejected: ${a.optString("decision_note")}"))
        }
        return a
    }

    // ---- routines ----

    fun listRoutines(orgId: Long?): JSONArray {
        val sql = if (orgId != null)
            "SELECT * FROM routines WHERE organisation_id=? ORDER BY id"
        else "SELECT * FROM routines ORDER BY id"
        val args = if (orgId != null) arrayOf(orgId.toString()) else null
        return queryList(sql, args) { routineFromCursor(it) }
    }

    private fun routineFromCursor(c: Cursor): JSONObject =
        cursorToJson(
            c, "id", "organisation_id", "name", "prompt", "cron", "every_seconds",
            "target_agent_id", "channel_id", "enabled", "last_run_at", "created_at"
        ).also {
            val e = it.opt("enabled")
            if (e is Int) it.put("enabled", e == 1)
        }

    fun createRoutine(
        orgId: Long,
        name: String,
        prompt: String,
        cron: String?,
        everySeconds: Int?,
        targetAgentId: Long?,
        channelId: Long?,
        enabled: Boolean = true,
    ): JSONObject {
        val cv = ContentValues().apply {
            put("organisation_id", orgId)
            put("name", name)
            put("prompt", prompt)
            put("cron", cron)
            if (everySeconds != null) put("every_seconds", everySeconds) else putNull("every_seconds")
            if (targetAgentId != null) put("target_agent_id", targetAgentId) else putNull("target_agent_id")
            if (channelId != null) put("channel_id", channelId) else putNull("channel_id")
            put("enabled", if (enabled) 1 else 0)
            put("created_at", nowIso())
        }
        val id = db().insertOrThrow("routines", null, cv)
        return queryOne("SELECT * FROM routines WHERE id=?", arrayOf(id.toString())) { routineFromCursor(it) }!!
    }

    fun deleteRoutine(id: Long) {
        db().delete("routines", "id=?", arrayOf(id.toString()))
    }

    fun fireRoutine(id: Long): JSONObject {
        val r = queryOne("SELECT * FROM routines WHERE id=?", arrayOf(id.toString())) { routineFromCursor(it) }
            ?: throw ApiError(404, "Routine not found")
        val orgId = r.getLong("organisation_id")
        var agentId = r.optLongOrNull("target_agent_id")
        var channelId = r.optLongOrNull("channel_id")
        if (agentId == null) {
            db().rawQuery(
                "SELECT id FROM agents WHERE organisation_id=? AND is_human=0 ORDER BY id LIMIT 1",
                arrayOf(orgId.toString())
            ).use { c -> if (c.moveToFirst()) agentId = c.getLong(0) }
        }
        if (channelId == null) {
            db().rawQuery(
                "SELECT id FROM channels WHERE organisation_id=? ORDER BY id LIMIT 1",
                arrayOf(orgId.toString())
            ).use { c -> if (c.moveToFirst()) channelId = c.getLong(0) }
        }
        val aId = agentId
        val cId = channelId
        if (aId != null && cId != null) {
            createMessage(cId, aId, "⏰ Routine '${r.getString("name")}' fired:\n${r.getString("prompt")}")
            createTask(
                orgId = orgId,
                title = "[Routine] ${r.getString("name")}",
                description = r.getString("prompt"),
                status = "assigned",
                assigneeId = aId,
                channelId = cId,
            )
        }
        val cv = ContentValues().apply { put("last_run_at", nowIso()) }
        db().update("routines", cv, "id=?", arrayOf(id.toString()))
        return queryOne("SELECT * FROM routines WHERE id=?", arrayOf(id.toString())) { routineFromCursor(it) }!!
    }

    // ---- files ----

    fun workspaceDir(): File {
        val dir = File(appContext.filesDir, "workspace")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    fun listWorkspaceFiles(): JSONObject {
        val root = workspaceDir()
        val entries = JSONArray()
        root.listFiles()?.sortedBy { it.name }?.forEach { f ->
            entries.put(
                JSONObject()
                    .put("name", f.name)
                    .put("path", f.name)
                    .put("type", if (f.isDirectory) "dir" else "file")
                    .put("size", if (f.isFile) f.length() else JSONObject.NULL)
            )
        }
        return JSONObject().put("path", ".").put("workspace", root.absolutePath).put("entries", entries)
    }

    fun saveWorkspaceFile(name: String, bytes: ByteArray): JSONObject {
        val safe = File(name).name
        val dest = File(workspaceDir(), safe)
        dest.writeBytes(bytes)
        return JSONObject().put("ok", true).put("path", safe).put("bytes", bytes.size)
    }

    // ---- connectors ----

    fun listConnectors(): JSONArray {
        val arr = JSONArray()
        arr.put(
            JSONObject().put("name", "files").put("label", "Files (workspace)")
                .put("available", true).put("enabled", true).put("user_enabled", true)
                .put("setup", "App filesDir/workspace")
        )
        arr.put(
            JSONObject().put("name", "web").put("label", "Web (HTTP fetch)")
                .put("available", true).put("enabled", true).put("user_enabled", true)
                .put("setup", "No configuration required.")
        )
        arr.put(
            JSONObject().put("name", "smtp_email").put("label", "Email (SMTP)")
                .put("available", false).put("enabled", false).put("user_enabled", false)
                .put("setup", "Configure SMTP on Python server; stub on Android.")
        )
        arr.put(
            JSONObject().put("name", "rest").put("label", "Generic REST")
                .put("available", true).put("enabled", true).put("user_enabled", true)
                .put("setup", "POST invoke with url/method.")
        )
        return arr
    }

    fun invokeConnector(name: String, payload: JSONObject): JSONObject {
        return when (name) {
            "files" -> listWorkspaceFiles()
            "web" -> {
                val url = payload.optString("url", "https://example.com")
                try {
                    val conn = (URL(url).openConnection() as HttpURLConnection).apply {
                        connectTimeout = 15000
                        readTimeout = 15000
                    }
                    val text = conn.inputStream.bufferedReader().use { it.readText() }
                    JSONObject().put("status_code", conn.responseCode).put("url", url)
                        .put("body", text.take(payload.optInt("max_chars", 400)))
                } catch (e: Exception) {
                    JSONObject().put("error", e.message ?: "fetch failed")
                }
            }
            else -> JSONObject().put("ok", true).put("stub", true).put("name", name)
        }
    }

}

