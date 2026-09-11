package com.grokorg.desk.server

import android.content.Context
import android.util.Log
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

/**
 * In-process HTTP server: static desk GUI + JSON API matching FastAPI routes.
 */
class LocalHttpServer(
    private val appContext: Context,
    private val store: OrgStore,
    hostname: String,
    port: Int,
) : NanoHTTPD(hostname, port) {

    private val runner = TaskRunner(store)

    override fun serve(session: IHTTPSession): Response {
        return try {
            val uri = session.uri.substringBefore('?')
            val method = session.method
            Log.d(TAG, "$method $uri")

            val filesMap = HashMap<String, String>()
            val body = readBody(session, filesMap)

            when {
                uri == "/health" && method == Method.GET ->
                    json(JSONObject().put("status", "ok").put("version", "2.1.3"))

                uri == "/" && method == Method.GET ->
                    asset("www/index.html", "text/html")

                uri.startsWith("/static/") && method == Method.GET ->
                    serveStatic(uri.removePrefix("/static/"))

                uri.startsWith("/api/") ->
                    handleApi(uri.removePrefix("/api"), method, session.parms, body, filesMap)

                else ->
                    // SPA-ish fallback
                    if (method == Method.GET) asset("www/index.html", "text/html")
                    else errorJson(404, "Not found")
            }
        } catch (e: ApiError) {
            errorJson(e.code, e.message)
        } catch (e: Exception) {
            Log.e(TAG, "serve error", e)
            errorJson(500, e.message ?: "Internal error")
        }
    }

    private fun readBody(session: IHTTPSession, filesOut: MutableMap<String, String>): String {
        return try {
            if (session.method == Method.POST ||
                session.method == Method.PUT ||
                session.method == Method.PATCH
            ) {
                session.parseBody(filesOut)
                filesOut["postData"] ?: ""
            } else ""
        } catch (_: Exception) {
            ""
        }
    }

    private fun handleApi(
        path: String,
        method: Method,
        query: Map<String, String>,
        body: String,
        filesMap: Map<String, String> = emptyMap(),
    ): Response {
        val p = path.trimEnd('/').ifEmpty { "/" }
        val jsonBody = if (body.isNotBlank()) JSONObject(body) else JSONObject()

        // ---- system ----
        if ((p == "/config" || p == "/settings") && method == Method.GET) {
            return json(store.configJson())
        }
        if ((p == "/config" || p == "/settings") && method == Method.PUT) {
            if (jsonBody.length() == 0) throw ApiError(400, "No settings to update")
            return json(store.updateSettings(jsonBody))
        }
        if (p == "/bootstrap" && method == Method.POST) {
            val name = jsonBody.optString("name", "Grok Demo Org").ifBlank { "Grok Demo Org" }
            return json(store.bootstrap(name), status = Response.Status.OK)
        }
        if (p == "/demo" && method == Method.POST) {
            val result = runner.runDemo(
                orgName = jsonBody.optString("org_name", "Grok Demo Org").ifBlank { "Grok Demo Org" },
                title = jsonBody.optString("title", "Launch Q4 product pilot")
                    .ifBlank { "Launch Q4 product pilot" },
                description = jsonBody.optString(
                    "description",
                    "Coordinate Ops, Research, and Comms to prepare a Q4 product pilot plan."
                ),
            )
            return json(result)
        }

        // ---- orgs ----
        if (p == "/orgs" && method == Method.GET) return json(store.listOrgs())
        if (p == "/orgs" && method == Method.POST) {
            val name = jsonBody.getString("name")
            val desc = if (jsonBody.has("description") && !jsonBody.isNull("description"))
                jsonBody.getString("description") else null
            return json(store.createOrg(name, desc), Response.Status.CREATED)
        }
        Regex("^/orgs/(\\d+)$").matchEntire(p)?.let { m ->
            val id = m.groupValues[1].toLong()
            when (method) {
                Method.GET -> {
                    val o = store.getOrg(id) ?: throw ApiError(404, "Organisation not found")
                    return json(o)
                }
                else -> {}
            }
        }

        // ---- teams ----
        if (p == "/teams" && method == Method.GET) {
            val oid = query["organisation_id"]?.toLongOrNull()
            return json(store.listTeams(oid))
        }
        if (p == "/teams" && method == Method.POST) {
            return json(
                store.createTeam(
                    jsonBody.getLong("organisation_id"),
                    jsonBody.getString("name"),
                    jsonBody.optNullableString("description"),
                ),
                Response.Status.CREATED
            )
        }

        // ---- agents ----
        if (p == "/agents" && method == Method.GET) {
            val oid = query["organisation_id"]?.toLongOrNull()
            return json(store.listAgents(oid))
        }
        if (p == "/agents" && method == Method.POST) {
            return json(
                store.createAgent(
                    orgId = jsonBody.getLong("organisation_id"),
                    name = jsonBody.getString("name"),
                    role = jsonBody.getString("role"),
                    teamId = jsonBody.optLongOrNull("team_id"),
                    isHuman = jsonBody.optBoolean("is_human", false),
                    systemPrompt = jsonBody.optNullableString("system_prompt"),
                ),
                Response.Status.CREATED
            )
        }

        // ---- channels ----
        if (p == "/channels" && method == Method.GET) {
            val oid = query["organisation_id"]?.toLongOrNull()
            return json(store.listChannels(oid))
        }
        if (p == "/channels" && method == Method.POST) {
            return json(
                store.createChannel(
                    jsonBody.getLong("organisation_id"),
                    jsonBody.getString("name"),
                    jsonBody.optNullableString("description"),
                ),
                Response.Status.CREATED
            )
        }

        // ---- messages ----
        if (p == "/messages" && method == Method.GET) {
            val cid = query["channel_id"]?.toLongOrNull()
            return json(store.listMessages(cid))
        }
        if (p == "/messages" && method == Method.POST) {
            return json(
                store.createMessage(
                    jsonBody.getLong("channel_id"),
                    jsonBody.getLong("agent_id"),
                    jsonBody.getString("content"),
                    jsonBody.optLongOrNull("parent_id"),
                ),
                Response.Status.CREATED
            )
        }

        // ---- tasks ----
        if (p == "/tasks" && method == Method.GET) {
            val oid = query["organisation_id"]?.toLongOrNull()
            val st = query["status"]
            return json(store.listTasks(oid, st))
        }
        if (p == "/tasks" && method == Method.POST) {
            return json(
                store.createTask(
                    orgId = jsonBody.getLong("organisation_id"),
                    title = jsonBody.getString("title"),
                    description = jsonBody.optNullableString("description"),
                    status = jsonBody.optString("status", "pending"),
                    assigneeId = jsonBody.optLongOrNull("assignee_id"),
                    channelId = jsonBody.optLongOrNull("channel_id"),
                    parentTaskId = jsonBody.optLongOrNull("parent_task_id"),
                ),
                Response.Status.CREATED
            )
        }

        Regex("^/tasks/(\\d+)$").matchEntire(p)?.let { m ->
            val id = m.groupValues[1].toLong()
            if (method == Method.GET) {
                val t = store.getTask(id) ?: throw ApiError(404, "Task not found")
                return json(t)
            }
        }

        Regex("^/tasks/(\\d+)/assign$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                val id = m.groupValues[1].toLong()
                store.getTask(id) ?: throw ApiError(404, "Task not found")
                val run = query["run"]?.lowercase() != "false"
                val assigneeId = jsonBody.getLong("assignee_id")
                val channelId = jsonBody.optLongOrNull("channel_id")
                return json(runner.assignTask(id, assigneeId, channelId, run))
            }
        }

        Regex("^/tasks/(\\d+)/handoff$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                val id = m.groupValues[1].toLong()
                store.getTask(id) ?: throw ApiError(404, "Task not found")
                val run = query["run"]?.lowercase() != "false"
                return json(
                    runner.handoff(
                        id,
                        jsonBody.getLong("to_agent_id"),
                        jsonBody.optNullableString("note"),
                        run,
                    )
                )
            }
        }

        Regex("^/tasks/(\\d+)/run$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                val id = m.groupValues[1].toLong()
                store.getTask(id) ?: throw ApiError(404, "Task not found")
                return json(runner.runTask(id))
            }
        }



        // ---- providers catalog ----
        if (p == "/providers" && method == Method.GET) {
            return json(store.providersJson())
        }

        // ---- models (accept JSON body overrides for key/base) ----
        if (p == "/models" && (method == Method.GET || method == Method.POST)) {
            val overrides = if (jsonBody.length() > 0) jsonBody else null
            return try {
                json(store.listModels(overrides))
            } catch (e: Exception) {
                Log.e(TAG, "listModels failed", e)
                json(
                    JSONObject()
                        .put("ok", false)
                        .put("mode", "live")
                        .put("error", e.message ?: "listModels failed")
                        .put("models", org.json.JSONArray())
                        .put("data", org.json.JSONArray())
                )
            }
        }

        // ---- settings test (accept body overrides) ----
        if ((p == "/settings/test" || p == "/config/test") && method == Method.POST) {
            val overrides = if (jsonBody.length() > 0) jsonBody else null
            return try {
                json(store.testLlmConnection(overrides))
            } catch (e: Exception) {
                Log.e(TAG, "testLlmConnection failed", e)
                json(
                    JSONObject()
                        .put("ok", false)
                        .put("mode", "live")
                        .put("error", e.message ?: "test failed")
                )
            }
        }

        // ---- agents status ----
        if (p == "/agents/status" && method == Method.GET) {
            return json(store.agentsStatus())
        }

        // ---- approvals ----
        if (p == "/approvals" && method == Method.GET) {
            val oid = query["organisation_id"]?.toLongOrNull()
            val st = query["status"]
            return json(store.listApprovals(oid, st))
        }
        if (p == "/approvals" && method == Method.POST) {
            return json(
                store.createApproval(
                    orgId = jsonBody.getLong("organisation_id"),
                    title = jsonBody.getString("title"),
                    description = jsonBody.optNullableString("description"),
                    requesterAgentId = jsonBody.optLongOrNull("requester_agent_id"),
                    relatedTaskId = jsonBody.optLongOrNull("related_task_id"),
                ),
                Response.Status.CREATED
            )
        }
        Regex("^/approvals/(\\d+)/approve$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                return json(store.resolveApproval(m.groupValues[1].toLong(), true, jsonBody.optNullableString("decision_note")))
            }
        }
        Regex("^/approvals/(\\d+)/reject$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                return json(store.resolveApproval(m.groupValues[1].toLong(), false, jsonBody.optNullableString("decision_note")))
            }
        }

        // ---- routines ----
        if (p == "/routines" && method == Method.GET) {
            val oid = query["organisation_id"]?.toLongOrNull()
            return json(store.listRoutines(oid))
        }
        if (p == "/routines" && method == Method.POST) {
            val every = if (jsonBody.has("every_seconds") && !jsonBody.isNull("every_seconds"))
                jsonBody.getInt("every_seconds") else null
            val cron = jsonBody.optNullableString("cron")
            if (every == null && cron.isNullOrBlank()) throw ApiError(400, "Provide cron or every_seconds")
            return json(
                store.createRoutine(
                    orgId = jsonBody.getLong("organisation_id"),
                    name = jsonBody.getString("name"),
                    prompt = jsonBody.getString("prompt"),
                    cron = cron,
                    everySeconds = every,
                    targetAgentId = jsonBody.optLongOrNull("target_agent_id"),
                    channelId = jsonBody.optLongOrNull("channel_id"),
                    enabled = jsonBody.optBoolean("enabled", true),
                ),
                Response.Status.CREATED
            )
        }
        Regex("^/routines/(\\d+)$").matchEntire(p)?.let { m ->
            if (method == Method.DELETE) {
                store.deleteRoutine(m.groupValues[1].toLong())
                return newFixedLengthResponse(Response.Status.NO_CONTENT, "text/plain", "").also { addCors(it) }
            }
        }
        Regex("^/routines/(\\d+)/run$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                return json(store.fireRoutine(m.groupValues[1].toLong()))
            }
        }

        // ---- connectors ----
        if (p == "/connectors" && method == Method.GET) {
            return json(store.listConnectors())
        }
        Regex("^/connectors/([^/]+)/enable$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                return json(JSONObject().put("name", m.groupValues[1]).put("enabled", jsonBody.optBoolean("enabled", true)))
            }
        }
        Regex("^/connectors/([^/]+)/invoke$").matchEntire(p)?.let { m ->
            if (method == Method.POST) {
                val payload = jsonBody.optJSONObject("payload") ?: JSONObject()
                return json(store.invokeConnector(m.groupValues[1], payload))
            }
        }

        // ---- files ----
        if (p == "/files" && method == Method.GET) {
            return json(store.listWorkspaceFiles())
        }
        if (p == "/files/upload" && method == Method.POST) {
            val tmp = filesMap["file"]
            if (!tmp.isNullOrBlank()) {
                val f = java.io.File(tmp)
                val name = query["filename"] ?: f.name.ifBlank { "upload.bin" }
                return json(store.saveWorkspaceFile(name, f.readBytes()))
            }
            val name = jsonBody.optString("filename", "upload.bin")
            val b64 = jsonBody.optString("content_base64", "")
            if (b64.isNotBlank()) {
                val bytes = android.util.Base64.decode(b64, android.util.Base64.DEFAULT)
                return json(store.saveWorkspaceFile(name, bytes))
            }
            val text = jsonBody.optString("content", "uploaded via Android")
            return json(store.saveWorkspaceFile(name, text.toByteArray(Charsets.UTF_8)))
        }


        throw ApiError(404, "Not found: $p")
    }

    private fun serveStatic(rel: String): Response {
        val clean = URLDecoder.decode(rel, "UTF-8").trimStart('/')
        if (clean.contains("..")) throw ApiError(400, "Bad path")
        val mime = when {
            clean.endsWith(".css") -> "text/css"
            clean.endsWith(".js") -> "application/javascript"
            clean.endsWith(".html") -> "text/html"
            clean.endsWith(".png") -> "image/png"
            clean.endsWith(".svg") -> "image/svg+xml"
            clean.endsWith(".json") -> "application/json"
            else -> "application/octet-stream"
        }
        return asset("www/$clean", mime)
    }

    private fun asset(path: String, mime: String): Response {
        return try {
            val bytes = appContext.assets.open(path).use { it.readBytes() }
            newFixedLengthResponse(
                Response.Status.OK,
                mime,
                ByteArrayInputStream(bytes),
                bytes.size.toLong()
            ).also { addCors(it) }
        } catch (e: Exception) {
            Log.w(TAG, "asset missing: $path", e)
            errorJson(404, "Asset not found: $path")
        }
    }

    private fun json(obj: Any, status: Response.Status = Response.Status.OK): Response {
        val text = obj.toString()
        val bytes = text.toByteArray(StandardCharsets.UTF_8)
        return newFixedLengthResponse(
            status,
            "application/json; charset=utf-8",
            ByteArrayInputStream(bytes),
            bytes.size.toLong()
        ).also { addCors(it) }
    }

    private fun errorJson(code: Int, detail: String): Response {
        val status = Response.Status.lookup(code) ?: Response.Status.INTERNAL_ERROR
        val text = JSONObject().put("detail", detail).toString()
        val bytes = text.toByteArray(StandardCharsets.UTF_8)
        return newFixedLengthResponse(
            status,
            "application/json; charset=utf-8",
            ByteArrayInputStream(bytes),
            bytes.size.toLong()
        ).also { addCors(it) }
    }

    private fun addCors(r: Response) {
        r.addHeader("Access-Control-Allow-Origin", "*")
        r.addHeader("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        r.addHeader("Access-Control-Allow-Headers", "Content-Type")
        r.addHeader("Cache-Control", "no-store")
    }

    companion object {
        private const val TAG = "LocalHttpServer"
    }
}

private fun JSONObject.optNullableString(key: String): String? {
    if (!has(key) || isNull(key)) return null
    val s = optString(key, "")
    return s.ifBlank { null }
}
