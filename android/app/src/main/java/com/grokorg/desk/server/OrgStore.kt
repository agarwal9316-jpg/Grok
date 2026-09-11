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
import java.util.TimeZone

/**
 * SQLite-backed store mirroring Python models + bootstrap.
 */
class OrgStore(context: Context) {
    private val dbHelper = DbHelper(context.applicationContext)
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

    fun loadLlmSettings() {
        llm.apiKey = getSetting("openai_api_key", "")
        llm.baseUrl = getSetting("openai_base_url", "https://api.openai.com/v1")
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
    }

    fun updateSettings(body: JSONObject): JSONObject {
        if (body.has("openai_api_key") && !body.isNull("openai_api_key")) {
            setSetting("openai_api_key", body.getString("openai_api_key"))
        }
        if (body.has("openai_base_url") && !body.isNull("openai_base_url")) {
            val v = body.getString("openai_base_url").trim()
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
            "is_human", "system_prompt", "created_at"
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
            "is_human", "system_prompt", "created_at"
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
                        "is_human", "system_prompt", "created_at"
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
                it, "id", "channel_id", "agent_id", "content", "created_at",
                "agent_name", "agent_role"
            )
        }
    }

    fun createMessage(channelId: Long, agentId: Long, content: String): JSONObject {
        val cv = ContentValues().apply {
            put("channel_id", channelId)
            put("agent_id", agentId)
            put("content", content)
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
                it, "id", "channel_id", "agent_id", "content", "created_at",
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
}
