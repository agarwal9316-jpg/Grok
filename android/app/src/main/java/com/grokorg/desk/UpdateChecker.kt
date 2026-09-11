package com.grokorg.desk

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.appcompat.app.AlertDialog
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class ReleaseInfo(
    val tagName: String,
    val name: String,
    val body: String,
    val htmlUrl: String,
    val apkUrl: String?
)

object UpdateChecker {
    private const val TAG = "UpdateChecker"
    private const val RELEASES_API =
        "https://api.github.com/repos/agarwal9316-jpg/Grok/releases/latest"

    suspend fun fetchLatest(): Result<ReleaseInfo> = withContext(Dispatchers.IO) {
        try {
            val conn = (URL(RELEASES_API).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("Accept", "application/vnd.github+json")
                setRequestProperty("User-Agent", "GrokOrgOS-Android")
            }
            val code = conn.responseCode
            if (code !in 200..299) {
                return@withContext Result.failure(
                    Exception("GitHub API HTTP $code")
                )
            }
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            val json = JSONObject(text)
            val tag = json.optString("tag_name", "")
            val name = json.optString("name", tag)
            val body = json.optString("body", "")
            val htmlUrl = json.optString("html_url", "")
            var apkUrl: String? = null
            val assets = json.optJSONArray("assets")
            if (assets != null) {
                for (i in 0 until assets.length()) {
                    val a = assets.getJSONObject(i)
                    val n = a.optString("name", "")
                    if (n.endsWith(".apk", ignoreCase = true)) {
                        apkUrl = a.optString("browser_download_url").ifBlank { null }
                        break
                    }
                }
            }
            Result.success(ReleaseInfo(tag, name, body, htmlUrl, apkUrl))
        } catch (e: Exception) {
            Log.w(TAG, "fetchLatest failed", e)
            Result.failure(e)
        }
    }

    /** Compare semver-ish versionName to tag like v1.2.0 or 1.2.0 */
    fun isNewer(latestTag: String, currentVersionName: String): Boolean {
        val latest = normalize(latestTag)
        val current = normalize(currentVersionName)
        if (latest.isEmpty() || current.isEmpty()) return false
        val lp = latest.split(".").mapNotNull { it.toIntOrNull() }
        val cp = current.split(".").mapNotNull { it.toIntOrNull() }
        val max = maxOf(lp.size, cp.size)
        for (i in 0 until max) {
            val l = lp.getOrElse(i) { 0 }
            val c = cp.getOrElse(i) { 0 }
            if (l > c) return true
            if (l < c) return false
        }
        return false
    }

    private fun normalize(v: String): String =
        v.trim().removePrefix("v").removePrefix("V").substringBefore("-").substringBefore("+")

    fun showUpdateDialog(context: Context, release: ReleaseInfo) {
        val notes = release.body.ifBlank { "A newer build is available." }
        val truncated = if (notes.length > 1200) notes.take(1200) + "…" else notes
        AlertDialog.Builder(context)
            .setTitle("${context.getString(R.string.update_available)}: ${release.tagName}")
            .setMessage(truncated)
            .setPositiveButton(R.string.download_update) { _, _ ->
                val url = release.apkUrl ?: release.htmlUrl
                if (url.isNotBlank()) {
                    context.startActivity(
                        Intent(Intent.ACTION_VIEW, Uri.parse(url))
                    )
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }
}
