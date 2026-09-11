package com.grokorg.desk

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
            try {
                val code = conn.responseCode
                if (code !in 200..299) {
                    return@withContext Result.failure(Exception("GitHub API HTTP $code"))
                }
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                val json = JSONObject(text)
                val tag = json.optString("tag_name", "")
                val name = json.optString("name", tag)
                val body = json.optString("body", "")
                val htmlUrl = json.optString("html_url", "")
                val apkUrl = pickBestApkUrl(json.optJSONArray("assets"))
                Result.success(ReleaseInfo(tag, name, body, htmlUrl, apkUrl))
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            Log.w(TAG, "fetchLatest failed", e)
            Result.failure(e)
        }
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
