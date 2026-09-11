package com.grokorg.desk

import android.content.Intent
import android.net.Uri
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
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
    const val RELEASES_API =
        "https://api.github.com/repos/agarwal9316-jpg/Grok/releases/latest"
    const val FALLBACK_JSON_URL =
        "https://raw.githubusercontent.com/agarwal9316-jpg/Grok/main/android/latest-release.json"
    const val RELEASES_PAGE_URL =
        "https://github.com/agarwal9316-jpg/Grok/releases"
    const val RATE_LIMIT_MESSAGE =
        "GitHub rate limit — try again in a few minutes or open Releases"

    suspend fun fetchLatest(): Result<ReleaseInfo> = withContext(Dispatchers.IO) {
        val apiResult = fetchFromApi()
        if (apiResult.isSuccess) return@withContext apiResult

        val apiError = apiResult.exceptionOrNull()
        if (!shouldTryFallback(apiError)) {
            return@withContext apiResult
        }

        Log.i(TAG, "API failed (${apiError?.message}); trying raw fallback JSON")
        val fallback = fetchFromFallbackJson()
        if (fallback.isSuccess) return@withContext fallback

        // Prefer the clearer rate-limit message when that was the API failure
        val combined = apiError?.message?.takeIf { it.contains("rate limit", ignoreCase = true) }
            ?: fallback.exceptionOrNull()?.message
            ?: apiError?.message
            ?: "Update check failed"
        Result.failure(Exception(combined))
    }

    /** True for rate-limit / network failures where raw JSON is a useful fallback. */
    fun shouldTryFallback(error: Throwable?): Boolean {
        if (error == null) return false
        val msg = error.message.orEmpty()
        if (msg.contains("rate limit", ignoreCase = true)) return true
        if (msg.contains("HTTP 403") || msg.contains("HTTP 429")) return true
        // Network / IO style failures (no HTTP code in message)
        if (!msg.contains("HTTP ")) return true
        return false
    }

    /** Map GitHub API HTTP status to a user-facing message. Exposed for unit tests. */
    fun httpErrorMessage(code: Int): String = when (code) {
        403, 429 -> RATE_LIMIT_MESSAGE
        else -> "GitHub API HTTP $code"
    }

    private fun fetchFromApi(): Result<ReleaseInfo> {
        return try {
            val conn = (URL(RELEASES_API).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("Accept", "application/vnd.github+json")
                setRequestProperty("User-Agent", "GrokOrgOS-Android")
            }
            try {
                val code = conn.responseCode
                if (code !in 200..299) {
                    return Result.failure(Exception(httpErrorMessage(code)))
                }
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                Result.success(parseApiReleaseJson(text))
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            Log.w(TAG, "fetchFromApi failed", e)
            Result.failure(e)
        }
    }

    private fun fetchFromFallbackJson(): Result<ReleaseInfo> {
        return try {
            val conn = (URL(FALLBACK_JSON_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("User-Agent", "GrokOrgOS-Android")
                setRequestProperty("Accept", "application/json")
            }
            try {
                val code = conn.responseCode
                if (code !in 200..299) {
                    return Result.failure(Exception("Fallback JSON HTTP $code"))
                }
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                Result.success(parseFallbackReleaseJson(text))
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            Log.w(TAG, "fetchFromFallbackJson failed", e)
            Result.failure(e)
        }
    }

    /** Parse GitHub /releases/latest JSON. Exposed for unit tests. */
    fun parseApiReleaseJson(text: String): ReleaseInfo {
        val json = JSONObject(text)
        val tag = json.optString("tag_name", "")
        val name = json.optString("name", tag)
        val body = json.optString("body", "")
        val htmlUrl = json.optString("html_url", "")
        val apkUrl = pickBestApkUrl(json.optJSONArray("assets"))
        return ReleaseInfo(tag, name, body, htmlUrl, apkUrl)
    }

    /**
     * Parse `android/latest-release.json` from main.
     * Prefers `apkUrl` from the file (debug APK). Exposed for unit tests.
     */
    fun parseFallbackReleaseJson(text: String): ReleaseInfo {
        val json = JSONObject(text)
        val tag = json.optString("tag", json.optString("tag_name", ""))
        val versionName = json.optString("versionName", tag.removePrefix("v").removePrefix("V"))
        val htmlUrl = json.optString(
            "htmlUrl",
            json.optString("html_url", "$RELEASES_PAGE_URL/tag/$tag")
        )
        val apkUrl = json.optString("apkUrl", json.optString("apk_url", "")).ifBlank { null }
        return ReleaseInfo(
            tagName = tag,
            name = versionName,
            body = "Update $versionName is available.",
            htmlUrl = htmlUrl,
            apkUrl = apkUrl
        )
    }

    /**
     * Prefer `*debug*.apk`; never pick `*unsigned*`. Falls back to any other `.apk`.
     * Exposed for unit tests.
     */
    fun pickBestApkUrl(assets: JSONArray?): String? {
        if (assets == null || assets.length() == 0) return null
        data class Asset(val name: String, val url: String)

        val apks = mutableListOf<Asset>()
        for (i in 0 until assets.length()) {
            val a = assets.getJSONObject(i)
            val n = a.optString("name", "")
            if (!n.endsWith(".apk", ignoreCase = true)) continue
            if (n.contains("unsigned", ignoreCase = true)) continue
            val url = a.optString("browser_download_url").ifBlank { null } ?: continue
            apks.add(Asset(n, url))
        }
        if (apks.isEmpty()) return null
        apks.firstOrNull { it.name.contains("debug", ignoreCase = true) }?.let { return it.url }
        return apks.first().url
    }

    /** Compare semver-ish versionName to tag like v1.2.0 or 1.2.0 */
    fun isNewer(latestTag: String, currentVersionName: String): Boolean {
        val latest = normalize(latestTag)
        val current = normalize(currentVersionName)
        if (latest.isEmpty() || current.isEmpty()) return false
        val lp = latest.split(".").mapNotNull { it.toIntOrNull() }
        val cp = current.split(".").mapNotNull { it.toIntOrNull() }
        if (lp.isEmpty() || cp.isEmpty()) return false
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

    /**
     * Shows release notes; positive button downloads the APK in-app and launches the installer.
     */
    fun showUpdateDialog(activity: AppCompatActivity, release: ReleaseInfo) {
        val notes = release.body.ifBlank { "A newer build is available." }
        val truncated = if (notes.length > 1200) notes.take(1200) + "…" else notes
        AlertDialog.Builder(activity)
            .setTitle("${activity.getString(R.string.update_available)}: ${release.tagName}")
            .setMessage(truncated)
            .setPositiveButton(R.string.download_and_install) { _, _ ->
                activity.lifecycleScope.launch {
                    downloadAndInstall(activity, release)
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** When update check fails completely, offer to open the GitHub releases page. */
    fun showCheckFailedDialog(activity: AppCompatActivity, message: String) {
        AlertDialog.Builder(activity)
            .setTitle(R.string.update_check_failed_title)
            .setMessage(message)
            .setPositiveButton(R.string.open_releases) { _, _ ->
                openReleasesPage(activity)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    fun openReleasesPage(activity: AppCompatActivity) {
        try {
            activity.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(RELEASES_PAGE_URL))
            )
        } catch (e: Exception) {
            Log.w(TAG, "openReleasesPage failed", e)
            Toast.makeText(activity, messageOrUnknown(e), Toast.LENGTH_LONG).show()
        }
    }

    private fun messageOrUnknown(e: Exception): String = e.message ?: "unknown"

    private suspend fun downloadAndInstall(activity: AppCompatActivity, release: ReleaseInfo) {
        val apkUrl = release.apkUrl
        if (apkUrl.isNullOrBlank()) {
            Toast.makeText(activity, R.string.update_no_apk, Toast.LENGTH_LONG).show()
            return
        }

        if (!ApkInstaller.canInstallPackages(activity)) {
            AlertDialog.Builder(activity)
                .setTitle(R.string.allow_install_title)
                .setMessage(R.string.allow_install_message)
                .setPositiveButton(R.string.open_settings) { _, _ ->
                    ApkInstaller.openUnknownSourcesSettings(activity)
                }
                .setNegativeButton(R.string.cancel, null)
                .show()
            return
        }

        val progress = AlertDialog.Builder(activity)
            .setTitle(R.string.downloading_update)
            .setMessage(activity.getString(R.string.download_progress, 0))
            .setCancelable(false)
            .create()
        progress.show()

        try {
            val file = ApkInstaller.downloadApk(activity, apkUrl) { pct ->
                activity.runOnUiThread {
                    if (progress.isShowing) {
                        progress.setMessage(
                            if (pct < 0) {
                                activity.getString(R.string.downloading_update)
                            } else {
                                activity.getString(R.string.download_progress, pct)
                            }
                        )
                    }
                }
            }
            if (progress.isShowing) progress.dismiss()
            try {
                ApkInstaller.installApk(activity, file)
            } catch (e: Exception) {
                Log.w(TAG, "installApk failed", e)
                Toast.makeText(
                    activity,
                    activity.getString(R.string.install_failed, e.message ?: "unknown"),
                    Toast.LENGTH_LONG
                ).show()
            }
        } catch (e: Exception) {
            if (progress.isShowing) progress.dismiss()
            Log.w(TAG, "downloadAndInstall failed", e)
            Toast.makeText(
                activity,
                activity.getString(R.string.download_failed, e.message ?: "unknown"),
                Toast.LENGTH_LONG
            ).show()
        }
    }
}
