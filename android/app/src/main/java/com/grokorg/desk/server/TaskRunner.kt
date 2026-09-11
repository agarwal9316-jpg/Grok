package com.grokorg.desk.server

import android.util.Log
import org.json.JSONObject

/** Port of Python TaskRunner — CoS decompose, specialists, synthesize. */
class TaskRunner(private val store: OrgStore) {
    private val llm get() = store.llm

    fun assignTask(
        taskId: Long,
        assigneeId: Long,
        channelId: Long?,
        run: Boolean = true,
    ): JSONObject {
        val assignee = store.getAgent(assigneeId) ?: throw ApiError(404, "Assignee not found")
        val updates = mutableMapOf<String, Any?>(
            "assignee_id" to assigneeId,
            "status" to "assigned",
        )
        if (channelId != null) updates["channel_id"] = channelId
        var task = store.updateTask(taskId, updates)

        val chId = channelId ?: task.optLongOrNull("channel_id")
        if (chId != null) {
            store.createMessage(
                chId,
                assigneeId,
                "Accepted task #${task.getLong("id")}: ${task.getString("title")}"
            )
        }

        val isHuman = assignee.optBoolean("is_human", false)
        if (run && !isHuman) {
            return runTask(taskId)
        }
        return task
    }

    fun handoff(taskId: Long, toAgentId: Long, note: String?, run: Boolean = true): JSONObject {
        val task = store.getTask(taskId) ?: throw ApiError(404, "Task not found")
        val fromId = task.optLongOrNull("assignee_id")
        store.updateTask(taskId, mapOf("status" to "handed_off"))
        val channelId = task.optLongOrNull("channel_id")
        val toAgent = store.getAgent(toAgentId) ?: throw ApiError(404, "Target agent not found")
        if (channelId != null && fromId != null) {
            var msg = "Handing off task #$taskId to ${toAgent.getString("name")}."
            if (!note.isNullOrBlank()) msg += " Note: $note"
            store.createMessage(channelId, fromId, msg)
        }
        return assignTask(taskId, toAgentId, channelId, run)
    }

    fun runTask(taskId: Long): JSONObject {
        val task = store.getTask(taskId) ?: throw ApiError(404, "Task not found")
        val assigneeId = task.optLongOrNull("assignee_id")
            ?: throw ApiError(400, "Task has no assignee")
        val assignee = store.getAgent(assigneeId) ?: throw ApiError(404, "Assignee not found")
        if (assignee.optBoolean("is_human", false)) return task

        store.updateTask(taskId, mapOf("status" to "in_progress"))
        return try {
            when (assignee.getString("role")) {
                "chief_of_staff" -> runChiefOfStaff(taskId, assignee)
                "specialist" -> runSpecialist(taskId, assignee)
                "ceo" -> runCeoAck(taskId, assignee)
                else -> store.getTask(taskId)!!
            }
        } catch (e: Exception) {
            Log.e(TAG, "Task $taskId failed", e)
            val failed = store.updateTask(
                taskId,
                mapOf("status" to "failed", "result" to (e.message ?: "error"))
            )
            val ch = failed.optLongOrNull("channel_id")
            if (ch != null) {
                store.createMessage(ch, assigneeId, "Task #$taskId failed: ${e.message}")
            }
            failed
        }
    }

    private fun runChiefOfStaff(taskId: Long, cos: JSONObject): JSONObject {
        val task = store.getTask(taskId)!!
        val orgId = task.getLong("organisation_id")
        val channelId = task.optLongOrNull("channel_id")
        val cosId = cos.getLong("id")
        val specialists = store.listSpecialists(orgId)

        val prompt =
            "Decompose the following organisational task into subtasks for Ops, Research, " +
                "and Comms specialists. Title: ${task.getString("title")}\n" +
                "Description: ${task.optString("description", "N/A")}\n" +
                "Break down into clear subtasks and assign each to a specialist team."

        val plan = llm.chat(
            listOf(
                mapOf(
                    "role" to "system",
                    "content" to (cos.optString("system_prompt").ifBlank {
                        "You are the Chief of Staff. Coordinate teams and decompose work."
                    })
                ),
                mapOf("role" to "user", "content" to prompt),
            )
        )

        if (channelId != null) {
            store.createMessage(channelId, cosId, "Decomposition plan for task #$taskId:\n$plan")
        }

        val created = mutableListOf<JSONObject>()
        for (specialist in specialists) {
            val teamId = specialist.optLongOrNull("team_id")
            val teamName = if (teamId != null) {
                store.getTeam(teamId)?.optString("name") ?: specialist.getString("name")
            } else specialist.getString("name")

            val sub = store.createTask(
                orgId = orgId,
                title = "$teamName: ${task.getString("title")}",
                description =
                    "Subtask derived from parent #$taskId.\n" +
                        "Focus area: $teamName\n" +
                        "Parent description: ${task.optString("description", task.getString("title"))}\n" +
                        "CoS plan excerpt:\n$plan",
                status = "assigned",
                assigneeId = specialist.getLong("id"),
                channelId = channelId,
                parentTaskId = taskId,
            )
            if (channelId != null) {
                store.createMessage(
                    channelId,
                    cosId,
                    "Assigned subtask #${sub.getLong("id")} to ${specialist.getString("name")} ($teamName)."
                )
            }
            created += sub
        }

        val results = mutableListOf<String>()
        for (sub in created) {
            val done = runSpecialist(sub.getLong("id"), store.getAgent(sub.getLong("assignee_id"))!!)
            val res = done.optString("result", "")
            if (res.isNotBlank()) {
                val name = store.getAgent(done.getLong("assignee_id"))?.getString("name") ?: "?"
                results += "- $name: $res"
            }
        }

        val summary = llm.chat(
            listOf(
                mapOf(
                    "role" to "system",
                    "content" to (cos.optString("system_prompt").ifBlank {
                        "You are the Chief of Staff. Synthesize team outputs for the CEO."
                    })
                ),
                mapOf(
                    "role" to "user",
                    "content" to "Synthesize results for parent task '${task.getString("title")}':\n" +
                        results.joinToString("\n")
                ),
            )
        )

        val done = store.updateTask(
            taskId,
            mapOf("result" to summary, "status" to "done")
        )
        if (channelId != null) {
            store.createMessage(channelId, cosId, "Executive summary for task #$taskId:\n$summary")
        }
        return done
    }

    private fun runSpecialist(taskId: Long, agent: JSONObject): JSONObject {
        val task = store.updateTask(taskId, mapOf("status" to "in_progress"))
        val channelId = task.optLongOrNull("channel_id")
        val agentId = agent.getLong("id")

        val result = llm.chat(
            listOf(
                mapOf(
                    "role" to "system",
                    "content" to (agent.optString("system_prompt").ifBlank {
                        "You are specialist agent ${agent.getString("name")}. Produce a concise useful result."
                    })
                ),
                mapOf(
                    "role" to "user",
                    "content" to "Complete this task.\nTitle: ${task.getString("title")}\n" +
                        "Description: ${task.optString("description", "N/A")}"
                ),
            )
        )
        val done = store.updateTask(taskId, mapOf("result" to result, "status" to "done"))
        if (channelId != null) {
            store.createMessage(channelId, agentId, "Completed task #$taskId:\n$result")
        }
        return done
    }

    private fun runCeoAck(taskId: Long, ceo: JSONObject): JSONObject {
        val task = store.getTask(taskId)!!
        val channelId = task.optLongOrNull("channel_id")
        val result = llm.chat(
            listOf(
                mapOf(
                    "role" to "system",
                    "content" to (ceo.optString("system_prompt").ifBlank {
                        "You are the CEO. Acknowledge and set direction."
                    })
                ),
                mapOf(
                    "role" to "user",
                    "content" to "Review and acknowledge: ${task.getString("title")}\n${task.optString("description", "")}"
                ),
            )
        )
        val done = store.updateTask(taskId, mapOf("result" to result, "status" to "done"))
        if (channelId != null) {
            store.createMessage(channelId, ceo.getLong("id"), result)
        }
        return done
    }

    fun runDemo(
        orgName: String = "Grok Demo Org",
        title: String = "Launch Q4 product pilot",
        description: String = "Coordinate Ops, Research, and Comms to prepare a Q4 product pilot plan.",
    ): JSONObject {
        val data = store.bootstrap(orgName)
        val org = data.getJSONObject("organisation")
        val agents = data.getJSONObject("agents")
        val cos = agents.getJSONObject("chief_of_staff")
        val channel = data.getJSONObject("channel")
        val ceo = agents.getJSONObject("ceo")

        store.createMessage(
            channel.getLong("id"),
            ceo.getLong("id"),
            "Directive: $title\n$description\nPlease coordinate the teams."
        )

        val task = store.createTask(
            orgId = org.getLong("id"),
            title = title,
            description = description,
            status = "pending",
            channelId = channel.getLong("id"),
        )

        val result = assignTask(
            task.getLong("id"),
            cos.getLong("id"),
            channel.getLong("id"),
            run = true,
        )
        val msgCount = store.messageCount(channel.getLong("id"))
        return JSONObject()
            .put("task", result)
            .put("message_count", msgCount)
            .put("channel", channel)
    }

    companion object {
        private const val TAG = "TaskRunner"
    }
}

class ApiError(val code: Int, override val message: String) : Exception(message)

fun JSONObject.optLongOrNull(key: String): Long? {
    if (!has(key) || isNull(key)) return null
    return optLong(key)
}
